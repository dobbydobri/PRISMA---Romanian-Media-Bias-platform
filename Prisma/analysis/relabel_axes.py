import argparse
import json
import logging
import socket
import time
from collections import defaultdict
from pathlib import Path

import httpx
import psycopg2

from env import DATABASE_URL, OLLAMA_BASE_URL
from urllib.parse import urlparse

DB_URL        = DATABASE_URL
OLLAMA_URL   = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_MODEL  = "aya-expanse:8b"

MAX_CONTENT_CHARS     = 1200
REQUEST_TIMEOUT       = 60.0
COMMIT_BATCH_SIZE     = 10
RELABEL_VERSION       = "v3_single_axis"
OLLAMA_POLL_INTERVAL  = 5
OLLAMA_MAX_WAIT       = 300

POLITICAL_TOPICS = {'politics', 'justice', 'economy', 'foreign_affairs'}

FACTCHECKER_OUTLETS = {'Factual', 'Veridica'}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

FAILED_LOG     = Path(__file__).parent / "relabel_failed.log"
RATIONALES_LOG = Path(__file__).parent / "relabel_rationales.log"


# ── Prompts ───────────────────────────────────────────────────────────────────

GOV_STANCE_PROMPT = """\
You are evaluating how a Romanian news article FRAMES the current governing coalition (PSD+PNL+UDMR). Focus on editorial choices — which sources are quoted, which words are chosen, which facts are emphasized or omitted — NOT on whether the news itself is positive or negative for the government.

IMPORTANT: This classification is ONLY about framing of government/coalition actors. If the article does not discuss government policy, legislation, ministers, or the PSD+PNL+UDMR coalition, the answer is always neutru regardless of the article's general tone.

Examples:
- Corruption indictment with balanced sourcing → neutru
- Corruption indictment with only opposition reactions and loaded adjectives → critic
- Government program with only ministerial quotes and no critical voices → favorabil
- Health article criticizing a medical practice → neutru (not about government)

Respond with ONLY a valid JSON object:
{{"gov_stance": "<str>", "signal_phrase": "<str>", "rationale": "<str>"}}

GOV_STANCE — pick ONE:
  critic — negative editorial framing toward the government (skeptical tone, critical sources foregrounded, government failures emphasized through word choice)
  favorabil — positive editorial framing toward the government (achievements emphasized, supportive sources, optimistic tone, no critical voices)
  neutru — article does not concern governance, OR reporting is genuinely balanced with both supportive and critical perspectives. Do NOT use neutru as a safe default — if any editorial lean toward government exists, pick critic or favorabil.

SIGNAL_PHRASE: copy 3-8 words from the article showing the government framing direction. If no government content, write "no_gov_content".
RATIONALE: one sentence.

Title: {title}
Text: {content}\
"""

FRAMING_PROMPT = """\
You are classifying the dominant EDITORIAL FRAMING STYLE of a Romanian news article. This is about journalistic technique, not topic or political stance.

Respond with ONLY a valid JSON object:
{{"framing": "<str>", "signal_phrase": "<str>", "rationale": "<str>"}}

FRAMING — pick ONE:
  critic — accountability framing: problems, failures, risks foregrounded; negative consequences emphasized; article demands answers or responsibility
  favorabil — positive/promotional framing: achievements, benefits foregrounded; tone supportive or celebratory; criticism absent; reads like a press release
  investigativ — the journalist conducted ORIGINAL investigation and discovered NEW information through documents, data, leaked sources, or verification work. Includes fact-checking articles that verify claims using primary sources and original research. The article builds a case with evidence.
  other — does not clearly fit critic, favorabil, or investigativ (neutral wire-service reporting, mixed framing with no dominant style)

When in doubt between critic and favorabil, pick whichever matches the dominant tone. Use "other" only when no editorial direction is present.

SIGNAL_PHRASE: copy 3-8 words exemplifying the framing style.
RATIONALE: one sentence.

Title: {title}
Text: {content}\
"""


# ── Ollama helpers ────────────────────────────────────────────────────────────

def ollama_is_reachable(timeout=3.0):
    parsed = urlparse(OLLAMA_BASE_URL)
    host   = parsed.hostname
    port   = parsed.port or 11434
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_ollama():
    waited = 0
    while not ollama_is_reachable():
        if waited >= OLLAMA_MAX_WAIT:
            log.error(f"Ollama unreachable after {OLLAMA_MAX_WAIT}s. Exiting.")
            raise SystemExit(1)
        log.warning(f"Ollama unreachable, retrying in {OLLAMA_POLL_INTERVAL}s...")
        time.sleep(OLLAMA_POLL_INTERVAL)
        waited += OLLAMA_POLL_INTERVAL
    log.info("Ollama is reachable.")


def call_ollama(client, prompt, num_predict):
    response = client.post(
        OLLAMA_URL,
        json={
            "model":   OLLAMA_MODEL,
            "prompt":  prompt,
            "stream":  False,
            "keep_alive": "30m",
            "options": {"temperature": 0.0, "num_predict": num_predict, "top_p": 1.0},
        },
        timeout=REQUEST_TIMEOUT,
    )
    return response.json().get("response", "")


def parse_json_response(raw):
    if not raw:
        return None
    cleaned = (raw.strip()
               .removeprefix("```json")
               .removeprefix("```")
               .removesuffix("```")
               .strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None


def call_with_retry(client, prompt, num_predict):
    while True:
        try:
            return call_ollama(client, prompt, num_predict)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            log.warning(f"Connection lost ({e}). Waiting for Ollama...")
            wait_for_ollama()


# ── Commit buffer ─────────────────────────────────────────────────────────────

class CommitBuffer:
    def __init__(self, conn, batch_size):
        self.conn = conn
        self.batch_size = batch_size
        self.pending = 0

    def mark_write(self):
        self.pending += 1
        if self.pending >= self.batch_size:
            self.flush()

    def flush(self):
        if self.pending > 0:
            self.conn.commit()
            self.pending = 0


# ── Axis scoring ──────────────────────────────────────────────────────────────

VALID_GOV_STANCE = {"critic", "favorabil", "neutru"}
VALID_FRAMING    = {"critic", "favorabil", "investigativ", "other"}


def score_axis(client, axis_name, prompt_template, valid_values,
               title, content, article_id):
    """Score one axis via LLM. Returns (value, success)."""
    truncated = (content or "")[:MAX_CONTENT_CHARS]
    raw = call_with_retry(
        client,
        prompt_template.format(title=title, content=truncated),
        num_predict=200,
    )
    data = parse_json_response(raw)

    if data and data.get(axis_name) in valid_values:
        value = data[axis_name]
        with open(RATIONALES_LOG, "a", encoding="utf-8") as f:
            f.write(
                f"{article_id}\t{axis_name}\t{value}\t"
                f"{data.get('signal_phrase', '')}\t"
                f"{data.get('rationale', '')}\n"
            )
        return value, True
    else:
        with open(FAILED_LOG, "a", encoding="utf-8") as f:
            f.write(f"{axis_name}\t{article_id}\t{title[:80]}\t{(raw or 'EMPTY')[:200]}\n")
        return None, False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    log.info("Checking Ollama connectivity...")
    wait_for_ollama()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    buf  = CommitBuffer(conn, COMMIT_BATCH_SIZE)
    client = httpx.Client()

    limit_clause = f"LIMIT {args.limit}" if args.limit > 0 else ""
    cur.execute(f"""
        SELECT a.id, a.title, a.content_text, a.llm_topic, o.name AS outlet
        FROM articles a
        JOIN outlets o ON a.outlet_id = o.id
        WHERE a.llm_sovereignism IS NOT NULL
          AND a.llm_gov_stance IS NULL
          AND a.llm_topic IS NOT NULL
          AND a.content_text IS NOT NULL
          AND LENGTH(a.content_text) >= 200
        ORDER BY a.id
        {limit_clause}
    """)
    articles = cur.fetchall()
    total = len(articles)

    political   = sum(1 for _, _, _, t, o in articles
                      if t in POLITICAL_TOPICS and o not in FACTCHECKER_OUTLETS)
    factcheckers = sum(1 for _, _, _, _, o in articles if o in FACTCHECKER_OUTLETS)
    auto_neutru  = total - political - factcheckers

    log.info(f"Articles to re-label: {total:,}")
    log.info(f"  Political (LLM gov_stance + framing):        {political:,}")
    log.info(f"  Fact-checkers (auto gov_stance, LLM framing):{factcheckers:,}")
    log.info(f"  Non-political (auto gov_stance, LLM framing):{auto_neutru:,}")
    log.info(f"  Estimated LLM calls: ~{political + total:,}")

    stats = {
        "gov_stance": defaultdict(int),
        "framing":    defaultdict(int),
        "gov_auto_neutru": 0,
        "gov_failed":      0,
        "framing_failed":  0,
    }
    start = time.time()

    for idx, (article_id, title, content, topic, outlet) in enumerate(articles, 1):
        gov_value     = None
        framing_value = None
        is_factchecker = outlet in FACTCHECKER_OUTLETS

        # ── Gov stance ────────────────────────────────────────────
        if is_factchecker or topic not in POLITICAL_TOPICS:
            gov_value = "neutru"
            stats["gov_auto_neutru"] += 1
        else:
            gov_value, ok = score_axis(
                client, "gov_stance", GOV_STANCE_PROMPT,
                VALID_GOV_STANCE, title, content, article_id,
            )
            if not ok:
                stats["gov_failed"] += 1

        if gov_value:
            stats["gov_stance"][gov_value] += 1

        # ── Framing ───────────────────────────────────────────────
        framing_value, ok = score_axis(
            client, "framing", FRAMING_PROMPT,
            VALID_FRAMING, title, content, article_id,
        )
        if not ok:
            stats["framing_failed"] += 1
        if framing_value:
            stats["framing"][framing_value] += 1

        # ── Write to DB ───────────────────────────────────────────
        if not args.dry_run and (gov_value or framing_value):
            set_parts = ["llm_prompt_version = %s", "llm_scored_at = NOW()"]
            values    = [RELABEL_VERSION]

            if gov_value:
                set_parts.append("llm_gov_stance = %s")
                values.append(gov_value)
            if framing_value:
                set_parts.append("llm_framing = %s")
                values.append(framing_value)

            values.append(article_id)
            cur.execute(
                f"UPDATE articles SET {', '.join(set_parts)} WHERE id = %s",
                values,
            )
            buf.mark_write()

        # ── Progress ──────────────────────────────────────────────
        if idx % 50 == 0:
            elapsed = time.time() - start
            log.info(
                f"  {idx:,}/{total:,}  ({idx/elapsed:.1f} art/sec)  "
                f"gov={dict(stats['gov_stance'])}  "
                f"frm={dict(stats['framing'])}  "
                f"auto={stats['gov_auto_neutru']}  "
                f"gov_fail={stats['gov_failed']}  frm_fail={stats['framing_failed']}"
            )

    buf.flush()
    client.close()

    elapsed = time.time() - start
    log.info(f"\nComplete. {total:,} articles in {elapsed/60:.1f} min.")

    for axis_name in ["gov_stance", "framing"]:
        dist       = stats[axis_name]
        total_axis = sum(dist.values())
        log.info(f"\n  {axis_name} (n={total_axis}):")
        for label, count in sorted(dist.items(), key=lambda x: -x[1]):
            log.info(f"    {label:20s} {count:>5d}  ({count/total_axis*100:.1f}%)")

    log.info(f"\n  gov auto-neutru : {stats['gov_auto_neutru']}")
    log.info(f"  gov LLM failures: {stats['gov_failed']}")
    log.info(f"  frm LLM failures: {stats['framing_failed']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\nInterrupted. Committed batches are safe.")
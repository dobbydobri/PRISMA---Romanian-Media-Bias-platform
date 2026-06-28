"""
PRISMA — EU Orientation Expansion Pass
---------------------------------------
Labels unlabeled articles that pass the EU keyword filter.

Pipeline per article:
  1. Topic prompt (1 call) → writes llm_topic
  2. If topic is political → EU orientation prompt (2-3 calls via voting)

Stops automatically when both suveranist >= TARGET and pragmatic >= TARGET
in the full database (not just this run).

Run:
    python expand_eu_labels.py
    python expand_eu_labels.py --dry-run
    python expand_eu_labels.py --target 350   # override class threshold
"""

import argparse
import json
import logging
import socket
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import httpx
import psycopg2
import psycopg2.extras

from env import DATABASE_URL, OLLAMA_BASE_URL

# ── Config ────────────────────────────────────────────────────────────────────

DB_URL               = DATABASE_URL
OLLAMA_URL           = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_MODEL         = "aya-expanse:8b"
MAX_CONTENT_CHARS    = 1200
REQUEST_TIMEOUT      = 60.0
COMMIT_BATCH_SIZE    = 10
OLLAMA_POLL_INTERVAL = 5
OLLAMA_MAX_WAIT      = 300
DEFAULT_TARGET       = 300
CHECK_THRESHOLD_EVERY = 50   # check DB counts every N articles processed

POLITICAL_TOPICS    = {'politics', 'justice', 'economy', 'foreign_affairs'}
FACTCHECKER_OUTLETS = {'Factual', 'Veridica'}

NEWS_TOPICS = {
    'politics', 'economy', 'foreign_affairs', 'justice', 'health',
    'culture', 'social', 'environment', 'technology'
}

OUT_OF_SCOPE_TOPICS = {
    'religious_content', 'lifestyle_wellness', 'recipe_howto',
    'entertainment_celebrity', 'astrology_horoscope',
    'sports_routine', 'routine_bulletin', 'sports', 'other_news'
}

ALL_VALID_TOPICS = NEWS_TOPICS | OUT_OF_SCOPE_TOPICS

EU_KEYWORDS = [
    'uniunea europeană', 'comisia europeană', 'bruxelles', 'parlamentul european',
    'fonduri europene', 'fonduri ue', 'integrare europeană', 'valori europene',
    'spațiul schengen', 'zona euro', 'acquis', 'suveranitate', 'dictat european',
    'cedarea suveranit', 'pierderea suveranit', 'alianța nato', 'flancul estic',
    'parteneriat transatlantic', 'birocrați de la bruxelles', 'federalizare',
    'colonie europeană', 'periferia europei', 'aderare la zona euro',
    'absorbția fondurilor', 'mecanismul de cooperare', 'interferență europeană',
]

EU_TITLE_KEYWORDS = ['ue', 'nato', 'bruxelles', 'european', 'europa', 'schengen', 'suveran']

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

FAILED_LOG     = Path(__file__).parent / "expand_eu_failed.log"
RATIONALES_LOG = Path(__file__).parent / "expand_eu_rationales.log"


# ── Prompts ───────────────────────────────────────────────────────────────────

TOPIC_PROMPT = """\
Classify the topic of this Romanian news article. Pick the ONE best label.

IN-SCOPE topics:
  politics        — government, parties, elections, parliament, politicians
  economy         — business, finance, markets, budgets, employment, trade
  foreign_affairs — international relations, wars, diplomacy, EU/NATO institutional news
  justice         — courts, prosecutors, corruption cases, laws, verdicts
  health          — medicine, public health, hospitals, pandemics
  culture         — arts, history, education, literature, film
  social          — society, demographics, community issues, poverty, migration
  environment     — climate, nature, pollution, energy transition
  technology      — tech industry, digital policy, cybersecurity, AI

OUT-OF-SCOPE topics (use these when the article does not belong above):
  sports_routine         — match results, scores, sports events
  lifestyle_wellness     — recipes, health tips, beauty, travel guides
  entertainment_celebrity — celebrity news, gossip, film releases
  religious_content      — church news, religious ceremonies
  astrology_horoscope    — horoscopes, esoteric content
  routine_bulletin       — weather, traffic, administrative notices
  other_news             — does not fit any category above

Respond with ONLY a valid JSON object:
{{"topic": "<label>", "rationale": "<one sentence>"}}

Title: {title}
Text: {content}\
"""

EU_PROMPT = """\
You are classifying how a Romanian news article FRAMES Romania's relationship with the European Union and Euro-Atlantic institutions.

IMPORTANT: Classify the JOURNALIST'S OWN framing, not the views of politicians quoted in the article. An article that neutrally reports an anti-EU politician's speech is PRAGMATIC, not SUVERANIST.

Pick ONE label:

PRO_EUROPEAN — The journalist frames EU membership, European integration, or NATO alignment as beneficial or desirable for Romania. Signals: EU values or partnerships described positively, Schengen/euro accession framed as achievement, European solidarity emphasized, EU criticism absent or dismissed.
Example: article about Romania's Schengen accession that uses "pas important", "succes", "apropierea de Europa" without any critical voice.

SUVERANIST — The journalist frames EU institutions or European integration as a threat to Romanian autonomy or national interest. Signals: EU rules described as impositions, Brussels portrayed as controlling Romania, national sovereignty presented as primary value, EU described as bureaucratic or harmful.
Example: article using "dictat de la Bruxelles", "cedarea suveranității", "interferență europeană", or framing EU regulations as damaging to Romania.

PRAGMATIC — The article discusses EU matters factually without ideological framing. Covers: fund absorption deadlines, trade negotiations, regulatory compliance, institutional appointments, NATO military logistics. Also use when reporting on pro-EU or sovereignist politicians without the journalist taking a side.
Example: article about EU fund absorption percentages, Schengen border procedures, or trade tariff negotiations with no editorial lean.

Do NOT use PRAGMATIC as a default. If the journalist's word choices show any lean toward EU being beneficial or threatening, pick PRO_EUROPEAN or SUVERANIST.

Respond with ONLY a valid JSON object:
{{"eu_orientation": "<pro_european/suveranist/pragmatic>", "signal_phrase": "<3-8 words from the article showing the framing>", "rationale": "<one sentence>"}}

Title: {title}
Text: {content}\
"""


# ── Ollama helpers ────────────────────────────────────────────────────────────

def is_eu_relevant(title: str, content: str) -> bool:
    title_l   = (title or '').lower()
    content_l = (content or '').lower()
    if any(kw in title_l for kw in EU_TITLE_KEYWORDS):
        return True
    return any(kw in content_l for kw in EU_KEYWORDS)


def ollama_is_reachable(timeout=3.0) -> bool:
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


def call_ollama(client: httpx.Client, prompt: str, num_predict: int = 150) -> str:
    response = client.post(
        OLLAMA_URL,
        json={
            "model":      OLLAMA_MODEL,
            "prompt":     prompt,
            "stream":     False,
            "keep_alive": "30m",
            "options":    {"temperature": 0.2, "num_predict": num_predict,
                           "num_ctx": 2048, "top_p": 1.0},
        },
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 404:
        raise RuntimeError(
            f"Ollama 404: model '{OLLAMA_MODEL}' not found. "
            f"Run 'ollama list' to check available models."
        )
    if response.status_code >= 500:
        raise RuntimeError(f"Ollama error {response.status_code}: {response.text[:200]}")
    return response.json().get("response", "")


def call_with_retry(client: httpx.Client, prompt: str, num_predict: int = 150) -> str:
    while True:
        try:
            return call_ollama(client, prompt, num_predict)
        except RuntimeError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            log.warning(f"Connection lost ({e}). Waiting for Ollama...")
            wait_for_ollama()


def parse_json(raw: str) -> dict | None:
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


def log_failure(axis: str, article_id: int, title: str, raw: str):
    with open(FAILED_LOG, "a", encoding="utf-8") as f:
        f.write(f"{axis}\t{article_id}\t{title[:80]}\t{(raw or 'EMPTY')[:200]}\n")


def log_rationale(article_id: int, axis: str, label: str, signal: str, rationale: str):
    with open(RATIONALES_LOG, "a", encoding="utf-8") as f:
        f.write(f"{article_id}\t{axis}\t{label}\t{signal}\t{rationale}\n")


# ── Voting ────────────────────────────────────────────────────────────────────

def run_vote(client: httpx.Client, prompt: str, extract_fn, valid_values: set,
             article_id: int, axis: str, title: str, max_runs: int = 3):
    votes    = []
    vote_log = []
    fail_count = 0

    for run_idx in range(max_runs):
        raw  = call_with_retry(client, prompt)
        data = parse_json(raw)

        if data:
            value = extract_fn(data)
            if value in valid_values:
                votes.append((value, data))
                vote_log.append(value)
            else:
                log_failure(axis, article_id, title, raw)
                vote_log.append(None)
                fail_count += 1
        else:
            log_failure(axis, article_id, title, raw)
            vote_log.append(None)
            fail_count += 1

        if fail_count == run_idx + 1:
            log.warning(f"All calls failed for article {article_id} axis={axis}. Aborting.")
            return None, None, vote_log

        valid_votes = [v for v, _ in votes]

        if len(votes) == 2:
            if valid_votes[0] == valid_votes[1]:
                winner_data = votes[0][1]
                log_rationale(article_id, axis, valid_votes[0],
                              winner_data.get('signal_phrase', ''),
                              winner_data.get('rationale', ''))
                return winner_data, 'high', vote_log
            if run_idx + 1 < max_runs:
                continue

        if len(vote_log) == max_runs:
            counts = defaultdict(list)
            for v, d in votes:
                counts[v].append(d)
            majority = [(v, d_list) for v, d_list in counts.items() if len(d_list) >= 2]
            if majority:
                winner_val, winner_data_list = majority[0]
                winner_data = winner_data_list[0]
                log_rationale(article_id, axis, winner_val,
                              winner_data.get('signal_phrase', ''),
                              winner_data.get('rationale', ''))
                return winner_data, 'low', vote_log
            return None, None, vote_log

    return None, None, vote_log


# ── Database ──────────────────────────────────────────────────────────────────

def fetch_expansion_candidates(conn) -> list[dict]:
    """
    Fetch unlabeled articles that pass the EU keyword filter,
    stratified by outlet (~175 per outlet), sovereignist-signal articles first.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT a.id, a.title, a.content_text, o.name AS outlet
        FROM (
            SELECT a.id, a.title, a.content_text, a.outlet_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.outlet_id
                       ORDER BY (
                           CASE WHEN a.content_text ILIKE '%suveranitate%'
                                     OR a.content_text ILIKE '%dictat european%'
                                     OR a.content_text ILIKE '%cedarea suveranit%'
                                     OR a.title ILIKE '%suveran%'
                                THEN 0 ELSE 1 END
                       ), RANDOM()
                   ) AS rn
            FROM articles a
            WHERE a.llm_topic IS NULL
              AND NOT COALESCE(a.is_excluded, false)
              AND a.content_text IS NOT NULL
              AND LENGTH(a.content_text) >= 200
              AND (
                  a.content_text ILIKE '%uniunea europeană%'
                  OR a.content_text ILIKE '%comisia europeană%'
                  OR a.content_text ILIKE '%bruxelles%'
                  OR a.content_text ILIKE '%parlamentul european%'
                  OR a.content_text ILIKE '%fonduri europene%'
                  OR a.content_text ILIKE '%suveranitate%'
                  OR a.content_text ILIKE '%dictat european%'
                  OR a.content_text ILIKE '%integrare europeană%'
                  OR a.content_text ILIKE '%alianța nato%'
                  OR a.content_text ILIKE '%cedarea suveranit%'
                  OR a.title ILIKE '%european%'
                  OR a.title ILIKE '%ue %'
                  OR a.title ILIKE '%nato%'
                  OR a.title ILIKE '%bruxelles%'
                  OR a.title ILIKE '%suveran%'
              )
        ) a
        JOIN outlets o ON a.outlet_id = o.id
        WHERE a.rn <= 175
        ORDER BY o.name, a.id
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def get_eu_class_counts(conn) -> dict:
    """Get current EU orientation label counts from the full database."""
    cur = conn.cursor()
    cur.execute("""
        SELECT llm_eu_orientation, COUNT(*)
        FROM articles
        WHERE llm_eu_orientation IS NOT NULL
        GROUP BY llm_eu_orientation
    """)
    counts = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    return counts


class CommitBuffer:
    def __init__(self, conn, batch_size: int):
        self.conn       = conn
        self.batch_size = batch_size
        self.pending    = 0

    def mark_write(self):
        self.pending += 1
        if self.pending >= self.batch_size:
            self.flush()

    def flush(self):
        if self.pending > 0:
            self.conn.commit()
            self.pending = 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PRISMA EU orientation expansion pass")
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--target",  type=int, default=DEFAULT_TARGET,
                        help=f"Min examples per minority class (default: {DEFAULT_TARGET})")
    args = parser.parse_args()

    log.info("Checking Ollama...")
    wait_for_ollama()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    buf  = CommitBuffer(conn, COMMIT_BATCH_SIZE)
    client = httpx.Client()

    # Show current class counts before starting
    initial_counts = get_eu_class_counts(conn)
    log.info(f"Current EU orientation counts: {initial_counts}")
    log.info(f"Target per minority class: {args.target}")

    candidates = fetch_expansion_candidates(conn)
    log.info(f"Expansion candidates: {len(candidates):,} articles")

    stats = {
        'topic_labeled':    0,
        'topic_political':  0,
        'topic_oos':        0,
        'eu_labeled':       0,
        'eu_skipped':       0,
        'eu': defaultdict(int),
    }

    start     = time.time()
    threshold_met = False

    for idx, article in enumerate(candidates, 1):
        article_id = article['id']
        title      = article['title'] or ''
        content    = (article['content_text'] or '')[:MAX_CONTENT_CHARS]
        outlet     = article['outlet']

        # ── Step 1: Topic labeling (single call, no voting needed) ────────────
        topic_prompt = TOPIC_PROMPT.format(title=title, content=content)
        raw  = call_with_retry(client, topic_prompt)
        data = parse_json(raw)

        topic = None
        if data:
            raw_topic = (data.get('topic') or '').lower().strip()
            if raw_topic in ALL_VALID_TOPICS:
                topic = raw_topic
            else:
                log_failure('topic', article_id, title, raw)
        else:
            log_failure('topic', article_id, title, raw)

        if not topic:
            continue

        # Write topic immediately
        if not args.dry_run:
            cur.execute(
                "UPDATE articles SET llm_topic = %s, llm_v4_scored_at = NOW() WHERE id = %s",
                (topic, article_id)
            )
            buf.mark_write()

        stats['topic_labeled'] += 1

        # Out of scope → skip EU labeling
        if topic in OUT_OF_SCOPE_TOPICS:
            stats['topic_oos'] += 1
            continue

        # Non-political in-scope → skip EU labeling
        is_political = topic in POLITICAL_TOPICS and outlet not in FACTCHECKER_OUTLETS
        if not is_political:
            continue

        stats['topic_political'] += 1

        # ── Step 2: EU orientation (voting) ───────────────────────────────────
        eu_prompt = EU_PROMPT.format(title=title, content=content)
        result, conf, votes = run_vote(
            client, eu_prompt,
            extract_fn   = lambda d: d.get('eu_orientation', '').lower(),
            valid_values = {'pro_european', 'suveranist', 'pragmatic'},
            article_id   = article_id,
            axis         = 'eu',
            title        = title,
            max_runs     = 3,
        )

        if result:
            eu_val = (result.get('eu_orientation') or '').lower()
            if not args.dry_run:
                cur.execute("""
                    UPDATE articles
                    SET llm_eu_orientation = %s,
                        llm_eu_conf        = %s,
                        llm_eu_votes       = %s,
                        llm_v4_scored_at   = NOW()
                    WHERE id = %s
                """, (eu_val, conf, json.dumps(votes), article_id))
                buf.mark_write()
            stats['eu'][eu_val] += 1
            stats['eu_labeled'] += 1
        else:
            stats['eu_skipped'] += 1

        # ── Progress ──────────────────────────────────────────────────────────
        if idx % 50 == 0:
            elapsed = time.time() - start
            rate    = idx / elapsed if elapsed > 0 else 0
            log.info(
                f"  {idx:,}/{len(candidates):,} ({rate:.1f} art/sec) | "
                f"topic={stats['topic_labeled']} political={stats['topic_political']} "
                f"oos={stats['topic_oos']} | eu={dict(stats['eu'])} "
                f"skip={stats['eu_skipped']}"
            )

            # Check threshold against full DB counts
            if not args.dry_run:
                current_counts = get_eu_class_counts(conn)
                suveranist_n   = current_counts.get('suveranist', 0)
                pragmatic_n    = current_counts.get('pragmatic', 0)
                log.info(
                    f"  DB totals → suveranist: {suveranist_n} / {args.target}  "
                    f"pragmatic: {pragmatic_n} / {args.target}"
                )
                if suveranist_n >= args.target and pragmatic_n >= args.target:
                    log.info(
                        f"Both minority classes reached target of {args.target}. Stopping."
                    )
                    threshold_met = True
                    break

    buf.flush()
    client.close()

    elapsed = time.time() - start
    log.info(f"\nExpansion complete. {idx:,} candidates processed in {elapsed/60:.1f} min.")
    log.info(f"  Topics labeled:   {stats['topic_labeled']}")
    log.info(f"  Political:        {stats['topic_political']}")
    log.info(f"  Out of scope:     {stats['topic_oos']}")
    log.info(f"  EU labeled:       {stats['eu_labeled']}")
    log.info(f"  EU skipped:       {stats['eu_skipped']}")
    log.info(f"  EU distribution:  {dict(stats['eu'])}")

    if not args.dry_run:
        final_counts = get_eu_class_counts(conn)
        log.info(f"\nFinal DB EU counts: {final_counts}")
        if not threshold_met:
            suveranist_n = final_counts.get('suveranist', 0)
            pragmatic_n  = final_counts.get('pragmatic', 0)
            if suveranist_n < args.target or pragmatic_n < args.target:
                log.warning(
                    f"Target not fully reached. "
                    f"suveranist={suveranist_n}/{args.target} "
                    f"pragmatic={pragmatic_n}/{args.target}. "
                    f"Consider increasing --target or expanding the candidate pool."
                )

    conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\nInterrupted. Committed batches are safe.")
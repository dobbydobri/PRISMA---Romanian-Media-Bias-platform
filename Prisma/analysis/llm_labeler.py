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

DB_URL            = DATABASE_URL
OLLAMA_URL        = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_MODEL      = "aya-expanse:8b"
MAX_CONTENT_CHARS = 1200
REQUEST_TIMEOUT   = 60.0
COMMIT_BATCH_SIZE = 10
LABEL_VERSION     = "v4"
OLLAMA_POLL_INTERVAL = 5
OLLAMA_MAX_WAIT      = 300

POLITICAL_TOPICS    = {'politics', 'justice', 'economy', 'foreign_affairs'}
FACTCHECKER_OUTLETS = {'Factual', 'Veridica'}

EU_KEYWORDS = [
    'uniunea europeană', 'comisia europeană', 'bruxelles', 'parlamentul european',
    'fonduri europene', 'fonduri ue', 'integrare europeană', 'valori europene',
    'spațiul schengen', 'zona euro', 'acquis', 'suveranitate', 'dictat european',
    'cedarea suveranit', 'pierderea suveranit', 'alianța nato', 'flancul estic',
    'parteneriat transatlantic', 'birocrați de la bruxelles', 'federalizare',
    'colonie europeană', 'periferia europei', 'aderare la zona euro',
    'absorbția fondurilor', 'mecanismul de cooperare', 'interferență europeană',
]

EU_TITLE_KEYWORDS = ['ue', 'nato', 'bruxelles', 'european', 'europa', 'schengen']

FACTCHECK_TITLE_PREFIXES = (
    'fals |', 'adevărat |', 'parțial adevărat |', 'context lipsă |',
    'fals:', 'adevărat:', 'parțial adevărat:', 'context lipsă:',
)


def is_factcheck_article(title: str) -> bool:
    """Returns True if the title matches a known fact-check verdict format."""
    return (title or '').lower().strip().startswith(FACTCHECK_TITLE_PREFIXES)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

FAILED_LOG     = Path(__file__).parent / "label_v4_failed.log"
RATIONALES_LOG = Path(__file__).parent / "label_v4_rationales.log"


# ── Prompts ───────────────────────────────────────────────────────────────────

REGISTER_PROMPT = """\
Classify the JOURNALISTIC STYLE of this Romanian news article. You are classifying HOW the article is written, not WHAT it is about.

Pick ONE label:

INFORMATIV — Standard news reporting. The journalist reports facts, quotes sources, presents multiple perspectives. Neutral tone. Wire-service style. Example: "Ministrul X a declarat că... Opoziția a criticat măsura, susținând că..."

OPINIE — The journalist expresses personal views or takes a clear position. Uses evaluative language, strong adjectives, or first-person voice. Often has a named columnist. Example: "Este inadmisibil ca guvernul să..." or "Trebuie să recunoaștem că..."

INVESTIGATIV — Two types qualify:
(a) Original investigation: the journalist discovered new information through documents, data analysis, leaked sources, or verification work. Example: "Am obținut documente care arată că..." or "Investigație exclusivă:"
(b) Fact-checking: the article verifies a specific public claim using primary sources, official data, or expert consultation, and delivers a verdict. Signals: title starts with "FALS |", "ADEVĂRAT |", "PARȚIAL ADEVĂRAT |", "CONTEXT LIPSĂ |", or the article opens by stating a claim and then systematically verifies or refutes it with evidence.

PROMOTIONAL — Reads like a press release. Only one source quoted, no critical voices, achievements presented without scrutiny. Often announces a project, budget, or event using the institution's own language. Example: "Primăria a anunțat un buget record, construit pe promisiunea continuării investițiilor..."

If the article mixes styles, pick the DOMINANT one.

Respond with ONLY a valid JSON object:
{{"register": "<label>", "signal_phrase": "<copy 3-8 words from the article showing the style>", "rationale": "<one sentence>"}}

Title: {title}
Text: {content}\
"""

STANCE_PROMPT = """\
Analyze how this Romanian news article FRAMES the main political actor it discusses.

STEP 1 — Who is this article mainly about?
Identify the ONE political actor (person, party, institution, or organization) that receives the most attention. Write their name as it appears in the article.
If the article is not about any political actor, write "none" and stop.

STEP 2 — How does the article frame this actor?
Focus on the journalist's editorial choices: word choice, which sources are quoted, what is emphasized or omitted.

CRITIC — negative framing: loaded or dismissive language, critical sources dominate, failures or scandals foregrounded, government or actor portrayed as incompetent or corrupt
FAVORABIL — positive framing: achievements and benefits highlighted, supportive or celebratory tone, critical voices absent or marginalized
NEUTRU — the article presents multiple perspectives with no dominant lean, OR reports events factually without editorial color (wire-service style, press conference summary, electoral procedure report)

Use NEUTRU when:
- Both supportive and critical voices are genuinely present
- The article is a factual summary with no adjectives revealing editorial position
- The journalist's voice is absent — only facts and direct quotes

Use CRITIC or FAVORABIL when the journalist's word choices or source selection clearly push in one direction, even subtly.

STEP 3 — Is the stance visible or hidden?
EXPLICIT — overt loaded language, sarcasm, or evaluative adjectives ("tupeu", "scandalos", "excelent")
IMPLICIT — bias through source selection, emphasis, or omission rather than language
If stance is NEUTRU, write "none" for intensity.

Respond with ONLY valid JSON:
{{"entity": "<name or none>", "stance": "<critic/favorabil/neutru/none>", "intensity": "<explicit/implicit/none>", "signal_phrase": "<3-8 words from the article showing the stance, or none>", "rationale": "<one sentence or none>"}}

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


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def call_ollama(client: httpx.Client, prompt: str, num_predict: int = 200) -> str:
    response = client.post(
        OLLAMA_URL,
        json={
            "model":      OLLAMA_MODEL,
            "prompt":     prompt,
            "stream":     False,
            "keep_alive": "30m",
            "options":    {"temperature": 0.2, "num_predict": num_predict, "top_p": 1.0},
        },
        timeout=REQUEST_TIMEOUT,
    )
    return response.json().get("response", "")


def call_with_retry(client: httpx.Client, prompt: str, num_predict: int = 200) -> str:
    while True:
        try:
            return call_ollama(client, prompt, num_predict)
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
             article_id: int, axis: str, title: str,
             max_runs: int = 3, register_mode: bool = False):
    """
    Run up to max_runs LLM calls and return (result_dict, confidence, votes_list).
    result_dict is None if no majority was reached.
    register_mode: on disagreement, defaults to informativ/low instead of 3rd run.
    """
    votes    = []
    raw_list = []

    for run_idx in range(max_runs):
        raw  = call_with_retry(client, prompt)
        data = parse_json(raw)
        raw_list.append(raw)

        if data:
            value = extract_fn(data)
            if value in valid_values:
                votes.append((value, data))
            else:
                log_failure(axis, article_id, title, raw)
                votes.append((None, None))
        else:
            log_failure(axis, article_id, title, raw)
            votes.append((None, None))

        valid_votes = [v for v, _ in votes if v is not None]

        # After 2 runs: check agreement
        if len(votes) == 2:
            if len(valid_votes) == 2 and valid_votes[0] == valid_votes[1]:
                # Agreement on run 1+2
                winner_data = votes[0][1]
                log_rationale(article_id, axis, valid_votes[0],
                              winner_data.get('signal_phrase', ''),
                              winner_data.get('rationale', ''))
                return winner_data, 'high', [v for v, _ in votes]

            # Disagreement after 2 runs
            if register_mode:
                # Default to informativ, no 3rd run
                return {'register': 'informativ'}, 'low', [v for v, _ in votes]

            # Continue to 3rd run for other axes
            continue

        # After 3 runs: majority vote
        if len(votes) == 3:
            counts = defaultdict(list)
            for v, d in votes:
                if v is not None:
                    counts[v].append(d)

            majority = [(v, d_list) for v, d_list in counts.items() if len(d_list) >= 2]
            if majority:
                winner_val, winner_data_list = majority[0]
                winner_data = winner_data_list[0]
                log_rationale(article_id, axis, winner_val,
                              winner_data.get('signal_phrase', ''),
                              winner_data.get('rationale', ''))
                return winner_data, 'low', [v for v, _ in votes]

            # All 3 different — discard
            return None, None, [v for v, _ in votes]

    return None, None, [v for v, _ in votes]


# ── Database ──────────────────────────────────────────────────────────────────

MIGRATION_SQL = """
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_register          TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_register_conf     TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_register_votes    JSONB;

ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_stance            TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_stance_entity     TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_stance_intensity  TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_stance_conf       TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_stance_votes      JSONB;

ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_eu_orientation    TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_eu_conf           TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_eu_votes          JSONB;

ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_v4_scored_at      TIMESTAMPTZ;
"""

ARCHIVE_SQL = """
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_sovereignism_v2 TEXT;
UPDATE articles
SET llm_sovereignism_v2 = llm_sovereignism
WHERE llm_sovereignism IS NOT NULL
  AND llm_sovereignism_v2 IS NULL;
"""


def migrate(conn):
    cur = conn.cursor()
    cur.execute(ARCHIVE_SQL)
    cur.execute(MIGRATION_SQL)
    conn.commit()
    cur.close()
    log.info("Schema migration complete.")


def fetch_articles(conn, rescore: bool, axis: str) -> list[dict]:
    # For rescore: fetch all labeled articles on the target axis to reprocess them.
    # For initial run: fetch only articles not yet labeled on register (the first axis).
    if rescore:
        # Rescore fetches everything with a valid topic regardless of existing labels
        rescore_clause = ""
    elif axis in ('stance', 'eu'):
        # Non-rescore stance/eu runs: only fetch articles that already have a register label
        # (ensures we don't process articles the register pass hasn't reached yet)
        rescore_clause = "AND a.llm_register IS NOT NULL"
    else:
        # Default: register pass fetches only unlabeled articles
        rescore_clause = "AND a.llm_register IS NULL"

    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(f"""
        SELECT a.id, a.title, a.content_text, a.llm_topic, o.name AS outlet
        FROM articles a
        JOIN outlets o ON a.outlet_id = o.id
        WHERE a.llm_topic IS NOT NULL
          AND a.llm_topic != 'sports'
          AND NOT COALESCE(a.is_excluded, false)
          AND a.content_text IS NOT NULL
          AND LENGTH(a.content_text) >= 200
          {rescore_clause}
        ORDER BY a.id
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


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


def write_article(cur, article_id: int, fields: dict):
    if not fields:
        return
    set_parts = [f"{k} = %({k})s" for k in fields]
    set_parts.append("llm_v4_scored_at = NOW()")
    fields['id'] = article_id
    cur.execute(
        f"UPDATE articles SET {', '.join(set_parts)} WHERE id = %(id)s",
        fields,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PRISMA v4 LLM labeling")
    parser.add_argument("--dry-run",  action="store_true", help="No DB writes")
    parser.add_argument("--limit",    type=int, default=0, help="Cap number of articles")
    parser.add_argument("--rescore",  action="store_true", help="Re-label already scored articles")
    parser.add_argument("--axis",     choices=["register", "stance", "eu", "all"], default="all",
                        help="Which axis to label (default: all)")
    args = parser.parse_args()

    log.info("Checking Ollama...")
    wait_for_ollama()

    conn = psycopg2.connect(DB_URL)
    migrate(conn)

    articles = fetch_articles(conn, args.rescore, args.axis)
    if args.limit > 0:
        articles = articles[:args.limit]

    total        = len(articles)
    political    = sum(1 for a in articles if a['llm_topic'] in POLITICAL_TOPICS
                       and a['outlet'] not in FACTCHECKER_OUTLETS)
    eu_relevant  = sum(1 for a in articles if a['llm_topic'] in POLITICAL_TOPICS
                       and a['outlet'] not in FACTCHECKER_OUTLETS
                       and is_eu_relevant(a['title'], a['content_text']))

    log.info(f"Articles to label: {total:,}")
    log.info(f"  Register axis:      {total:,} (all)")
    log.info(f"  Stance axis:        {political:,} (political, non-fact-checker)")
    log.info(f"  EU orientation:     {eu_relevant:,} (political + EU keyword match)")

    stats = {
        'register':  defaultdict(int),
        'stance':    defaultdict(int),
        'eu':        defaultdict(int),
        'reg_skip':  0,
        'sta_skip':  0,
        'eu_skip':   0,
        'reg_low':   0,
        'sta_low':   0,
        'eu_low':    0,
    }

    cur    = conn.cursor()
    buf    = CommitBuffer(conn, COMMIT_BATCH_SIZE)
    client = httpx.Client()
    start  = time.time()

    for idx, article in enumerate(articles, 1):
        article_id = article['id']
        title      = article['title'] or ''
        content    = (article['content_text'] or '')[:MAX_CONTENT_CHARS]
        topic      = article['llm_topic']
        outlet     = article['outlet']
        is_political   = topic in POLITICAL_TOPICS and outlet not in FACTCHECKER_OUTLETS
        is_eu          = is_political and is_eu_relevant(title, article['content_text'])
        fields         = {}

        # ── Register ──────────────────────────────────────────────────────────
        if args.axis in ('register', 'all'):
            # Fact-check articles from fact-checker outlets: force investigativ
            # without spending an LLM call — their format is unambiguous
            if outlet in FACTCHECKER_OUTLETS and is_factcheck_article(title):
                fields['llm_register']       = 'investigativ'
                fields['llm_register_conf']  = 'high'
                fields['llm_register_votes'] = json.dumps(['forced_factcheck'])
                stats['register']['investigativ'] += 1
            else:
                prompt = REGISTER_PROMPT.format(title=title, content=content)
                result, conf, votes = run_vote(
                    client, prompt,
                    extract_fn    = lambda d: d.get('register', '').lower(),
                    valid_values  = {'informativ', 'opinie', 'investigativ', 'promotional'},
                    article_id    = article_id,
                    axis          = 'register',
                    title         = title,
                    max_runs      = 2,
                    register_mode = True,
                )
                if result:
                    reg_val = (result.get('register') or '').lower()
                    fields['llm_register']       = reg_val
                    fields['llm_register_conf']  = conf
                    fields['llm_register_votes'] = json.dumps(votes)
                    stats['register'][reg_val] += 1
                    if conf == 'low':
                        stats['reg_low'] += 1
                else:
                    stats['reg_skip'] += 1

        # ── Entity stance ─────────────────────────────────────────────────────
        if args.axis in ('stance', 'all') and is_political:
            prompt = STANCE_PROMPT.format(title=title, content=content)
            result, conf, votes = run_vote(
                client, prompt,
                extract_fn   = lambda d: d.get('stance', '').lower(),
                valid_values = {'critic', 'favorabil', 'neutru', 'none'},
                article_id   = article_id,
                axis         = 'stance',
                title        = title,
                max_runs     = 3,
            )
            if result:
                stance = (result.get('stance') or '').lower()
                entity = (result.get('entity') or '').lower()
                if stance and stance != 'none':
                    fields['llm_stance']           = stance
                    fields['llm_stance_entity']    = entity if entity != 'none' else None
                    fields['llm_stance_intensity'] = (result.get('intensity') or '').lower() \
                                                     or None
                    if fields['llm_stance_intensity'] == 'none':
                        fields['llm_stance_intensity'] = None
                    fields['llm_stance_conf']      = conf
                    fields['llm_stance_votes']     = json.dumps(votes)
                    stats['stance'][stance] += 1
                    if conf == 'low':
                        stats['sta_low'] += 1
            else:
                stats['sta_skip'] += 1

        # ── EU orientation ────────────────────────────────────────────────────
        if args.axis in ('eu', 'all') and is_eu:
            prompt = EU_PROMPT.format(title=title, content=content)
            result, conf, votes = run_vote(
                client, prompt,
                extract_fn   = lambda d: d.get('eu_orientation', '').lower(),
                valid_values = {'pro_european', 'suveranist', 'pragmatic'},
                article_id   = article_id,
                axis         = 'eu',
                title        = title,
                max_runs     = 3,
            )
            if result:
                eu_val = (result.get('eu_orientation') or '').lower()
                fields['llm_eu_orientation'] = eu_val
                fields['llm_eu_conf']        = conf
                fields['llm_eu_votes']       = json.dumps(votes)
                stats['eu'][eu_val] += 1
                if conf == 'low':
                    stats['eu_low'] += 1
            else:
                stats['eu_skip'] += 1

        # ── Write ─────────────────────────────────────────────────────────────
        if fields and not args.dry_run:
            write_article(cur, article_id, fields)
            buf.mark_write()

        # ── Progress ──────────────────────────────────────────────────────────
        if idx % 100 == 0:
            elapsed = time.time() - start
            rate    = idx / elapsed if elapsed > 0 else 0
            log.info(
                f"  {idx:,}/{total:,} ({rate:.1f} art/sec) | "
                f"reg={dict(stats['register'])} "
                f"sta={dict(stats['stance'])} "
                f"eu={dict(stats['eu'])} | "
                f"skips: reg={stats['reg_skip']} sta={stats['sta_skip']} eu={stats['eu_skip']}"
            )

    buf.flush()
    client.close()
    conn.close()

    elapsed = time.time() - start
    log.info(f"\nComplete. {total:,} articles in {elapsed/60:.1f} min.")
    log.info("\n── Register ──")
    for label, count in sorted(stats['register'].items(), key=lambda x: -x[1]):
        log.info(f"  {label:<15} {count:>6}  (low-conf: {stats['reg_low']})")
    log.info("\n── Stance ──")
    for label, count in sorted(stats['stance'].items(), key=lambda x: -x[1]):
        log.info(f"  {label:<15} {count:>6}  (low-conf: {stats['sta_low']})")
    log.info("\n── EU Orientation ──")
    for label, count in sorted(stats['eu'].items(), key=lambda x: -x[1]):
        log.info(f"  {label:<15} {count:>6}  (low-conf: {stats['eu_low']})")
    log.info(f"\n  Skipped (all-different votes): "
             f"reg={stats['reg_skip']} sta={stats['sta_skip']} eu={stats['eu_skip']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\nInterrupted. Committed batches are safe.")
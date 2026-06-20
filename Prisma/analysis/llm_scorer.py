import psycopg2
from pgvector.psycopg2 import register_vector
import httpx
import json
import time
import socket
import logging
from pathlib import Path
from collections import defaultdict
from env import DATABASE_URL, OLLAMA_BASE_URL
from urllib.parse import urlparse

DB_URL       = DATABASE_URL
OLLAMA_URL   = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_MODEL = "aya-expanse:8b"

MAX_CONTENT_CHARS = 1200
REQUEST_TIMEOUT   = 60.0
PROMPT_VERSION    = "v2_two_stage"

COMMIT_BATCH_SIZE = 10

OLLAMA_POLL_INTERVAL = 5
OLLAMA_MAX_WAIT_SECONDS = 300

OUTLET_TARGETS = {
    'Agerpres':              800,
    'Ziare':                 800,
    'Defapt.ro':             500,
    'Desteptarea':           700,
    'Monitorul de Botosani': 700,
    'Buletin de Bucuresti':  500,
    'Veridica':              350,
    'Argesul Online':        600,
    'PressOne':              500,
    'Gazeta de Sud':         500,
    'Factual':               350,
    'Arad24':                450,
}

POOL_MULTIPLIER = 2.0

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

FAILED_LOG     = Path(__file__).parent / "failed_articles.log"
RATIONALES_LOG = Path(__file__).parent / "rationales.log"

# ─────────────────────────────────────────────────────────────────
# Taxonomies.
# ─────────────────────────────────────────────────────────────────
NEWS_TOPICS = {
    'politics', 'economy', 'foreign_affairs', 'justice', 'health',
    'culture', 'social', 'environment', 'technology'
}

OUT_OF_SCOPE_TOPICS = {
    'religious_content', 'lifestyle_wellness', 'recipe_howto',
    'entertainment_celebrity', 'astrology_horoscope',
    'sports_routine', 'routine_bulletin', 'other_news'
}

ALL_VALID_TOPICS = NEWS_TOPICS | OUT_OF_SCOPE_TOPICS

VALID_GOV_STANCE = {
    'puternic_critic', 'moderat_critic', 'neutru',
    'moderat_favorabil', 'puternic_favorabil'
}
VALID_ANTI_ESTABLISHMENT = {'anti_institutional', 'neutru', 'pro_institutional'}
VALID_EU_ORIENTATION = {
    'puternic_eurosceptic', 'moderat_eurosceptic', 'neutru',
    'moderat_proeuropean', 'puternic_proeuropean'
}
VALID_SOVEREIGNISM = {'cadru_suveranist', 'neutru', 'cadru_integrationist'}
VALID_FRAMING = {
    'neutru', 'favorabil', 'critic', 'alarmist',
    'interes_uman', 'investigativ', 'promotional'
}
VALID_CONFIDENCE = {'high', 'low'}

# ─────────────────────────────────────────────────────────────────
# Prompt 1: topic classification only.
# ─────────────────────────────────────────────────────────────────
TOPIC_PROMPT = """\
You are a neutral academic media analyst classifying Romanian news articles by topic for a political/media-bias analysis project.

Respond with ONLY a valid JSON object:
{{"topic": "<str>", "confidence": "<str>"}}

TOPIC — choose exactly one. First check if the article is genuine, in-scope news of public interest (politics, governance, economy, justice, social issues, health policy, foreign affairs, environment, technology, culture WITH broader public-interest significance). If so, use one of:
  politics | economy | foreign_affairs | justice | health | culture | social | environment | technology

If the article is OUT OF SCOPE for political/media-bias analysis — religious observance content, generic lifestyle/wellness advice, recipes or how-to guides, celebrity gossip or entertainment without public-interest angle, horoscope/astrology, routine sports results with no broader context, routine administrative/procedural bulletins, or anything else outside the project scope — use one of:
  religious_content | lifestyle_wellness | recipe_howto | entertainment_celebrity | astrology_horoscope | sports_routine | routine_bulletin | other_news

OVERRIDE RULE: if an article is nominally about religion, health, sports, or lifestyle but contains real political, social, or public-interest significance (e.g. a religious leader commenting on legislation, a health minister scandal, a sports federation corruption case), classify it under the appropriate IN-SCOPE topic. When in doubt about genuine public significance, prefer the in-scope topic.

CONFIDENCE: "high" if classification was straightforward, "low" if ambiguous.

Title: {title}
Text: {content}\
"""

# ─────────────────────────────────────────────────────────────────
# Prompt 2: 5-axis bias scoring.
# ─────────────────────────────────────────────────────────────────
BIAS_PROMPT = """\
You are a neutral academic media analyst evaluating the LINGUISTIC TONE and FRAMING of a Romanian news article. Do NOT judge whether claims are true or false — only evaluate how the journalist frames the story.

Respond with ONLY a valid JSON object including a one-sentence "rationale" field that will be logged but not stored:
{{"gov_stance": "<str>", "anti_establishment": "<str>", "eu_orientation": "<str>", "sovereignism": "<str>", "framing": "<str>", "confidence": "<str>", "rationale": "<str>"}}

GOV_STANCE — editorial posture toward the current PSD+PNL+UDMR governing coalition expressed through framing choices, source selection, and tone (NOT through whether reported facts are negative):
  puternic_critic — aggressive negative framing, opposition voices quoted approvingly, emotional language
  moderat_critic — problems highlighted with skeptical tone but factual basis maintained
  neutru — balanced reporting with no discernible editorial lean, or topic unrelated to governance
  moderat_favorabil — achievements emphasized, optimistic framing, criticism minimized
  puternic_favorabil — uncritical praise, propagandistic tone

A factual article about a government failure is neutru if reporting is balanced. The classification is about framing, not about whether the news is good or bad for the government.

ANTI_ESTABLISHMENT — framing of Romanian state institutions (judiciary, intelligence services, parliament, regulatory bodies) as adversarial to citizens. Orthogonal to gov_stance — captures distrust of institutional power itself:
  anti_institutional — institutions framed as corrupt, captured, conspiratorial; "stat paralel"/"deep state" narratives sympathetically presented; judicial processes framed as political persecution
  neutru — institutions mentioned factually without editorial stance on their legitimacy
  pro_institutional — rule of law, judicial independence, institutional accountability framed as values

Criticizing a specific court ruling is not anti_institutional — it becomes so when criticism extends to the judiciary as a system.

EU_ORIENTATION — editorial framing of Romania's relationship with the EU and Euro-Atlantic structures:
  puternic_eurosceptic — EU framed as oppressive external force, Brussels "dictates" to Romania, anti-Western framing
  moderat_eurosceptic — specific EU policies criticized, sovereignty concerns, skeptical but not hostile
  neutru — EU mentioned factually or not at all
  moderat_proeuropean — EU membership framed as beneficial, European standards aspirational
  puternic_proeuropean — uncritical pro-EU framing, Brussels as solution to domestic problems

SOVEREIGNISM — whether the article frames issues through a national self-determination lens, independent of the EU dimension. Extends to energy ("independență energetică"), agriculture ("fermierul român"), foreign policy ("interese naționale"), cultural policy, defense:
  cadru_suveranist — national sovereignty, self-sufficiency, independence from external actors presented as primary values
  neutru — no sovereignty dimension, or balanced presentation
  cadru_integrationist — international cooperation, multilateralism, institutional alignment presented as natural

An article can be moderat_proeuropean on EU orientation while being cadru_suveranist on this axis (supporting EU membership but arguing Romania should assert more independence within the EU).

FRAMING — dominant editorial framing strategy:
  neutru — factual reporting without discernible editorial framing, inverted pyramid
  favorabil — positive framing, achievements/benefits emphasized
  critic — negative framing, problems/failures emphasized, accountability demanded
  alarmist — crisis framing, threat/urgency language, worst-case scenarios, emotional appeals to fear
  interes_uman — story framed through individual experience, emotional narrative arc
  investigativ — exposé framing, document-driven, accountability-focused, implies original reporting
  promotional — uncritical coverage reading like PR, event announcements with no critical perspective

IMPORTANT: All field values in your JSON response must use ONLY the Romanian labels listed above.
Do NOT use English equivalents such as "neutral", "supportive", or "critical" — use "neutru",
"favorabil", "critic" instead. Responding with any English label will be treated as a parse failure.

CONFIDENCE: "high" if classification was straightforward, "low" if ambiguous.
RATIONALE: one sentence explaining the key signal that drove the classification.

Title: {title}
Text: {content}\
"""


# ─────────────────────────────────────────────────────────────────
# Ollama connectivity guards.
# ─────────────────────────────────────────────────────────────────

def ollama_is_reachable(timeout=3.0):
    parsed = urlparse(OLLAMA_BASE_URL)
    host   = parsed.hostname
    port   = parsed.port or 11434
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_ollama(max_wait_seconds: int = OLLAMA_MAX_WAIT_SECONDS,
                     poll_interval: int = OLLAMA_POLL_INTERVAL):
    """
    Blocks until Ollama is reachable again, or exits the process after
    max_wait_seconds. Called both at startup and whenever a connection
    error is detected mid-run.
    """
    waited = 0
    while not ollama_is_reachable():
        if waited >= max_wait_seconds:
            logger.error(
                f"Ollama still unreachable after {max_wait_seconds}s. "
                f"Start it with 'ollama serve' (or relaunch the app) and "
                f"rerun this script — all progress so far is safely committed."
            )
            raise SystemExit(1)
        logger.warning(
            f"Ollama unreachable at {OLLAMA_BASE_URL}, "
            f"waiting {poll_interval}s before retry ({waited}s elapsed)..."
        )
        time.sleep(poll_interval)
        waited += poll_interval
    logger.info("Ollama is reachable.")


def call_ollama(client: httpx.Client, prompt: str, num_predict: int) -> str | None:
    """
    Returns the raw response text, or None if Ollama responded but the
    content was unusable. Raises httpx.ConnectError if Ollama itself
    is unreachable — callers are expected to catch that specifically
    and retry via wait_for_ollama() rather than treating it as a
    per-article content failure.
    """
    response = client.post(
        OLLAMA_URL,
        json={
            "model":   OLLAMA_MODEL,
            "prompt":  prompt,
            "stream":  False,
            "options": {
                "temperature": 0.0,
                "num_predict": num_predict,
                "top_p":       1.0,
            }
        },
        timeout=REQUEST_TIMEOUT,
    )
    return response.json().get('response', '')


def parse_json_response(raw: str) -> dict | None:
    if not raw:
        return None
    cleaned = raw.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    start, end = cleaned.find('{'), cleaned.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None


def classify_topic(client: httpx.Client, title: str, content: str) -> dict | None:
    """
    May raise httpx.ConnectError / httpx.TransportError if Ollama is
    unreachable — callers use the _with_retry wrapper below to handle
    that case rather than calling this directly.
    """
    truncated = (content or '')[:MAX_CONTENT_CHARS]
    raw = call_ollama(client, TOPIC_PROMPT.format(title=title, content=truncated), num_predict=80)
    data = parse_json_response(raw)
    if not data:
        return None
    if data.get('topic') not in ALL_VALID_TOPICS:
        return None
    if data.get('confidence') not in VALID_CONFIDENCE:
        data['confidence'] = 'low'
    return data


def score_bias(client: httpx.Client, title: str, content: str) -> dict | None:
    """Same connection-error contract as classify_topic above."""
    truncated = (content or '')[:MAX_CONTENT_CHARS]
    raw = call_ollama(client, BIAS_PROMPT.format(title=title, content=truncated), num_predict=250)
    data = parse_json_response(raw)
    if not data:
        return None
    required = {'gov_stance', 'anti_establishment', 'eu_orientation',
                'sovereignism', 'framing', 'confidence'}
    if not required.issubset(data.keys()):
        return None
    if data['gov_stance'] not in VALID_GOV_STANCE:                return None
    if data['anti_establishment'] not in VALID_ANTI_ESTABLISHMENT: return None
    if data['eu_orientation'] not in VALID_EU_ORIENTATION:        return None
    if data['sovereignism'] not in VALID_SOVEREIGNISM:            return None
    if data['framing'] not in VALID_FRAMING:                      return None
    if data['confidence'] not in VALID_CONFIDENCE:
        data['confidence'] = 'low'
    return data


def classify_topic_with_retry(client: httpx.Client, title: str, content: str) -> dict | None:
    """
    Wraps classify_topic with connection-outage handling. A connection
    error pauses and waits for Ollama to come back, then retries the
    SAME article — it never gets recorded as a content failure for an
    infrastructure problem. A content-level failure (bad JSON, invalid
    field) still returns None normally.
    """
    while True:
        try:
            return classify_topic(client, title, content)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            logger.warning(f"Lost connection to Ollama mid-run ({e}). Waiting for it to come back...")
            wait_for_ollama()


def score_bias_with_retry(client: httpx.Client, title: str, content: str) -> dict | None:
    """Same retry contract as classify_topic_with_retry, for the bias prompt."""
    while True:
        try:
            return score_bias(client, title, content)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            logger.warning(f"Lost connection to Ollama mid-run ({e}). Waiting for it to come back...")
            wait_for_ollama()


def get_already_labeled_count(cursor, outlet_name: str) -> int:
    """
    Source of truth for cross-restart quota tracking. Queries the
    database directly rather than trusting any in-memory counter,
    which resets to zero every time the process restarts.
    """
    cursor.execute("""
        SELECT COUNT(*)
        FROM articles a
        JOIN outlets o ON o.id = a.outlet_id
        WHERE o.name = %s
          AND a.llm_prompt_version = %s
          AND a.llm_gov_stance IS NOT NULL
    """, (outlet_name, PROMPT_VERSION))
    return cursor.fetchone()[0]


def fetch_pool_for_outlet(cursor, outlet_name: str, pool_size: int) -> list:
    """
    Restart-safe pool fetch: only pulls articles that have never been
    attempted (llm_scored_at IS NULL). Once an article gets
    llm_scored_at set — whether excluded, bias-scored, or bias-failed —
    it never reappears in this pool again, regardless of how many
    times the script restarts.
    """
    cursor.execute("""
        SELECT id, title, content_text
        FROM (
            SELECT a.id, a.title, a.content_text,
                   ROW_NUMBER() OVER (ORDER BY a.published_at ASC) AS rn,
                   COUNT(*) OVER () AS total
            FROM articles a
            JOIN outlets o ON o.id = a.outlet_id
            WHERE o.name = %s
              AND a.content_text IS NOT NULL
              AND a.llm_scored_at IS NULL
              AND LENGTH(a.content_text) >= 500
              AND NOT a.is_excluded
        ) ranked
        WHERE rn %% GREATEST(total / %s, 1) = 0
        LIMIT %s
    """, (outlet_name, pool_size, pool_size))
    return cursor.fetchall()


def materialize_exclusions(cursor):
    cursor.execute("""
        UPDATE articles a
        SET is_excluded = TRUE
        WHERE EXISTS (
            SELECT 1 FROM article_exclusions ae
            WHERE ae.article_id = a.id AND ae.confidence >= 0.8
        )
        AND NOT a.is_excluded
    """)
    logger.info(f"  is_excluded materialization: {cursor.rowcount} rows newly flagged")


def print_full_progress(cursor, outlet_targets: dict):
    """
    Queries the database directly for true cross-restart progress.
    Safe to call at any point — a handful of indexed COUNT queries.
    """
    logger.info("\n  --- Full progress (from database, all-time) ---")
    for outlet_name, target in outlet_targets.items():
        done = get_already_labeled_count(cursor, outlet_name)
        mark = "DONE" if done >= target else "    "
        logger.info(f"    [{mark}] {outlet_name:25s} {done:>4d} / {target:>4d}")


# ─────────────────────────────────────────────────────────────────
# Pending-write buffer.
# ─────────────────────────────────────────────────────────────────
class CommitBuffer:
    def __init__(self, conn, batch_size: int):
        self.conn = conn
        self.batch_size = batch_size
        self.pending = 0

    def mark_write(self):
        """Call after every cursor.execute() that writes to the DB."""
        self.pending += 1
        if self.pending >= self.batch_size:
            self.flush()

    def flush(self):
        if self.pending > 0:
            self.conn.commit()
            logger.debug(f"  committed batch of {self.pending}")
            self.pending = 0


def main():
    logger.info("Checking Ollama connectivity before starting...")
    wait_for_ollama()

    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    register_vector(conn)

    commit_buffer = CommitBuffer(conn, COMMIT_BATCH_SIZE)

    client = httpx.Client()
    start_time = time.time()

    stats = {
        'topic_processed': 0, 'topic_in_scope': 0,
        'topic_excluded': 0, 'topic_failed': 0,
        'bias_scored': 0, 'bias_failed': 0,
    }
    topic_distribution = defaultdict(int)

    logger.info("=== Starting run. Checking existing progress... ===")
    print_full_progress(cursor, OUTLET_TARGETS)

    for outlet_name, target in OUTLET_TARGETS.items():
        commit_buffer.flush()

        already_done = get_already_labeled_count(cursor, outlet_name)
        remaining = target - already_done

        logger.info(f"\n=== {outlet_name}: target={target}, already_done={already_done}, remaining={remaining} ===")

        if remaining <= 0:
            logger.info(f"  {outlet_name} already at target, skipping")
            continue

        pool_size = int(remaining * POOL_MULTIPLIER)
        pool = fetch_pool_for_outlet(cursor, outlet_name, pool_size)
        logger.info(f"  pool returned: {len(pool)} articles")

        if not pool:
            logger.warning(f"  no articles available for {outlet_name}, skipping")
            continue

        labeled_this_run = 0

        for article_id, title, content in pool:
            if already_done + labeled_this_run >= target:
                break

            topic_result = classify_topic_with_retry(client, title, content)
            stats['topic_processed'] += 1

            if topic_result is None:
                stats['topic_failed'] += 1
                cursor.execute("""
                    UPDATE articles
                    SET llm_scored_at = NOW(), llm_prompt_version = %s
                    WHERE id = %s
                """, (PROMPT_VERSION, article_id))
                commit_buffer.mark_write()
                with open(FAILED_LOG, 'a', encoding='utf-8') as f:
                    f.write(f"TOPIC_FAIL\t{article_id}\t{title[:100]}\n")
                continue

            topic = topic_result['topic']
            topic_confidence = topic_result['confidence']
            topic_distribution[topic] += 1

            if topic in OUT_OF_SCOPE_TOPICS:
                cursor.execute("""
                    UPDATE articles
                    SET llm_topic = %s, llm_confidence = %s,
                        llm_prompt_version = %s, llm_scored_at = NOW()
                    WHERE id = %s
                """, (topic, topic_confidence, PROMPT_VERSION, article_id))
                cursor.execute("""
                    INSERT INTO article_exclusions
                        (article_id, reason, method, confidence)
                    VALUES (%s, %s, 'llm_classifier', %s)
                    ON CONFLICT DO NOTHING
                """, (article_id, topic, 0.8))
                stats['topic_excluded'] += 1
                commit_buffer.mark_write()
                continue

            stats['topic_in_scope'] += 1

            bias_result = score_bias_with_retry(client, title, content)
            if bias_result is None:
                stats['bias_failed'] += 1
                cursor.execute("""
                    UPDATE articles
                    SET llm_topic = %s, llm_confidence = %s,
                        llm_prompt_version = %s, llm_scored_at = NOW()
                    WHERE id = %s
                """, (topic, topic_confidence, PROMPT_VERSION, article_id))
                commit_buffer.mark_write()
                with open(FAILED_LOG, 'a', encoding='utf-8') as f:
                    f.write(f"BIAS_FAIL\t{article_id}\t{title[:100]}\n")
                continue

            with open(RATIONALES_LOG, 'a', encoding='utf-8') as f:
                f.write(f"{article_id}\t{topic}\t{bias_result.get('rationale', '')}\n")
            bias_result.pop('rationale', None)

            cursor.execute("""
                UPDATE articles
                SET llm_topic               = %s,
                    llm_gov_stance          = %s,
                    llm_anti_establishment  = %s,
                    llm_eu_orientation      = %s,
                    llm_sovereignism        = %s,
                    llm_framing             = %s,
                    llm_confidence          = %s,
                    llm_prompt_version      = %s,
                    llm_scored_at           = NOW()
                WHERE id = %s
            """, (
                topic,
                bias_result['gov_stance'],
                bias_result['anti_establishment'],
                bias_result['eu_orientation'],
                bias_result['sovereignism'],
                bias_result['framing'],
                bias_result['confidence'],
                PROMPT_VERSION,
                article_id,
            ))
            commit_buffer.mark_write()
            stats['bias_scored'] += 1
            labeled_this_run += 1

            if stats['topic_processed'] % 50 == 0:
                elapsed = time.time() - start_time
                rate = stats['topic_processed'] / elapsed
                logger.info(
                    f"  [{outlet_name}] processed={stats['topic_processed']} "
                    f"in_scope={stats['topic_in_scope']} excluded={stats['topic_excluded']} "
                    f"bias_scored={stats['bias_scored']} bias_failed={stats['bias_failed']} "
                    f"({rate:.1f} art/sec)"
                )

        logger.info(f"  {outlet_name}: this run labeled {labeled_this_run}, "
                     f"total now {already_done + labeled_this_run}/{target}")

    commit_buffer.flush()

    materialize_exclusions(cursor)
    conn.commit()
    client.close()

    elapsed = time.time() - start_time
    logger.info(f"\n=== COMPLETE in {elapsed/60:.1f} min (this run) ===")
    logger.info(f"  This run — topic calls: {stats['topic_processed']}, "
                f"in_scope: {stats['topic_in_scope']}, excluded: {stats['topic_excluded']}, "
                f"topic_failed: {stats['topic_failed']}")
    logger.info(f"  This run — bias scored: {stats['bias_scored']}, "
                f"bias_failed: {stats['bias_failed']}")

    print_full_progress(cursor, OUTLET_TARGETS)

    logger.info(f"\n  Topic distribution (this run only):")
    for topic, count in sorted(topic_distribution.items(), key=lambda x: -x[1]):
        scope = "in-scope" if topic in NEWS_TOPICS else "out-of-scope"
        logger.info(f"    {topic:30s} {count:>5d}  ({scope})")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n\n=== Interrupted by user. ===")
        logger.info("Any in-flight Ollama request was abandoned — that single")
        logger.info("article will be retried automatically on the next run.")
        logger.info("All previously committed batches are safely persisted.")
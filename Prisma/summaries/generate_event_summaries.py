import os
import sys
import json
import time
import logging
from typing import Optional

import numpy as np
import psycopg2
import psycopg2.extras
import requests
from pgvector.psycopg2 import register_vector
from env import DATABASE_URL, OLLAMA_BASE_URL

# ── Config ────────────────────────────────────────────────────────────────────
DB_URL          = DATABASE_URL
OLLAMA_HOST     = OLLAMA_BASE_URL
MODEL           = os.environ.get("LLM_MODEL", "aya-expanse:8b")
K_ARTICLES      = 8
CHAR_LIMIT      = 800
MIN_COSINE      = 0.65
NUM_CTX         = 8192
TEMPERATURE     = 0.2
REQUEST_TIMEOUT = 180
MAX_LLM_RETRIES = 2        
PROMPT_VERSION  = "event_summary_v2"

OUTLET_TYPE_PRIORITY = [
    "investigative",
    "fact_checker",
    "regional_newspaper",
    "civic_news",
    "national_agency",
    "news_aggregator",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("event_summaries")


# ── Prompt ────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Ești un analist media neutru. Sarcina ta este să sintetizezi un eveniment de știri pe baza mai multor articole din presa românească.

Reguli de neutralitate:
- Evită formulări care presupun adevărul unei părți într-o dispută.
- Nu folosi etichete politice generice ("liberali", "social-democrați", "extremiști") decât dacă apar ca atribuire directă într-un articol.
- Nu repeta limbajul emoțional sau acuzator din articolele sursă; reformulează-l descriptiv ("partidul X a acuzat că ...").
- Atribuie clar afirmațiile contestate sursei lor.
- Nu adăuga informații care nu apar în articolele furnizate. Nu inventa cifre, date sau citate.
- Scrie la timpul trecut, în limbaj jurnalistic neutru.

Răspunde EXCLUSIV cu un obiect JSON valid cu această structură:
{
  "title": "<titlu neutru, sugestiv, maxim 10 cuvinte, în limba română>",
  "summary": "<rezumat neutru de 120-180 de cuvinte, în limba română>",
  "key_points": ["<punct cheie 1>", "<punct cheie 2>", "<punct cheie 3>", ...]
}

key_points trebuie să conțină între 3 și 5 enunțuri scurte, fiecare cu maxim 25 de cuvinte, fiecare descriind un fapt distinct.
Titlul trebuie să descrie evenimentul fără a favoriza nicio parte și fără limbaj senzaționalist."""


def build_user_prompt(k: int, date_from, date_to, articles_block: str) -> str:
    return (
        f"Mai jos sunt {k} articole despre un singur eveniment de știri "
        f"din perioada {date_from} – {date_to}. "
        f"Sintetizează evenimentul respectând regulile de neutralitate.\n\n"
        f"{articles_block}"
    )


# ── DB SQL ────────────────────────────────────────────────────────────────────
CANDIDATE_SQL = """
SELECT
    cl.cluster_id,
    cl.cluster_run_id,
    cl.article_count,
    cl.outlet_count,
    cl.date_from,
    cl.date_to,
    cl.label_text
FROM cluster_labels cl
WHERE cl.is_event_cluster = TRUE
  AND cl.cluster_run_id = (SELECT MAX(id) FROM cluster_runs)
  AND cl.outlet_count   >= 3
  AND cl.article_count  BETWEEN 4 AND 60
  AND (cl.date_to - cl.date_from) <= 7
  AND NOT EXISTS (
      SELECT 1 FROM cluster_summaries cs
      WHERE cs.scope = 'event'
        AND cs.cluster_run_id = cl.cluster_run_id
        AND cs.cluster_id     = cl.cluster_id
  )
ORDER BY cl.article_count DESC;
"""

MEMBERS_META_SQL = """
SELECT
    a.id,
    a.embedding,
    o.outlet_type
FROM articles a
JOIN outlets o ON o.id = a.outlet_id
WHERE a.sub_cluster_id  = %s
  AND a.cluster_run_id  = %s
  AND a.embedding IS NOT NULL
  AND a.content_text IS NOT NULL;
"""

ARTICLE_TEXTS_SQL = """
SELECT id, title, content_text
FROM articles
WHERE id = ANY(%s);
"""

INSERT_SQL = """
INSERT INTO cluster_summaries
    (scope, cluster_run_id, cluster_id, cluster_title, summary_text, key_points,
     source_article_ids, model, prompt_version,
     mean_pairwise_cosine, generation_ms)
VALUES ('event', %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
ON CONFLICT (scope, cluster_run_id, cluster_id) DO NOTHING;
"""


# ── Cluster diagnostics ──────────────────────────────────────────────────────
def mean_pairwise_cosine(embeddings: np.ndarray) -> float:
    n = embeddings.shape[0]
    if n < 2:
        return 0.0
    sim = embeddings @ embeddings.T   # L2-normalised inputs → cosine
    return float((sim.sum() - n) / (n * (n - 1)))


# ── Sampling ─────────────────────────────────────────────────────────────────
def stratified_sample(articles: list[dict], k: int) -> list[dict]:
    """Round 1: top-1 per outlet_type by priority. Round 2: fill by global cosine."""
    if len(articles) <= k:
        return articles

    embeddings = np.array([a["embedding"] for a in articles], dtype=np.float32)
    centroid = embeddings.mean(axis=0)
    centroid /= (np.linalg.norm(centroid) or 1.0)
    sims = embeddings @ centroid
    for i, a in enumerate(articles):
        a["_sim"] = float(sims[i])

    by_type: dict[str, list[dict]] = {}
    for a in articles:
        by_type.setdefault(a["outlet_type"] or "unknown", []).append(a)
    for lst in by_type.values():
        lst.sort(key=lambda x: x["_sim"], reverse=True)

    picked: list[dict] = []
    picked_ids: set[int] = set()

    for otype in OUTLET_TYPE_PRIORITY:
        bucket = by_type.get(otype)
        if bucket:
            top = bucket[0]
            picked.append(top)
            picked_ids.add(top["id"])
            if len(picked) >= k:
                return picked

    remaining = sorted(
        (a for a in articles if a["id"] not in picked_ids),
        key=lambda x: x["_sim"],
        reverse=True,
    )
    for a in remaining:
        if len(picked) >= k:
            break
        picked.append(a)

    return picked


def truncate_at_word_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_space = cut.rfind(" ")
    if last_space > limit * 0.7:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def build_articles_block(sampled: list[dict]) -> str:
    blocks = []
    for i, a in enumerate(sampled, start=1):
        title = (a["title"] or "").strip()
        text = truncate_at_word_boundary((a["content_text"] or "").strip(), CHAR_LIMIT)
        otype = a["outlet_type"] or "unknown"
        blocks.append(f"Articol {i} ({otype}): {title}\n{text}")
    return "\n\n".join(blocks)


# ── LLM call ─────────────────────────────────────────────────────────────────
def validate_schema(data) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "not an object"
    if not all(k in data for k in ("title", "summary", "key_points")):
        return False, "missing keys"
    if not isinstance(data["title"], str) or not data["title"].strip():
        return False, "title not a non-empty string"
    if len(data["title"].split()) > 15:
        return False, f"title too long ({len(data['title'].split())} words)"
    if not isinstance(data["summary"], str) or not data["summary"].strip():
        return False, "summary not a non-empty string"
    if not isinstance(data["key_points"], list):
        return False, "key_points not a list"
    if not (3 <= len(data["key_points"]) <= 5):
        return False, f"key_points length {len(data['key_points'])}"
    if not all(isinstance(p, str) and p.strip() for p in data["key_points"]):
        return False, "key_points contain non-strings or empty entries"
    wc = len(data["summary"].split())
    if not (80 <= wc <= 220):              # allow some slack around the 120-180 target
        return False, f"summary word count {wc} out of range"
    return True, "ok"


def call_ollama(user_prompt: str) -> tuple[Optional[dict], int]:
    """Returns (parsed_json or None, elapsed_ms_of_successful_call)."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": TEMPERATURE,
            "num_ctx": NUM_CTX,
        },
    }

    last_err = None
    for attempt in range(MAX_LLM_RETRIES + 1):
        start = time.monotonic()
        try:
            r = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            raw = r.json()["message"]["content"]
            data = json.loads(raw)
            ok, reason = validate_schema(data)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if ok:
                return data, elapsed_ms
            last_err = f"schema invalid ({reason})"
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            last_err = f"{type(e).__name__}: {e}"
        log.warning("LLM attempt %d/%d failed: %s", attempt + 1, MAX_LLM_RETRIES + 1, last_err)
        time.sleep(2)

    log.error("LLM exhausted retries: %s", last_err)
    return None, 0


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    conn = psycopg2.connect(DB_URL)
    register_vector(conn)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(CANDIDATE_SQL)
        candidates = cur.fetchall()

    log.info("Candidate event clusters: %d", len(candidates))
    if not candidates:
        log.info("Nothing to do.")
        return

    stats = {"ok": 0, "skip_cosine": 0, "skip_empty": 0, "skip_llm": 0}

    for idx, c in enumerate(candidates, start=1):
        cid, run_id = c["cluster_id"], c["cluster_run_id"]
        tag = f"[{idx}/{len(candidates)}] cluster_id={cid}"

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(MEMBERS_META_SQL, (cid, run_id))
            members_meta = [dict(m) for m in cur.fetchall()]

        if len(members_meta) < 4:
            log.info("%s skip: only %d valid articles", tag, len(members_meta))
            stats["skip_empty"] += 1
            continue

        embeddings = np.array([m["embedding"] for m in members_meta], dtype=np.float32)
        cohesion = mean_pairwise_cosine(embeddings)

        if cohesion < MIN_COSINE:
            log.info("%s skip: mean cosine %.3f < %.2f", tag, cohesion, MIN_COSINE)
            stats["skip_cosine"] += 1
            continue

        sampled_meta = stratified_sample(members_meta, K_ARTICLES)
        source_ids = [s["id"] for s in sampled_meta]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(ARTICLE_TEXTS_SQL, (source_ids,))
            texts_by_id = {r["id"]: dict(r) for r in cur.fetchall()}

        sampled = []
        for m in sampled_meta:
            tr = texts_by_id.get(m["id"])
            if tr is None:
                continue
            sampled.append({
                "id": m["id"],
                "title": tr["title"],
                "content_text": tr["content_text"],
                "outlet_type": m["outlet_type"],
            })

        if len(sampled) < 3:
            log.info("%s skip: only %d articles after text fetch", tag, len(sampled))
            stats["skip_empty"] += 1
            continue

        user_prompt = build_user_prompt(
            k=len(sampled),
            date_from=c["date_from"],
            date_to=c["date_to"],
            articles_block=build_articles_block(sampled),
        )

        result, elapsed_ms = call_ollama(user_prompt)
        if result is None:
            stats["skip_llm"] += 1
            continue

        with conn.cursor() as cur:
            cur.execute(INSERT_SQL, (
                run_id,
                cid,
                result["title"].strip(),
                result["summary"].strip(),
                json.dumps(result["key_points"], ensure_ascii=False),
                source_ids,
                MODEL,
                PROMPT_VERSION,
                round(cohesion, 4),
                elapsed_ms,
            ))
        conn.commit()
        stats["ok"] += 1
        log.info("%s ok: cohesion=%.3f, %d articles sampled, %d ms",
                 tag, cohesion, len(sampled), elapsed_ms)

    conn.close()
    log.info("Done. Stats: %s", stats)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        sys.exit(130)
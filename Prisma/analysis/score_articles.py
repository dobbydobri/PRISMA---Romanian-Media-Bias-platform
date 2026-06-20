import psycopg2
from pgvector.psycopg2 import register_vector
import re
import json
import time
from lexicons import (
    SENSATIONALIST_KEYWORDS,
    ATTRIBUTION_MARKERS,
    VAGUE_SOURCE_MARKERS,
    SPECULATION_MARKERS,
    DISCOURSE_REGISTERS,
    ALL_RHETORIC_TERMS,
)
from env import DATABASE_URL

DB_URL     = DATABASE_URL
BATCH_SIZE = 500


# ── Score 1: Title Sensationalism ─────────────────────────────────────────────

def score_sensationalism(title: str) -> float:
    if not title:
        return 0.0

    title_lower = title.lower()
    words       = title.split()

    punct     = title.count('!') + title.count('?')
    punct_s   = min(1.0, punct / 3)

    caps      = [w for w in words if w.isupper() and len(w) >= 5]
    caps_s    = min(1.0, len(caps) / 2)

    hits      = sum(1 for kw in SENSATIONALIST_KEYWORDS if kw in title_lower)
    kw_s      = min(1.0, hits / 2)

    listicle  = 1.0 if re.match(r'^\d+\s+\w+', title_lower) else 0.0

    length_s  = min(1.0, max(0.0, (len(words) - 8) / 12))

    return round(
        punct_s   * 0.25 +
        caps_s    * 0.20 +
        kw_s      * 0.30 +
        listicle  * 0.15 +
        length_s  * 0.10,
        4
    )


# ── Score 2: Citation Quality ─────────────────────────────────────────────────

def score_citation_quality(content: str) -> float:
    if not content or len(content) < 100:
        return 0.5  # neutral default for very short articles

    content_lower = content.lower()
    word_count    = max(len(content.split()), 1)

    attr_count = sum(content_lower.count(m) for m in ATTRIBUTION_MARKERS)
    vague_count = sum(content_lower.count(m) for m in VAGUE_SOURCE_MARKERS)
    spec_count = sum(content_lower.count(m) for m in SPECULATION_MARKERS)

    attr_d  = attr_count  / word_count * 1000
    vague_d = vague_count / word_count * 1000
    spec_d  = spec_count  / word_count * 1000

    quality = (
        min(1.0, attr_d  / 6)              * 0.55 +
        (1 - min(1.0, spec_d  / 3))        * 0.25 +
        (1 - min(1.0, vague_d / 3))        * 0.20
    )
    return round(quality, 4)


# ── Score 3: Rhetoric Intensity + Discourse Registers ─────────────────────────

def score_rhetoric(content: str) -> tuple[float, dict]:
    if not content or len(content) < 100:
        return 0.0, {}

    content_lower = content.lower()
    word_count    = max(len(content.split()), 1)

    register_scores = {}
    total_hits      = 0

    for register_name, keywords in DISCOURSE_REGISTERS.items():
        hits = sum(content_lower.count(kw.lower()) for kw in keywords)
        density = min(1.0, hits / word_count * 1000 / 3)
        register_scores[register_name] = round(density, 4)
        total_hits += hits

    intensity = min(1.0, total_hits / word_count * 1000 / 5)

    return round(intensity, 4), register_scores


# ── Batch processor ───────────────────────────────────────────────────────────

def process_batch(cursor, conn):
    cursor.execute("""
        SELECT id, title, content_text
        FROM articles
        WHERE score_sensationalism IS NULL
          AND content_text IS NOT NULL
        ORDER BY id
        LIMIT %s
    """, (BATCH_SIZE,))
    rows = cursor.fetchall()

    if not rows:
        return 0

    updates = []
    for article_id, title, content in rows:
        s_score = score_sensationalism(title)
        c_score = score_citation_quality(content)
        r_score, registers = score_rhetoric(content)

        updates.append((
            s_score,
            c_score,
            r_score,
            json.dumps(registers, ensure_ascii=False),
            article_id
        ))

    cursor.executemany("""
        UPDATE articles
        SET score_sensationalism    = %s,
            score_citation_quality  = %s,
            score_rhetoric_intensity = %s,
            discourse_registers     = %s
        WHERE id = %s
    """, updates)
    conn.commit()
    return len(rows)


def main():
    conn   = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    register_vector(conn)

    cursor.execute(
        "SELECT COUNT(*) FROM articles WHERE score_sensationalism IS NULL AND content_text IS NOT NULL"
    )
    total = cursor.fetchone()[0]
    print(f"[SCORING] {total:,} articles to score.\n")

    processed = 0
    start     = time.time()

    while True:
        batch_count = process_batch(cursor, conn)
        if batch_count == 0:
            break
        processed += batch_count
        elapsed = time.time() - start
        rate    = processed / elapsed if elapsed > 0 else 0
        print(f"  Scored {processed:,} / {total:,}  ({rate:.0f} articles/sec)")

    print(f"\n[SCORING] Complete. {processed:,} articles scored in {time.time()-start:.1f}s.")

    cursor.execute("""
        SELECT
            o.name,
            o.outlet_type,
            COUNT(*)                                           AS articles,
            ROUND(AVG(a.score_sensationalism)::numeric,    3)  AS avg_sensationalism,
            ROUND(AVG(a.score_citation_quality)::numeric,  3)  AS avg_citation,
            ROUND(AVG(a.score_rhetoric_intensity)::numeric, 3) AS avg_rhetoric
        FROM articles a
        JOIN outlets o ON a.outlet_id = o.id
        WHERE a.score_sensationalism IS NOT NULL
        GROUP BY o.name, o.outlet_type
        ORDER BY avg_sensationalism DESC
    """)

    print(f"\n{'Outlet':<25} {'Type':<20} {'N':>6}  "
          f"{'Sensational':>11}  {'Citation':>8}  {'Rhetoric':>8}")
    print("-" * 90)
    for row in cursor.fetchall():
        print(f"{row[0]:<25} {row[1]:<20} {row[2]:>6}  "
              f"{row[3]:>11}  {row[4]:>8}  {row[5]:>8}")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
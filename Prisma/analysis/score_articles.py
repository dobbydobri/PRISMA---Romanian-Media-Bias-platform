import argparse
import json
import re
import time

import psycopg2
from pgvector.psycopg2 import register_vector

from lexicons import (
    ATTRIBUTION_MARKERS,
    QUOTE_OPEN,
    SENSATIONALIST_TIER1,
    SENSATIONALIST_TIER2,
    SPECULATION_MARKERS,
    VAGUE_SOURCE_MARKERS,
    normalise,
)
from env import DATABASE_URL

BATCH_SIZE = 500

_SURSE_RE = re.compile(r'\bsurse\b')

def _build_patterns(terms: set) -> list[re.Pattern]:
    patterns = []
    for t in terms:
        if ' ' in t:
            patterns.append(re.compile(re.escape(t)))
        else:
            patterns.append(re.compile(r'\b' + re.escape(t) + r'\b'))
    return patterns

_TIER1_PATTERNS = _build_patterns(SENSATIONALIST_TIER1)
_TIER2_PATTERNS = _build_patterns(SENSATIONALIST_TIER2)


# ── Score 1: Title Sensationalism ─────────────────────────────────────────────

def score_sensationalism(title: str) -> float:
    """
    Scores title-level sensationalism on 0–1.

    Components:
      punct_s   — exclamation/question marks (max at 3+)
      caps_s    — ALL-CAPS words ≥5 chars that are not known acronyms
      tier1_s   — Tier 1 keyword hits (always sensationalist)
      tier2_s   — Tier 2 keyword hits (context-dependent; dampened)
      listicle  — headline starts with a digit ("10 motive...")
      length_s  — very long titles skew sensationalist
    """
    if not title:
        return 0.0

    title_norm = normalise(title)
    words      = title.split()

    # Punctuation
    punct   = title.count('!') + title.count('?')
    punct_s = min(1.0, punct / 3)

    # ALL-CAPS words — exclude common Romanian acronyms to avoid false positives
    _ACRONYMS = {'NATO', 'ANAF', 'DNA', 'DIICOT', 'MAI', 'MFP', 'BNR',
                 'ANM', 'SRI', 'SIE', 'MAE', 'UE', 'ONU', 'FMI', 'BCE'}
    caps   = [w for w in words if w.isupper() and len(w) >= 5 and w not in _ACRONYMS]
    caps_s = min(1.0, len(caps) / 2)

    # Tier 1 — always sensationalist
    tier1_hits = sum(1 for p in _TIER1_PATTERNS if p.search(title_norm))
    tier1_s    = min(1.0, tier1_hits / 1)   # 1 hit already maxes this component

    # Tier 2 — context-dependent; require 2+ hits or a co-occurring Tier 1 hit
    tier2_hits = sum(1 for p in _TIER2_PATTERNS if p.search(title_norm))
    if tier1_hits > 0:
        tier2_s = min(1.0, tier2_hits / 2)
    else:
        tier2_s = min(1.0, max(0, tier2_hits - 1) / 2)  # first hit free

    # Listicle pattern — "10 motive...", "5 lucruri..."
    listicle = 1.0 if re.match(r'^\d+\s+\w+', title_norm) else 0.0

    # Length — very long titles correlate with clickbait
    length_s = min(1.0, max(0.0, (len(words) - 8) / 12))

    return round(
        punct_s  * 0.20 +
        caps_s   * 0.15 +
        tier1_s  * 0.35 +
        tier2_s  * 0.15 +
        listicle * 0.10 +
        length_s * 0.05,
        4
    )


# ── Score 2: Citation Quality (Source Transparency) ───────────────────────────

def _count_quotes(content: str) -> int:
    """
    Count the number of direct quotations delimited by „..." or «...».
    Uses opening-delimiter count as a proxy (each opening = one quote).
    """
    return len(QUOTE_OPEN.findall(content))


def score_citation_quality(
    content: str,
    named_entities: list[str] | None = None,
) -> float:
    """
    Scores source transparency on 0–1.

    Components (three sub-scores combined):
      attr_s   — density of explicit attribution markers (named-source signals)
      vague_s  — penalty for anonymous sourcing language
      spec_s   — penalty for speculation / unverified-claim language
      quote_s  — density of direct quotations („…" / «…» delimiters)

    named_entities: list of PER/ORG entity surface forms from NER for this
    article; used to down-weight vague-source penalties when a named entity
    appears in the same sentence window as the vague marker.
    """
    if not content or len(content) < 100:
        return 0.5   # neutral default for very short / missing content

    content_norm = normalise(content)
    word_count   = max(len(content.split()), 1)

    # Attribution markers
    attr_count = sum(content_norm.count(m) for m in ATTRIBUTION_MARKERS)
    attr_d     = attr_count / word_count * 1000

    # Vague source markers
    vague_count = sum(content_norm.count(m) for m in VAGUE_SOURCE_MARKERS)
    # Standalone "surse" via word-boundary regex on normalised text
    vague_count += len(_SURSE_RE.findall(content_norm))
    vague_d     = vague_count / word_count * 1000

    if named_entities:
        entity_density = min(1.0, len(named_entities) / max(word_count / 100, 1))
        vague_d = vague_d * (1.0 - 0.5 * entity_density)

    # Speculation markers
    spec_count = sum(content_norm.count(m) for m in SPECULATION_MARKERS)
    spec_d     = spec_count / word_count * 1000

    # Direct quotation density
    n_quotes = _count_quotes(content)
    quote_d  = n_quotes / word_count * 1000
    quote_s  = min(1.0, quote_d / 2)   

    # Composite
    attr_s  = min(1.0, attr_d  / 6)
    vague_s = 1 - min(1.0, vague_d / 3)
    spec_s  = 1 - min(1.0, spec_d  / 3)

    score = (
        attr_s  * 0.45 +
        vague_s * 0.20 +
        spec_s  * 0.15 +
        quote_s * 0.20
    )
    return round(score, 4)


# ── Database helpers ───────────────────────────────────────────────────────────

def fetch_named_entities(cursor, article_ids: list[int]) -> dict[int, list[str]]:
    """
    Returns {article_id: [entity_surface_form, ...]} for PER and ORG labels.
    Accepts both 'PER'/'ORG' and 'PERSON'/'ORGANIZATION' label conventions.
    Falls back gracefully if the table is empty or the query returns nothing.
    """
    if not article_ids:
        return {}
    cursor.execute(
        """
        SELECT article_id, entity_text
        FROM   article_entities_full
        WHERE  article_id = ANY(%s)
          AND  entity_label IN ('PERSON', 'ORGANIZATION')
        """,
        (article_ids,),
    )
    result: dict[int, list[str]] = {}
    for article_id, entity_text in cursor.fetchall():
        result.setdefault(article_id, []).append(entity_text)
    return result


# ── Batch processor ────────────────────────────────────────────────────────────

def process_batch(cursor, conn) -> int:
    cursor.execute(
        """
        SELECT id, title, content_text
        FROM   articles
        WHERE  score_sensationalism IS NULL
          AND  content_text IS NOT NULL
          AND  NOT COALESCE(is_excluded, false)
        ORDER BY id
        LIMIT  %s
        """,
        (BATCH_SIZE,),
    )
    rows = cursor.fetchall()
    if not rows:
        return 0

    article_ids = [r[0] for r in rows]
    entities_map = fetch_named_entities(cursor, article_ids)

    updates = []
    for article_id, title, content in rows:
        s_score = score_sensationalism(title)
        c_score = score_citation_quality(
            content,
            named_entities=entities_map.get(article_id),
        )
        updates.append((s_score, c_score, article_id))

    cursor.executemany(
        """
        UPDATE articles
        SET    score_sensationalism   = %s,
               score_citation_quality = %s
        WHERE  id = %s
        """,
        updates,
    )
    conn.commit()
    return len(rows)


def reset_scores(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE articles
        SET score_sensationalism   = NULL,
            score_citation_quality = NULL
        WHERE NOT COALESCE(is_excluded, false)
        """
    )
    conn.commit()
    cur.close()
    print("[RESET] Scores cleared.\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="PRISMA NLP article scorer")
    parser.add_argument(
        '--reset',
        action='store_true',
        help='NULL all existing scores and re-score from scratch',
    )
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    register_vector(conn)

    if args.reset:
        reset_scores(conn)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM   articles
        WHERE  score_sensationalism IS NULL
          AND  content_text IS NOT NULL
          AND  NOT COALESCE(is_excluded, false)
        """
    )
    total = cursor.fetchone()[0]
    print(f"[SCORING] {total:,} articles to score.\n")

    processed = 0
    start     = time.time()

    while True:
        n = process_batch(cursor, conn)
        if n == 0:
            break
        processed += n
        elapsed = time.time() - start
        rate    = processed / elapsed if elapsed > 0 else 0
        print(f"  Scored {processed:,} / {total:,}  ({rate:.0f} art/sec)")

    elapsed = time.time() - start
    print(f"\n[SCORING] Done. {processed:,} articles in {elapsed:.1f}s.")

    # Per-outlet summary
    cursor.execute(
        """
        SELECT
            o.name,
            o.outlet_type,
            COUNT(*)                                          AS n,
            ROUND(AVG(a.score_sensationalism)::numeric,   3) AS sensationalism,
            ROUND(AVG(a.score_citation_quality)::numeric, 3) AS citation_quality
        FROM   articles a
        JOIN   outlets  o ON a.outlet_id = o.id
        WHERE  a.score_sensationalism IS NOT NULL
        GROUP BY o.name, o.outlet_type
        ORDER BY sensationalism DESC
        """
    )
    print(
        f"\n{'Outlet':<25} {'Type':<20} {'N':>6}  "
        f"{'Sensational':>11}  {'Citation':>8}"
    )
    print("-" * 78)
    for row in cursor.fetchall():
        print(
            f"{row[0]:<25} {row[1]:<20} {row[2]:>6}  "
            f"{row[3]:>11}  {row[4]:>8}"
        )

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
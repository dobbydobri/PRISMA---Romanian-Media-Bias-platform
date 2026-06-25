import os
import sys
import time
import logging
import math
import psycopg2
from psycopg2.extras import execute_values
import networkx as nx
from collections import defaultdict
from entity_normalizer import build_canonical_map
from env import DATABASE_URL

DB_URL = DATABASE_URL

MIN_RAW_COMENTIONS = int(os.getenv("MIN_RAW_COMENTIONS", "5"))
MIN_PMI            = float(os.getenv("MIN_PMI", "0.0"))

BYLINE_ENTROPY_THRESHOLD = float(os.getenv("BYLINE_ENTROPY_THRESHOLD", "0.3"))

ALLOWED_LABELS = {"PERSON", "ORGANIZATION", "GPE", "LOC", "EVENT"}

_WIRE_SERVICE_BLACKLIST: frozenset[str] = frozenset({
    "reuters",
    "afp",
    "ap",
    "associated press",
    "mediafax",
    "agerpres",
})
_KNOWN_BYLINES: frozenset[str] = frozenset({
    "simonă aruștei",
    "mihai țenea",
    "andreea preda",
    "alexandru cojocaru",
    "ady ivașcu",
    "vlad constantinescu",
    "ionuț mareș",
    "răzvan chiruță",
    "florin ștefan",
})

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# ── Schema ─────────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS entity_connections (
    id               SERIAL PRIMARY KEY,
    source_entity    VARCHAR(255) NOT NULL,
    source_label     VARCHAR(50)  NOT NULL,
    target_entity    VARCHAR(255) NOT NULL,
    target_label     VARCHAR(50)  NOT NULL,
    weight_raw       INTEGER      NOT NULL,
    weight_pmi       FLOAT        NOT NULL,
    UNIQUE(source_entity, target_entity)
);

CREATE INDEX IF NOT EXISTS idx_entity_connections_source
    ON entity_connections(source_entity);

CREATE INDEX IF NOT EXISTS idx_entity_connections_target
    ON entity_connections(target_entity);

CREATE INDEX IF NOT EXISTS idx_entity_connections_pmi
    ON entity_connections(weight_pmi DESC);
"""


# ── Byline entropy ─────────────────────────────────────────────────────────────

def compute_outlet_entropy(
    entity: str,
    entity_outlets: dict[str, list[str]],
) -> float:
    """
    Compute Shannon entropy of outlet distribution for an entity.

    H(entity) = -Σ P(outlet|entity) × log₂(P(outlet|entity))

    Returns:
        0.0 = all mentions from one outlet (likely byline)
        log₂(N_outlets) = uniform across all outlets (definitely public figure)

    Only applied to PERSON entities. Organisations, locations, and events
    can legitimately appear in only one regional outlet.
    """
    outlets = entity_outlets.get(entity, [])
    if not outlets:
        return 0.0

    total = len(outlets)
    counts: dict[str, int] = defaultdict(int)
    for o in outlets:
        counts[o] += 1

    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    return entropy


# ── Data loading ───────────────────────────────────────────────────────────────

def load_entity_data(conn):
    logger.info("Loading entity data from article_entities_full...")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            aef.article_id,
            aef.entity_text,
            aef.entity_label,
            o.name AS outlet_name
        FROM article_entities_full aef
        JOIN articles a ON a.id = aef.article_id
        JOIN outlets  o ON o.id = a.outlet_id
        WHERE aef.entity_label = ANY(%s)
        ORDER BY aef.article_id;
    """, (list(ALLOWED_LABELS),))

    rows = cursor.fetchall()
    cursor.close()
    logger.info(f"Loaded {len(rows):,} entity rows.")

    canonical_map = build_canonical_map(row[1] for row in rows)

    entity_articles: dict[str, set] = defaultdict(set)
    entity_label_counts: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    article_entities: dict[int, set] = defaultdict(set)
    entity_outlets: dict[str, list[str]] = defaultdict(list)

    for article_id, entity_text, entity_label, outlet_name in rows:
        canonical = canonical_map.get(entity_text)
        if not canonical:  
            continue

        if canonical.lower() in _WIRE_SERVICE_BLACKLIST:
            continue
        if canonical.lower() in _KNOWN_BYLINES:
            continue

        entity_articles[canonical].add(article_id)
        entity_label_counts[canonical][entity_label] += 1
        article_entities[article_id].add(canonical)

        if entity_label == 'PERSON':
            entity_outlets[canonical].append(outlet_name)

    entity_labels = {
        entity: max(label_counts, key=label_counts.get)
        for entity, label_counts in entity_label_counts.items()
    }

    byline_filtered = 0
    persons_to_remove = []
    for entity, label in entity_labels.items():
        if label != 'PERSON':
            continue
        h = compute_outlet_entropy(entity, entity_outlets)
        if h < BYLINE_ENTROPY_THRESHOLD:
            persons_to_remove.append(entity)

    for entity in persons_to_remove:
        article_ids_for_entity = entity_articles.pop(entity, set())
        entity_labels.pop(entity, None)
        entity_outlets.pop(entity, None)
        for a_id in article_ids_for_entity:
            article_entities[a_id].discard(entity)
        byline_filtered += 1

    wire_filtered = sum(
        1 for row in rows
        if canonical_map.get(row[1], '').lower() in _WIRE_SERVICE_BLACKLIST
    )

    logger.info(
        f"Canonical entities: {len(entity_articles):,} | "
        f"Articles with entities: {len(article_entities):,} | "
        f"Wire-service entities filtered: {wire_filtered:,} rows | "
        f"Byline PERSON entities filtered (H < {BYLINE_ENTROPY_THRESHOLD}): {byline_filtered:,}"
    )
    return entity_articles, entity_labels, article_entities


# ── PMI computation ────────────────────────────────────────────────────────────

def compute_pmi(
    entity_a: str,
    entity_b: str,
    entity_articles: dict,
    pair_articles: dict,
    total_articles: int
) -> float:
    p_a  = len(entity_articles[entity_a]) / total_articles
    p_b  = len(entity_articles[entity_b]) / total_articles
    p_ab = len(pair_articles.get((entity_a, entity_b), set())) / total_articles

    if p_ab == 0:
        return float('-inf')

    return math.log(p_ab / (p_a * p_b))


# ── Edge construction ──────────────────────────────────────────────────────────

def build_edges(entity_articles, entity_labels, article_entities, total_articles):
    logger.info("Computing co-mention pairs...")

    pair_articles: dict[tuple, set] = defaultdict(set)

    for article_id, entities in article_entities.items():
        entity_list = sorted(entities) 
        for i in range(len(entity_list)):
            for j in range(i + 1, len(entity_list)):
                pair = (entity_list[i], entity_list[j])
                pair_articles[pair].add(article_id)

    logger.info(f"Raw co-mention pairs found: {len(pair_articles):,}")

    edges = []
    skipped_raw = 0
    skipped_pmi = 0

    for (entity_a, entity_b), article_set in pair_articles.items():
        raw_count = len(article_set)

        if raw_count < MIN_RAW_COMENTIONS:
            skipped_raw += 1
            continue

        pmi = compute_pmi(entity_a, entity_b, entity_articles, pair_articles, total_articles)
        if pmi <= MIN_PMI:
            skipped_pmi += 1
            continue

        edges.append({
            "source_entity": entity_a,
            "source_label":  entity_labels.get(entity_a, "UNKNOWN"),
            "target_entity": entity_b,
            "target_label":  entity_labels.get(entity_b, "UNKNOWN"),
            "weight_raw":    raw_count,
            "weight_pmi":    round(pmi, 6),
        })

    logger.info(
        f"Edges after filtering: {len(edges):,} | "
        f"Skipped (low frequency): {skipped_raw:,} | "
        f"Skipped (low PMI): {skipped_pmi:,}"
    )
    return edges


# ── NetworkX validation ────────────────────────────────────────────────────────

def validate_graph(edges):
    logger.info("Validating graph topology with NetworkX...")
    G = nx.Graph()
    for e in edges:
        G.add_edge(
            e["source_entity"],
            e["target_entity"],
            weight=e["weight_pmi"]
        )

    components = nx.number_connected_components(G)
    largest    = len(max(nx.connected_components(G), key=len))

    logger.info(
        f"Graph stats — Nodes: {G.number_of_nodes():,} | "
        f"Edges: {G.number_of_edges():,} | "
        f"Connected components: {components:,} | "
        f"Largest component: {largest:,} nodes"
    )
    return G


# ── Database write ─────────────────────────────────────────────────────────────

def write_to_database(conn, edges):
    logger.info(f"Writing {len(edges):,} edges to entity_connections...")
    cursor = conn.cursor()

    try:
        cursor.execute("TRUNCATE TABLE entity_connections RESTART IDENTITY;")

        insert_rows = [
            (
                e["source_entity"], e["source_label"],
                e["target_entity"], e["target_label"],
                e["weight_raw"],    e["weight_pmi"]
            )
            for e in edges
        ]

        execute_values(cursor, """
            INSERT INTO entity_connections
                (source_entity, source_label, target_entity, target_label, weight_raw, weight_pmi)
            VALUES %s
            ON CONFLICT (source_entity, target_entity) DO UPDATE SET
                weight_raw  = EXCLUDED.weight_raw,
                weight_pmi  = EXCLUDED.weight_pmi,
                source_label = EXCLUDED.source_label,
                target_label = EXCLUDED.target_label;
        """, insert_rows, page_size=1000)

        conn.commit()
        logger.info("✓ entity_connections table successfully updated.")

    except Exception as e:
        conn.rollback()
        logger.error(f"Database write failed, rolled back: {e}")
        raise
    finally:
        cursor.close()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    start = time.time()

    logger.info("graph_builder.py starting...")
    logger.info(
        f"Thresholds — MIN_RAW_COMENTIONS: {MIN_RAW_COMENTIONS} | "
        f"MIN_PMI: {MIN_PMI} | "
        f"BYLINE_ENTROPY_THRESHOLD: {BYLINE_ENTROPY_THRESHOLD}"
    )

    try:
        conn = psycopg2.connect(DB_URL)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)

    cursor = conn.cursor()

    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    cursor.close()

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM articles WHERE content_text IS NOT NULL;")
    total_articles = cursor.fetchone()[0]
    cursor.close()
    logger.info(f"Total articles in corpus: {total_articles:,}")

    if total_articles == 0:
        logger.error("No articles found. Exiting.")
        sys.exit(1)

    entity_articles, entity_labels, article_entities = load_entity_data(conn)
    edges = build_edges(entity_articles, entity_labels, article_entities, total_articles)

    if not edges:
        logger.warning("No edges passed the filters. Check MIN_RAW_COMENTIONS and MIN_PMI settings.")
        sys.exit(0)

    validate_graph(edges)
    write_to_database(conn, edges)

    conn.close()
    logger.info(f"graph_builder.py completed in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()

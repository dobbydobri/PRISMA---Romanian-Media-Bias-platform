import json
import math
import os
import sys
import logging
from collections import Counter

import psycopg2
import psycopg2.extras

from env import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_URL = DATABASE_URL
CLUSTER_RUN_ID = os.environ.get("CLUSTER_RUN_ID")  # None = latest
P_MIN = float(os.environ.get("P_MIN", "3.0"))

PARTICIPATING_OUTLETS = [
    "Arad24",
    "Argesul Online",
    "Buletin de Bucuresti",
    "Desteptarea",
    "Monitorul de Botosani",
    "PressOne",
    "Ziare",
]
MAX_OUTLETS = len(PARTICIPATING_OUTLETS)  

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

SQL_LATEST_RUN = """
    SELECT cr.id
    FROM cluster_runs cr
    JOIN cluster_labels cl ON cl.cluster_run_id = cr.id AND cl.is_event_cluster = TRUE
    GROUP BY cr.id
    ORDER BY cr.id DESC
    LIMIT 1;
"""

SQL_EVENT_CLUSTERS = """
    SELECT
        cl.cluster_run_id,
        cl.cluster_id,
        cl.article_count,
        ARRAY_AGG(DISTINCT o.name)
            FILTER (WHERE o.outlet_type != 'national_agency') AS covering_outlets,
        COUNT(DISTINCT o.id)
            FILTER (WHERE o.outlet_type != 'national_agency') AS outlet_count,
        COUNT(DISTINCT o.outlet_type)
            FILTER (WHERE o.outlet_type != 'national_agency') AS outlet_type_count
    FROM cluster_labels cl
    JOIN articles a
        ON a.cluster_run_id = cl.cluster_run_id
       AND a.sub_cluster_id = cl.cluster_id
    JOIN outlets o
        ON o.id = a.outlet_id
    WHERE cl.cluster_run_id = %s
      AND cl.is_event_cluster = TRUE
    GROUP BY cl.cluster_run_id, cl.cluster_id, cl.article_count;
"""

SQL_TOPICS_FOR_CLUSTERS = """
    SELECT
        a.sub_cluster_id AS cluster_id,
        a.llm_topic
    FROM articles a
    WHERE a.cluster_run_id = %s
      AND a.sub_cluster_id IS NOT NULL
      AND a.llm_topic IS NOT NULL;
"""

SQL_TRUNCATE = """
    DELETE FROM cluster_coverage_metrics WHERE cluster_run_id = %s;
"""

SQL_INSERT = """
    INSERT INTO cluster_coverage_metrics
        (cluster_run_id, cluster_id, article_count, outlet_count,
         outlet_type_count, popularity_score, gap_score,
         category, covering_outlets, missing_outlets)
    VALUES %s
    ON CONFLICT (cluster_run_id, cluster_id) DO UPDATE SET
        article_count     = EXCLUDED.article_count,
        outlet_count      = EXCLUDED.outlet_count,
        outlet_type_count = EXCLUDED.outlet_type_count,
        popularity_score  = EXCLUDED.popularity_score,
        gap_score         = EXCLUDED.gap_score,
        category          = EXCLUDED.category,
        covering_outlets  = EXCLUDED.covering_outlets,
        missing_outlets   = EXCLUDED.missing_outlets,
        computed_at       = now();
"""


def resolve_run_id(cur) -> int:
    """Get the cluster_run_id to process."""
    if CLUSTER_RUN_ID is not None:
        return int(CLUSTER_RUN_ID)
    cur.execute(SQL_LATEST_RUN)
    row = cur.fetchone()
    if row is None:
        log.error("No event-cluster runs found.")
        sys.exit(1)
    return row[0]


def build_category_map(cur, run_id: int) -> dict[int, str]:
    """
    For each event cluster, derive category from the modal llm_topic
    across member articles. Returns {cluster_id: category_string}.
    """
    cur.execute(SQL_TOPICS_FOR_CLUSTERS, (run_id,))
    cluster_topics: dict[int, list[str]] = {}
    for cluster_id, topic in cur:
        cluster_topics.setdefault(cluster_id, []).append(topic)

    category_map = {}
    for cluster_id, topics in cluster_topics.items():
        counts = Counter(topics)
        top_two = counts.most_common(2)
        if len(top_two) == 1:
            category_map[cluster_id] = top_two[0][0]
        elif top_two[0][1] > top_two[1][1]:
            category_map[cluster_id] = top_two[0][0]
        else:
            category_map[cluster_id] = f"{top_two[0][0]} / {top_two[1][0]}"

    return category_map


def compute_missing_outlets(covering: list[str]) -> list[str]:
    """Diff covering outlets against the known participating set."""
    covering_set = set(covering) if covering else set()
    return sorted(set(PARTICIPATING_OUTLETS) - covering_set)


def main():
    log.info("Connecting to database...")
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        run_id = resolve_run_id(cur)
        log.info(f"Processing cluster_run_id = {run_id}")
        log.info(f"P_MIN = {P_MIN}, MAX_OUTLETS = {MAX_OUTLETS}")

        log.info("Building category map from llm_topic...")
        category_map = build_category_map(cur, run_id)
        log.info(f"  Categories derived for {len(category_map)} clusters")

        log.info("Fetching event cluster statistics...")
        cur.execute(SQL_EVENT_CLUSTERS, (run_id,))
        rows = cur.fetchall()
        log.info(f"  Found {len(rows)} event clusters")

        results = []
        skipped_low_pop = 0
        skipped_zero_outlets = 0

        for (c_run_id, c_id, article_count,
             covering_outlets, outlet_count, outlet_type_count) in rows:

            if outlet_count == 0 or outlet_type_count == 0:
                skipped_zero_outlets += 1
                continue

            popularity_score = math.log(1 + article_count) * outlet_type_count

            if popularity_score < P_MIN:
                skipped_low_pop += 1
                continue

            gap_score = popularity_score * (1.0 - outlet_count / MAX_OUTLETS)

            covering = covering_outlets if covering_outlets else []
            missing = compute_missing_outlets(covering)
            category = category_map.get(c_id)

            results.append((
                c_run_id,
                c_id,
                article_count,
                outlet_count,
                outlet_type_count,
                round(popularity_score, 4),
                round(gap_score, 4),
                category,
                json.dumps(covering, ensure_ascii=False),
                json.dumps(missing, ensure_ascii=False),
            ))

        log.info(f"  Passed P_MIN filter: {len(results)}")
        log.info(f"  Skipped (low popularity): {skipped_low_pop}")
        log.info(f"  Skipped (zero non-agency outlets): {skipped_zero_outlets}")

        log.info("Writing to cluster_coverage_metrics...")
        cur.execute(SQL_TRUNCATE, (run_id,))
        if results:
            psycopg2.extras.execute_values(
                cur, SQL_INSERT, results,
                template=(
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)"
                ),
                page_size=500,
            )
        conn.commit()
        log.info(f"  Wrote {len(results)} rows for run_id={run_id}")

        if results:
            gap_scores = [r[6] for r in results]
            gap_scores.sort(reverse=True)
            log.info(f"  Gap score range: {gap_scores[-1]:.2f} – {gap_scores[0]:.2f}")
            log.info(f"  Top-5 gap scores: {[f'{g:.2f}' for g in gap_scores[:5]]}")

    except Exception:
        conn.rollback()
        log.exception("Pipeline failed, transaction rolled back.")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

    log.info("Done.")


if __name__ == "__main__":
    main()
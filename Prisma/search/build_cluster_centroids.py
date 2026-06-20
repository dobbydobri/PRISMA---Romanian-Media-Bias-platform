from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Optional

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
from env import DATABASE_URL

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_URL_DEFAULT = DATABASE_URL
MIN_MEMBERS    = int(os.getenv("MIN_MEMBERS", "1"))
COMMIT_EVERY   = int(os.getenv("COMMIT_EVERY", "500"))
LOG_EVERY      = int(os.getenv("LOG_EVERY", "100"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("centroid_backfill")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def l2_normalize(v: np.ndarray) -> np.ndarray:
    """L2-normalize a 1-D array. Zero vectors stay zero (no division by zero)."""
    n = float(np.linalg.norm(v))
    return (v / n).astype(np.float32) if n > 0.0 else v.astype(np.float32)


def _aggregate(cur, run_id: Optional[int], membership_col: str) -> list[tuple]:
    where_extra = ""
    params: list = []
    if run_id is not None:
        where_extra = "AND a.cluster_run_id = %s"
        params.append(run_id)

    sql = f"""
        SELECT
            a.cluster_run_id,
            a.{membership_col} AS cluster_id,
            AVG(a.embedding)   AS mean_embedding,
            COUNT(*)           AS n_members
        FROM   articles a
        WHERE  a.embedding IS NOT NULL
          AND  NOT a.is_templated
          AND  a.{membership_col} IS NOT NULL
          AND  a.{membership_col} >= 0
          {where_extra}
        GROUP  BY a.cluster_run_id, a.{membership_col}
        HAVING COUNT(*) >= %s
        ORDER  BY a.cluster_run_id, a.{membership_col}
    """
    cur.execute(sql, params + [MIN_MEMBERS])
    return cur.fetchall()


def aggregate_topical_means(cur, run_id: Optional[int]) -> list[tuple]:
    """Aggregate topical (HDBSCAN) clusters via articles.cluster_id."""
    return _aggregate(cur, run_id, "cluster_id")


def aggregate_event_means(cur, run_id: Optional[int]) -> list[tuple]:
    """Aggregate event (TDT) clusters via articles.sub_cluster_id."""
    return _aggregate(cur, run_id, "sub_cluster_id")


def report_final_state(cur, run_id: Optional[int]) -> None:
    """Log how many clusters in cluster_labels now have a centroid vs not."""
    where_extra = "WHERE cluster_run_id = %s" if run_id is not None else ""
    params: list = [run_id] if run_id is not None else []

    cur.execute(f"""
        SELECT COUNT(*)                   AS total,
               COUNT(centroid)            AS with_centroid,
               COUNT(*) - COUNT(centroid) AS missing
        FROM   cluster_labels
        {where_extra}
    """, params)
    total, with_c, missing = cur.fetchone()

    scope = f" (run_id={run_id})" if run_id is not None else ""
    log.info("Final state%s: total=%d, with_centroid=%d, missing=%d",
             scope, total, with_c, missing)

    if missing > 0:
        cur.execute(f"""
            SELECT cluster_run_id, cluster_id, article_count
            FROM   cluster_labels
            WHERE  centroid IS NULL
            {('AND cluster_run_id = %s' if run_id is not None else '')}
            ORDER  BY article_count DESC NULLS LAST
            LIMIT  10
        """, params)
        rows = cur.fetchall()
        if rows:
            log.info("Top missing-centroid clusters by article_count:")
            for cr, cid, ac in rows:
                log.info("  run_id=%s cluster_id=%s article_count=%s", cr, cid, ac)
            log.info("These are likely all-templated or all-embeddings-missing clusters.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _process_scope(
    cur,
    conn,
    rows: list[tuple],
    scope_label: str,
    is_event_cluster: bool,
    dry_run: bool,
) -> int:
    """
    Normalize and (if not dry-run) UPDATE cluster_labels for a single scope.
    Returns the number of rows written (0 in dry-run mode).
    """
    if not rows:
        log.info("[%s] No clusters to process.", scope_label)
        return 0

    log.info("[%s] Normalizing and writing %d centroid(s)%s...",
             scope_label, len(rows), " (dry-run)" if dry_run else "")
    t0 = time.perf_counter()
    writes = 0
    sample_logged = 0

    for i, (run_id, cluster_id, mean_emb, n_members) in enumerate(rows, start=1):
        if mean_emb is None:
            log.warning("[%s] Cluster (%s, %s): AVG returned NULL on %d rows, skipping",
                        scope_label, run_id, cluster_id, n_members)
            continue

        vec = np.asarray(mean_emb, dtype=np.float32)
        centroid = l2_normalize(vec)

        if dry_run:
            if sample_logged < 3:
                log.info("[%s] (dry) run_id=%s cluster_id=%s n=%d  pre=%.4f post=%.4f",
                         scope_label, run_id, cluster_id, n_members,
                         float(np.linalg.norm(vec)),
                         float(np.linalg.norm(centroid)))
                sample_logged += 1
        else:
            cur.execute(
                "UPDATE cluster_labels "
                "   SET centroid = %s "
                " WHERE cluster_run_id   = %s "
                "   AND cluster_id       = %s "
                "   AND is_event_cluster = %s",
                (centroid, run_id, cluster_id, is_event_cluster),
            )
            writes += 1
            if writes % COMMIT_EVERY == 0:
                conn.commit()
                log.info("[%s] Committed batch (%d total written so far)",
                         scope_label, writes)

        if i % LOG_EVERY == 0:
            log.info("[%s] Processed %d / %d clusters", scope_label, i, len(rows))

    if not dry_run:
        conn.commit()

    log.info("[%s] %s %d centroid(s) in %.1fs",
             scope_label,
             "Would write" if dry_run else "Wrote",
             len(rows) if dry_run else writes,
             time.perf_counter() - t0)
    return writes


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill cluster_labels.centroid")
    parser.add_argument("--run-id", type=int, default=None,
                        help="Restrict to one cluster_run_id (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute centroids but don't write to the database")
    parser.add_argument("--db-url", default=DB_URL_DEFAULT,
                        help="Postgres connection URL (default: PRISMA_DB_URL env var)")
    parser.add_argument("--scope", choices=["topical", "event", "both"], default="both",
                        help="Which cluster scope to backfill (default: both)")
    args = parser.parse_args()

    if not args.db_url:
        log.error("No database URL provided. Set PRISMA_DB_URL or pass --db-url.")
        return 1

    log.info("Connecting to %s", args.db_url.rsplit("@", 1)[-1])
    conn = psycopg2.connect(args.db_url)
    register_vector(conn)

    try:
        with conn.cursor() as cur:
            # ---------- Aggregate ----------
            do_topical = args.scope in ("topical", "both")
            do_event   = args.scope in ("event",   "both")

            topical_rows: list[tuple] = []
            event_rows:   list[tuple] = []

            if do_topical:
                log.info("Aggregating TOPICAL clusters (via articles.cluster_id)...")
                t0 = time.perf_counter()
                topical_rows = aggregate_topical_means(cur, args.run_id)
                log.info("Aggregated %d topical cluster(s) in %.1fs",
                         len(topical_rows), time.perf_counter() - t0)

            if do_event:
                log.info("Aggregating EVENT clusters (via articles.sub_cluster_id)...")
                t0 = time.perf_counter()
                event_rows = aggregate_event_means(cur, args.run_id)
                log.info("Aggregated %d event cluster(s) in %.1fs",
                         len(event_rows), time.perf_counter() - t0)

            if not topical_rows and not event_rows:
                log.warning("No clusters to update.")
                return 0

            # ---------- Normalize + write ----------
            total_writes = 0
            if do_topical:
                total_writes += _process_scope(
                    cur, conn, topical_rows,
                    scope_label="topical",
                    is_event_cluster=False,
                    dry_run=args.dry_run,
                )
            if do_event:
                total_writes += _process_scope(
                    cur, conn, event_rows,
                    scope_label="event",
                    is_event_cluster=True,
                    dry_run=args.dry_run,
                )

            log.info("Total writes: %d", total_writes)

            # ---------- Report ----------
            report_final_state(cur, args.run_id)

        log.info("-" * 60)
        log.info("Next step: create the IVFFlat index now that centroids exist.")
        log.info("Paste in pgAdmin:")
        log.info("")
        log.info("    CREATE INDEX cluster_labels_centroid_idx")
        log.info("        ON cluster_labels USING ivfflat (centroid vector_cosine_ops)")
        log.info("        WITH (lists = 100);")
        log.info("")

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
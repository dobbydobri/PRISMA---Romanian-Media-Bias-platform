import psycopg2
from pgvector.psycopg2 import register_vector
import numpy as np
from hdbscan import HDBSCAN
import umap
import time
import pandas as pd
from datetime import datetime, timezone
from scipy.spatial.distance import pdist, squareform
from env import DATABASE_URL

DB_URL = DATABASE_URL

# ── Hyperparameters ────────────────────────────────────────────────────────────
UMAP_NEIGHBORS      = 15
UMAP_COMPONENTS     = 15
UMAP_MIN_DIST       = 0.0
UMAP_METRIC         = 'euclidean'   
HDBSCAN_MIN_SIZE    = 10
HDBSCAN_MIN_SAMPLES = 5
CLUSTER_METHOD      = 'eom'
WINDOW_DAYS         = 28            
MIN_ENTITIES        = 2            
MIN_CONTENT_CHARS   = 800          

TEMPORAL_SCALE      = 0.20

MAX_SAME_OUTLET_PENALTY = 1.20


# ── Temporal feature ──────────────────────────────────────────────────────────

def build_temporal_semantic_matrix(
    embeddings: np.ndarray,
    timestamps: list
) -> np.ndarray:
    """
    Augments the semantic embedding matrix with a normalised temporal feature.
    """
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms < 1e-10, 1.0, norms)
    embeddings_normed = embeddings / norms

    if len(timestamps) < 2:
        return np.hstack([embeddings_normed, np.zeros((len(embeddings), 1))])

    t0 = min(timestamps)
    t1 = max(timestamps)
    window_seconds = max((t1 - t0).total_seconds(), 1.0)

    t_normalised = np.array([
        (t - t0).total_seconds() / window_seconds
        for t in timestamps
    ])  

    return np.hstack([
        embeddings_normed,
        (TEMPORAL_SCALE * t_normalised).reshape(-1, 1)
    ])


# ── Core window function ───────────────────────────────────────────────────────

def cluster_window(
    start_date,
    end_date,
    current_max_cluster_id: int,
    conn,
    run_id: int
) -> int:
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.id, a.embedding, a.published_at, a.outlet_id
        FROM articles a
        INNER JOIN outlets o ON a.outlet_id = o.id
        INNER JOIN (
            SELECT article_id
            FROM article_entities
            WHERE entity_label IN ('PERSON', 'ORGANIZATION', 'GPE')
            GROUP BY article_id
            HAVING COUNT(*) >= %s
        ) ae ON ae.article_id = a.id
        WHERE a.embedding IS NOT NULL
          AND a.embedding_version = 'v2_entity_augmented'
          AND o.outlet_type != 'fact_checker'
          AND a.published_at >= %s
          AND a.published_at < %s
          AND LENGTH(a.content_text) >= %s
        ORDER BY a.published_at ASC
    """, (MIN_ENTITIES, start_date, end_date, MIN_CONTENT_CHARS))

    rows = cursor.fetchall()

    if not rows:
        print(f"  [SKIP]  {start_date.date()} → {end_date.date()} | No articles after pre-filter.")
        cursor.close()
        return current_max_cluster_id

    ids         = [row[0] for row in rows]
    embeddings  = np.array([row[1] for row in rows])
    timestamps  = [row[2] for row in rows]
    outlet_ids  = np.array([row[3] for row in rows])  

    timestamps = [
        t.replace(tzinfo=None) if hasattr(t, 'tzinfo') and t.tzinfo else t
        for t in timestamps
    ]

    if len(ids) < UMAP_NEIGHBORS + 1:
        print(f"  [SKIP]  {start_date.date()} → {end_date.date()} "
              f"| {len(ids)} articles after filter, need {UMAP_NEIGHBORS + 1}.")
        cursor.close()
        return current_max_cluster_id

    # ── Temporal-semantic augmentation ────────────────────────────────────────
    augmented = build_temporal_semantic_matrix(embeddings, timestamps)

    # ── Dynamic Volume-Scaled Distance Penalization ───────────────────────────
    # Calculate base pair-wise Euclidean distances across the augmented space
    base_distances = squareform(pdist(augmented, metric='euclidean'))
    
    # Calculate volume share of each outlet inside this specific window
    unique_outlets, counts = np.unique(outlet_ids, return_counts=True)
    outlet_shares = {oid: count / len(ids) for oid, count in zip(unique_outlets, counts)}
    article_outlet_shares = np.array([outlet_shares[oid] for oid in outlet_ids])
    
    # Create mask tracking items sharing identical outlet matching origins
    same_outlet_mask = (outlet_ids[:, None] == outlet_ids[None, :])
    np.fill_diagonal(same_outlet_mask, False)  # Do not penalize self-distance
    
    # Penalize distances dynamically: high-volume outlets get high distance dispersion penalties
    dynamic_penalty = 1.0 + (MAX_SAME_OUTLET_PENALTY * article_outlet_shares[:, None])
    penalized_distances = np.where(same_outlet_mask, base_distances * dynamic_penalty, base_distances)

    # ── UMAP reduction ────────────────────────────────────────────────────────
    reducer = umap.UMAP(
        n_neighbors   = UMAP_NEIGHBORS,
        n_components  = UMAP_COMPONENTS,
        min_dist      = UMAP_MIN_DIST,
        metric        = 'precomputed',  
        random_state  = 42,
        low_memory    = False
    )

    # ── HDBSCAN ───────────────────────────────────────────────────────────────
    clusterer = HDBSCAN(
        min_cluster_size    = HDBSCAN_MIN_SIZE,
        min_samples         = HDBSCAN_MIN_SAMPLES,
        cluster_selection_method = CLUSTER_METHOD,
        metric              = 'euclidean',  
        gen_min_span_tree   = True
    )

    try:
        reduced        = reducer.fit_transform(penalized_distances)
        cluster_labels = clusterer.fit_predict(reduced)
    except Exception as e:
        print(f"  [ERROR] {start_date.date()} → {end_date.date()} | {e}. Skipping.")
        cursor.close()
        return current_max_cluster_id

    # ── Quality metrics ───────────────────────────────────────────────────────
    valid_labels  = [lbl for lbl in cluster_labels if lbl != -1]
    n_clusters    = len(set(valid_labels))
    n_noise       = list(cluster_labels).count(-1)
    noise_pct     = n_noise / len(ids) * 100
    dbcv          = clusterer.relative_validity_

    print(f"  [OK]    {start_date.date()} → {end_date.date()} "
          f"| Articles: {len(ids):,} | Events: {n_clusters} "
          f"| Noise: {noise_pct:.1f}% | DBCV: {dbcv:.4f}")

    if dbcv < 0.1:
        print(f"  [WARN]  DBCV below 0.10 — consider tuning parameters for this window.")

    # ── Write cluster assignments ─────────────────────────────────────────────
    update_data = []
    for label, article_id in zip(cluster_labels, ids):
        if label == -1:
            update_data.append((None, run_id, int(article_id)))
        else:
            new_cluster_id = int(label) + int(current_max_cluster_id)
            update_data.append((int(new_cluster_id), run_id, int(article_id)))

    cursor.executemany(
        "UPDATE articles SET cluster_id = %s, cluster_run_id = %s WHERE id = %s AND cluster_id IS NULL;",
        update_data
    )

    # ── Log window statistics to cluster_runs ────────────────────────────────
    cursor.execute("""
        INSERT INTO cluster_run_windows
            (run_id, window_start, window_end, articles_in, n_clusters, n_noise, dbcv)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (run_id, start_date, end_date, len(ids), n_clusters, n_noise, float(dbcv)))

    conn.commit()
    cursor.close()

    next_max_id = (int(current_max_cluster_id) + int(max(valid_labels)) + 1
                   if valid_labels else int(current_max_cluster_id))
    return next_max_id


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    conn   = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    register_vector(conn)

    cursor.execute("""
        INSERT INTO cluster_runs
            (umap_neighbors, umap_components, temporal_scale,
             hdbscan_min_size, hdbscan_min_samples,
             cluster_method, window_days, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        UMAP_NEIGHBORS, UMAP_COMPONENTS, TEMPORAL_SCALE,
        HDBSCAN_MIN_SIZE, HDBSCAN_MIN_SAMPLES,
        CLUSTER_METHOD, WINDOW_DAYS,
        'v2 entity-augmented embeddings, temporal-semantic hybrid, entity pre-filter, dynamic volume-scaled outlet penalty'
    ))
    run_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()

    # 28-day windows over the full scraping period
    windows     = pd.date_range('2024-01-01', '2026-01-01', freq=f'14D')
    offset      = 1
    start_total = time.time()

    print(f"[RUN {run_id}] Dynamic Penalty Topic Clustering | "
          f"{len(windows)-1} windows × {WINDOW_DAYS} days\n")

    for start in windows:
        end = start + pd.Timedelta(days=WINDOW_DAYS)
        offset = cluster_window(start, end, offset, conn, run_id)

    elapsed = time.time() - start_total
    print(f"\n[RUN {run_id}] COMPLETE in {elapsed/60:.1f} min. "
          f"Total events generated: {offset - 1:,}")

    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cluster_runs SET total_clusters = %s, completed_at = NOW() WHERE id = %s",
        (offset - 1, run_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
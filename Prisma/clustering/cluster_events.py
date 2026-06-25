import psycopg2
import ast
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scipy.spatial.distance import cdist
from collections import defaultdict
from env import DATABASE_URL

DB_URL = DATABASE_URL

# ── Methodology parameters (cite in thesis methodology section) ────────────────
WINDOW_DAYS          = 7     
WINDOW_STRIDE_DAYS   = 3    
SEMANTIC_THRESHOLD   = 0.12  
TITLE_SIM_THRESHOLD  = 0.15  
MIN_OUTLETS_PER_EVENT   = 2  
MIN_ARTICLES_FOR_PARENT = 10 


# ── Title pre-filter ───────────────────────────────────────────────────────────

def filter_by_title_similarity(assigned_indices, titles_lookup, threshold=TITLE_SIM_THRESHOLD):
    if len(assigned_indices) < 2:
        return assigned_indices

    titles = [titles_lookup[i] for i in assigned_indices]

    try:
        vec = TfidfVectorizer(
            min_df=1,
            token_pattern=r'(?u)\b[a-zA-ZÀ-ÿăîâșțĂÎÂȘȚ]{3,}\b'
        )
        tfidf_matrix = vec.fit_transform(titles)
    except ValueError:
        return assigned_indices

    sim_matrix = cosine_similarity(tfidf_matrix)
    # Use max pairwise similarity (excluding self) rather than average:
    # articles covering an event from an unusual angle score low on average
    # but remain connected to at least one cluster member — dropping them via
    # avg-sim removes genuine cross-outlet diversity, which is what PRISMA measures.
    np.fill_diagonal(sim_matrix, 0.0)
    max_sim = sim_matrix.max(axis=1)

    kept = [assigned_indices[i] for i, s in enumerate(max_sim) if s >= threshold]

    return kept if len(kept) >= 2 else assigned_indices


# ── Time-window assignment ─────────────────────────────────────────────────────

def assign_to_time_windows(timestamps_dt, window_days=WINDOW_DAYS, stride_days=WINDOW_STRIDE_DAYS):
    if not timestamps_dt:
        return {}

    base_date  = min(timestamps_dt).date()
    end_date   = max(timestamps_dt).date()
    total_days = (end_date - base_date).days

    windows = defaultdict(list)

    window_starts = []
    current = 0
    while current <= total_days:
        window_starts.append(current)
        current += stride_days

    for idx, ts in enumerate(timestamps_dt):
        article_day = (ts.date() - base_date).days
        for window_idx, window_start in enumerate(window_starts):
            window_end = window_start + window_days
            if window_start <= article_day <= window_end:
                windows[window_idx].append(idx)

    return windows


# ── Semantic clustering inside one window ──────────────────────────────────────

def cluster_window(window_indices, embeddings, threshold=SEMANTIC_THRESHOLD):
    if len(window_indices) < 2:
        return {window_indices[0]: 0} if window_indices else {}

    window_embeddings = embeddings[window_indices]
    distance_matrix   = cdist(window_embeddings, window_embeddings, metric='cosine')

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=threshold,
        linkage='average',
        metric='precomputed'
    )
    labels = clustering.fit_predict(distance_matrix)

    return dict(zip(window_indices, labels))


# ── Deduplication across overlapping windows ───────────────────────────────────

def deduplicate_articles_across_windows(window_assignments):
    final_assignment = {}
    for window_idx in sorted(window_assignments.keys()):
        for article_idx, sub_label in window_assignments[window_idx].items():
            if article_idx not in final_assignment:
                final_assignment[article_idx] = (window_idx, sub_label)
    return final_assignment


# ── Cross-window centroid merge ────────────────────────────────────────────────
# Articles in overlapping windows are anchored to their earliest eligible window
# by deduplicate_articles_across_windows. This can split a single real-world event
# across two adjacent window clusters when the event's density center straddles
# a window boundary. This pass merges such split candidates post-hoc.
#
# Algorithm:
#   1. Compute the embedding centroid of every candidate event group.
#   2. For each pair of candidates from adjacent windows (w, w+1), compute the
#      cosine distance between their centroids.
#   3. If distance < MERGE_THRESHOLD, merge the smaller group into the larger,
#      re-keying all articles under the surviving group's key.
#
# MERGE_THRESHOLD is set conservatively higher than SEMANTIC_THRESHOLD (0.12)
# because centroid distances are compressed relative to pairwise distances —
# two groups sharing ~70% of their vocabulary will have centroids much closer
# than any individual cross-group article pair.

CENTROID_MERGE_THRESHOLD = 0.18


def merge_adjacent_window_events(event_groups, embeddings):
    """
    Merges event candidate groups from adjacent windows whose centroids are
    within CENTROID_MERGE_THRESHOLD cosine distance of each other.

    Args:
        event_groups: dict mapping (window_idx, sub_label) → [article_indices]
        embeddings:   np.ndarray of all article embeddings for this topic cluster

    Returns:
        merged_groups: dict mapping canonical key → [article_indices]
    """
    keys   = list(event_groups.keys())
    groups = {k: list(v) for k, v in event_groups.items()}

    # Compute centroid per group
    def centroid(indices):
        vecs = embeddings[indices]
        c = vecs.mean(axis=0)
        norm = np.linalg.norm(c)
        return c / norm if norm > 1e-10 else c

    centroids = {k: centroid(groups[k]) for k in keys}

    # Union-Find for efficient group merging
    parent = {k: k for k in keys}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        # Larger group absorbs smaller
        if len(groups[ra]) >= len(groups[rb]):
            parent[rb] = ra
        else:
            parent[ra] = rb

    # Only compare candidates from adjacent windows
    by_window = defaultdict(list)
    for k in keys:
        by_window[k[0]].append(k)

    window_indices = sorted(by_window.keys())
    merges = 0

    for i, w in enumerate(window_indices[:-1]):
        next_w = window_indices[i + 1]
        if next_w - w > 1:
            continue  # non-adjacent windows, skip
        for ka in by_window[w]:
            for kb in by_window[next_w]:
                if find(ka) == find(kb):
                    continue
                ca, cb = centroids[find(ka)], centroids[find(kb)]
                dist = float(1.0 - np.dot(ca, cb))  # cosine distance of unit vectors
                if dist < CENTROID_MERGE_THRESHOLD:
                    union(ka, kb)
                    merges += 1

    # Rebuild groups under canonical (root) keys
    merged = defaultdict(list)
    for k in keys:
        root = find(k)
        merged[root].extend(groups[k])

    if merges > 0:
        print(f"  Merged {merges} cross-window boundary splits → "
              f"{len(merged)} candidates (was {len(keys)})")

    return dict(merged)




def main():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    print("Fetching eligible Tier 1 Topic Clusters grouped by run...")
    cur.execute("""
        SELECT cluster_run_id, cluster_id, COUNT(*)
        FROM articles
        WHERE cluster_id IS NOT NULL AND cluster_run_id IS NOT NULL
        GROUP BY cluster_run_id, cluster_id
        HAVING COUNT(*) >= %s;
    """, (MIN_ARTICLES_FOR_PARENT,))
    target_clusters = cur.fetchall()

    total_events_created    = 0
    total_skipped_outlet    = 0
    total_skipped_title     = 0

    for run_id, parent_cluster_id, article_count in target_clusters:
        cur.execute("""
            SELECT COALESCE(MAX(cluster_id), 0)
            FROM cluster_labels
            WHERE cluster_run_id = %s;
        """, (run_id,))
        next_cluster_id = cur.fetchone()[0] + 1

        print(f"\nProcessing Run {run_id} | Topic Cluster {parent_cluster_id} ({article_count} articles)...")

        # Resume guard: skip topic clusters already processed in a previous interrupted run.
        # Safe to restart at any point — completed clusters are detected by existing event
        # labels and skipped; only the in-progress cluster at crash time is re-processed.
        cur.execute("""
            SELECT COUNT(*) FROM cluster_labels
            WHERE cluster_run_id = %s AND parent_cluster_id = %s AND is_event_cluster = TRUE;
        """, (run_id, parent_cluster_id))
        if cur.fetchone()[0] > 0:
            print(f"  [SKIP] Already processed.")
            continue

        cur.execute("""
            SELECT id, embedding, published_at, outlet_id, title
            FROM articles
            WHERE cluster_run_id = %s AND cluster_id = %s AND published_at IS NOT NULL
            ORDER BY published_at ASC;
        """, (run_id, parent_cluster_id))

        rows = cur.fetchall()
        if not rows:
            continue

        article_ids   = [r[0] for r in rows]
        embeddings    = np.array(
            [ast.literal_eval(r[1]) if isinstance(r[1], str) else r[1] for r in rows],
            dtype=np.float32
        )
        timestamps_dt = [r[2] for r in rows]
        outlet_ids    = [r[3] for r in rows]
        titles_lookup = {i: (r[4] or '') for i, r in enumerate(rows)}

        # Step 1: Assign articles to rolling time windows
        windows = assign_to_time_windows(timestamps_dt)

        # Step 2: Cluster semantically inside each window
        window_assignments = {}
        for window_idx, indices in windows.items():
            window_assignments[window_idx] = cluster_window(indices, embeddings)

        # Step 3: Resolve overlapping assignments → one cluster per article
        final_assignment = deduplicate_articles_across_windows(window_assignments)

        # Step 4: Group into candidate event sub-clusters
        event_groups = defaultdict(list)
        for article_idx, (window_idx, sub_label) in final_assignment.items():
            event_groups[(window_idx, sub_label)].append(article_idx)

        print(f"  Initial candidates: {len(event_groups)}")

        # Step 4b: Merge candidates split across adjacent window boundaries.
        # Articles are anchored to their earliest eligible window by step 3, which
        # can fragment a single real event whose density center straddles the boundary.
        event_groups = merge_adjacent_window_events(event_groups, embeddings)

        # Step 5: Filter and persist
        events_created_this_topic = 0

        for (window_idx, sub_label), assigned_indices in event_groups.items():

            # ── Title pre-filter ────────────────────────────────────────────
            filtered_indices = filter_by_title_similarity(
                assigned_indices, titles_lookup, threshold=TITLE_SIM_THRESHOLD
            )
            n_filtered = len(assigned_indices) - len(filtered_indices)
            if n_filtered > 0:
                total_skipped_title += n_filtered

            assigned_indices = filtered_indices

            # ── Multi-outlet filter ─────────────────────────────────────────
            assigned_article_ids = [article_ids[i] for i in assigned_indices]
            sub_timestamps       = [timestamps_dt[i] for i in assigned_indices]
            sub_outlets          = set([outlet_ids[i] for i in assigned_indices])

            sub_article_count = len(assigned_article_ids)
            sub_outlet_count  = len(sub_outlets)

            if sub_outlet_count < MIN_OUTLETS_PER_EVENT:
                total_skipped_outlet += 1
                continue

            sub_date_from = min(sub_timestamps).date()
            sub_date_to   = max(sub_timestamps).date()

            current_event_id  = next_cluster_id
            next_cluster_id  += 1
            events_created_this_topic += 1

            cur.execute("""
                INSERT INTO cluster_labels (
                    cluster_run_id, cluster_id, parent_cluster_id, is_event_cluster,
                    top_tfidf_terms, top_entities,
                    label_text, article_count, outlet_count, date_from, date_to
                ) VALUES (%s, %s, %s, TRUE,
                    ARRAY[]::TEXT[], ARRAY[]::TEXT[],
                    %s, %s, %s, %s, %s)
                ON CONFLICT (cluster_run_id, cluster_id) DO NOTHING;
            """, (run_id, current_event_id, parent_cluster_id,
                  'Pending Event Label...', sub_article_count, sub_outlet_count,
                  sub_date_from, sub_date_to))

            cur.execute("""
                UPDATE articles
                SET sub_cluster_id = %s
                WHERE id = ANY(%s);
            """, (current_event_id, assigned_article_ids))

        total_events_created += events_created_this_topic
        print(f"  Kept: {events_created_this_topic} multi-outlet events")
        conn.commit()

    print(f"\n{'='*60}")
    print(f"Time-Windowed Event Sub-Clustering Complete")
    print(f"{'='*60}")
    print(f"Events created:              {total_events_created}")
    print(f"Articles removed by title:   {total_skipped_title}")
    print(f"Clusters removed (1 outlet): {total_skipped_outlet}")
    print(f"Window:                      {WINDOW_DAYS}d (stride {WINDOW_STRIDE_DAYS}d)")
    print(f"Semantic threshold:          {SEMANTIC_THRESHOLD}")
    print(f"Centroid merge threshold:    {CENTROID_MERGE_THRESHOLD}")
    print(f"Title similarity threshold:  {TITLE_SIM_THRESHOLD}")

    print("\nGenerating labels for new event sub-clusters...")
    from generate_labels import label_event_clusters
    label_event_clusters(conn)

    conn.close()


if __name__ == "__main__":
    main()
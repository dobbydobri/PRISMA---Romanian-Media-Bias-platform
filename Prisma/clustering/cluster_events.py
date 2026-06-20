import psycopg2
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
    avg_sim = sim_matrix.mean(axis=1)

    kept = [assigned_indices[i] for i, s in enumerate(avg_sim) if s >= threshold]

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


# ── Main ───────────────────────────────────────────────────────────────────────

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
            [eval(r[1]) if isinstance(r[1], str) else r[1] for r in rows],
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
    print(f"Title similarity threshold:  {TITLE_SIM_THRESHOLD}")

    print("\nGenerating labels for new event sub-clusters...")
    from generate_labels import label_event_clusters
    label_event_clusters(conn)

    conn.close()


if __name__ == "__main__":
    main()
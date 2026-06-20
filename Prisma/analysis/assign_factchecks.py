import psycopg2
from pgvector.psycopg2 import register_vector
import numpy as np
import time
from sentence_transformers import CrossEncoder
from env import DATABASE_URL

DB_URL = DATABASE_URL

BI_ENCODER_THRESHOLD = 0.85
CROSS_ER_THRESHOLD = 0.7
SUB_CLUSTER_THRESHOLD = 0.6

print("[INIT] Loading multilingual BGE Reranker model...")
cross_model = CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512, device='cuda')


def shares_meaningful_keywords(claim: str, title: str) -> bool:
    ignore_words = {
        'este', 'sunt', 'fost', 'care', 'găsit', 'spune', 'arată', 'vrea',
        'românia', 'româniei', 'bucurești', 'bucuresti', 'guvern', 'ministru',
        'declarat', 'oficial', 'video', 'imagini', 'atacat', 'noua', 'veche',
        'acest', 'aceasta', 'după', 'peste', 'când', 'cum'
    }
    
    def extract_roots(text: str):
        words = text.lower().split()
        roots = set()
        for w in words:
            clean_w = w.strip(".,!?\"'()„”:-–—")
            if len(clean_w) > 4 and clean_w not in ignore_words:
                roots.add(clean_w[:5])
        return roots

    claim_roots = extract_roots(claim)
    title_roots = extract_roots(title)
    
    return len(claim_roots.intersection(title_roots)) >= 1


# ── Pass 1: Topic Cluster Assignment (unchanged logic) ────────────────────────

def assign_to_topic_clusters(conn, run_id):
    cursor = conn.cursor()

    print("  Computing cluster centroids...")
    cursor.execute("""
        SELECT cluster_id, AVG(embedding) AS centroid
        FROM articles
        WHERE cluster_run_id = %s
          AND cluster_id IS NOT NULL
          AND embedding IS NOT NULL
        GROUP BY cluster_id
        ORDER BY cluster_id
    """, (run_id,))

    centroid_rows = cursor.fetchall()
    cluster_ids   = [row[0] for row in centroid_rows]
    centroids     = np.array([row[1] for row in centroid_rows])

    norms     = np.linalg.norm(centroids, axis=1, keepdims=True)
    norms     = np.where(norms < 1e-10, 1.0, norms)
    centroids = centroids / norms

    print("  Fetching sample news headlines...")
    cursor.execute("""
        WITH RankedTitles AS (
            SELECT cluster_id, title,
                   ROW_NUMBER() OVER(PARTITION BY cluster_id ORDER BY id) as rn
            FROM articles
            WHERE cluster_run_id = %s 
              AND cluster_id IS NOT NULL 
              AND title IS NOT NULL
        )
        SELECT cluster_id, title FROM RankedTitles WHERE rn <= 10;
    """, (run_id,))
    
    cluster_titles = {}
    for row in cursor.fetchall():
        c_id, title = row[0], row[1]
        if c_id not in cluster_titles:
            cluster_titles[c_id] = []
        cluster_titles[c_id].append(title)

    cursor.execute("""
        SELECT fc.id, fc.article_id, fc.verdict, fc.claim_text, a.embedding
        FROM fact_checks fc
        JOIN articles a ON fc.article_id = a.id
        WHERE a.embedding IS NOT NULL
    """)
    fc_rows = cursor.fetchall()
    
    if not fc_rows:
        cursor.close()
        return

    fc_ids         = [row[0] for row in fc_rows]
    fc_article_ids = [row[1] for row in fc_rows]
    fc_claims      = [row[3] for row in fc_rows]
    fc_embeddings  = np.array([row[4] for row in fc_rows])

    fc_norms      = np.linalg.norm(fc_embeddings, axis=1, keepdims=True)
    fc_norms      = np.where(fc_norms < 1e-10, 1.0, fc_norms)
    fc_embeddings = fc_embeddings / fc_norms

    print("  Running fast Bi-Encoder matrix search...")
    similarities = fc_embeddings @ centroids.T

    print("  Running strict relevance verification...")
    
    assigned        = 0
    rejected_coarse = 0
    rejected_guard  = 0
    rejected_fine   = 0
    insert_rows     = []

    start = time.time()

    for i in range(len(fc_ids)):
        claim_text = fc_claims[i]
        top_3_indices = np.argsort(similarities[i])[::-1][:3]
        
        best_cluster_id = None
        best_rerank_score = -1.0
        best_bi_sim = 0.0

        for idx in top_3_indices:
            bi_sim = float(similarities[i][idx])
            if bi_sim < BI_ENCODER_THRESHOLD:
                continue
                
            candidate_cluster_id = cluster_ids[idx]
            candidate_titles = cluster_titles.get(candidate_cluster_id, [])
            
            valid_titles = [t for t in candidate_titles if shares_meaningful_keywords(claim_text, t)]
            
            if not valid_titles:
                rejected_guard += 1
                continue

            pairs = [[claim_text, title] for title in valid_titles]
            logits = cross_model.predict(pairs)
            
            if isinstance(logits, float) or isinstance(logits, np.float32):
                logits = np.array([logits])
                
            scores = 1 / (1 + np.exp(-logits))
                
            max_score = float(np.max(scores))

            if max_score > best_rerank_score:
                best_rerank_score = max_score
                best_cluster_id = candidate_cluster_id
                best_bi_sim = bi_sim

        if best_rerank_score == -1.0:
            insert_rows.append((int(fc_ids[i]), int(fc_article_ids[i]), run_id, None, 0.0))
            rejected_coarse += 1
            
        elif best_rerank_score >= CROSS_ER_THRESHOLD:
            insert_rows.append((int(fc_ids[i]), int(fc_article_ids[i]), run_id, best_cluster_id, round(best_rerank_score, 4)))
            assigned += 1
            
        else:
            insert_rows.append((int(fc_ids[i]), int(fc_article_ids[i]), run_id, None, round(best_rerank_score, 4)))
            rejected_fine += 1

    elapsed = time.time() - start
    print(f"  Pass 1 complete in {elapsed:.1f}s.")

    cursor.executemany("""
        INSERT INTO factcheck_cluster_map
            (factcheck_id, article_id, cluster_run_id, cluster_id, similarity)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (factcheck_id, cluster_run_id) DO UPDATE SET
            cluster_id = EXCLUDED.cluster_id,
            similarity = EXCLUDED.similarity
    """, insert_rows)
    conn.commit()

    total = assigned + rejected_coarse + rejected_guard + rejected_fine
    print(f"\n  === Pass 1: Topic Cluster Assignment ===")
    print(f"  Assigned (Confirmed Matches):           {assigned:,}")
    print(f"  Rejected (Failed Coarse Net):           {rejected_coarse:,}")
    print(f"  Rejected (Vetoed by Keyword Guardrail): {rejected_guard:,}")
    print(f"  Rejected (Failed Reranker Relevance):   {rejected_fine:,}")
    print(f"  Topic Assignment Rate:                  {assigned/total*100:.1f}%\n")

    cursor.close()


# ── Pass 2: Sub-Cluster Refinement (NEW) ──────────────────────────────────────

def refine_to_sub_clusters(conn, run_id):
    cursor = conn.cursor()

    print("  Fetching fact-checks already assigned to topic clusters...")
    cursor.execute("""
        SELECT fcm.factcheck_id, fc.claim_text, fcm.cluster_id
        FROM factcheck_cluster_map fcm
        JOIN fact_checks fc ON fc.id = fcm.factcheck_id
        WHERE fcm.cluster_run_id = %s
          AND fcm.cluster_id IS NOT NULL
        ORDER BY fcm.factcheck_id
    """, (run_id,))
    
    assigned_fcs = cursor.fetchall()
    if not assigned_fcs:
        print("  No topic-assigned fact-checks to refine.")
        cursor.close()
        return

    print(f"  Refining {len(assigned_fcs):,} fact-checks to event sub-clusters...")

    refined         = 0
    no_sub_found    = 0
    no_keyword_pass = 0
    low_score       = 0
    update_rows     = []
    
    start = time.time()

    for fc_id, claim_text, parent_cluster_id in assigned_fcs:
        cursor.execute("""
            SELECT cl.cluster_id,
                   array_agg(a.title ORDER BY a.published_at) AS titles
            FROM cluster_labels cl
            JOIN articles a ON a.sub_cluster_id = cl.cluster_id 
                            AND a.cluster_run_id = cl.cluster_run_id
            WHERE cl.is_event_cluster = TRUE
              AND cl.parent_cluster_id = %s
              AND cl.cluster_run_id = %s
            GROUP BY cl.cluster_id
        """, (parent_cluster_id, run_id))
        
        candidates = cursor.fetchall()
        if not candidates:
            no_sub_found += 1
            continue
        
        best_sub_id = None
        best_sub_score = -1.0

        for sub_id, titles in candidates:
            sample_titles = titles[:8]
            valid_titles = [t for t in sample_titles if shares_meaningful_keywords(claim_text, t)]
            
            if not valid_titles:
                continue

            pairs = [[claim_text, t] for t in valid_titles]
            logits = cross_model.predict(pairs)
            
            if isinstance(logits, float) or isinstance(logits, np.float32):
                logits = np.array([logits])
                
            scores = 1 / (1 + np.exp(-logits))
            max_score = float(np.max(scores))

            if max_score > best_sub_score:
                best_sub_score = max_score
                best_sub_id = sub_id

        if best_sub_id is None:
            no_keyword_pass += 1
        elif best_sub_score >= SUB_CLUSTER_THRESHOLD:
            update_rows.append((best_sub_id, round(best_sub_score, 4), fc_id, run_id))
            refined += 1
        else:
            low_score += 1

    elapsed = time.time() - start
    print(f"  Pass 2 complete in {elapsed:.1f}s.")

    if update_rows:
        cursor.executemany("""
            UPDATE factcheck_cluster_map
            SET sub_cluster_id = %s,
                sub_similarity = %s
            WHERE factcheck_id = %s
              AND cluster_run_id = %s
        """, update_rows)
        conn.commit()

    total = len(assigned_fcs)
    print(f"\n  === Pass 2: Sub-Cluster Refinement ===")
    print(f"  Refined to event sub-cluster:           {refined:,}")
    print(f"  No event sub-clusters in topic:         {no_sub_found:,}")
    print(f"  No sub-cluster passed keyword filter:   {no_keyword_pass:,}")
    print(f"  Low reranker score (kept at topic):     {low_score:,}")
    print(f"  Sub-Cluster Refinement Rate:            {refined/total*100:.1f}%\n")

    cursor.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    conn   = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    register_vector(conn)

    cursor.execute("SELECT MAX(id) FROM cluster_runs WHERE completed_at IS NOT NULL")
    run_id = cursor.fetchone()[0]
    print(f"\n[ASSIGN] Using cluster run {run_id}\n")
    cursor.close()

    print("[PASS 1] Topic Cluster Assignment")
    assign_to_topic_clusters(conn, run_id)

    print("[PASS 2] Sub-Cluster Refinement")
    refine_to_sub_clusters(conn, run_id)

    conn.close()
    print("[DONE] Fact-check assignment complete.\n")


if __name__ == '__main__':
    main()
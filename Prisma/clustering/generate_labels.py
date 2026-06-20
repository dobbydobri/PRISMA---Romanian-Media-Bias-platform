import psycopg2
from pgvector.psycopg2 import register_vector
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
from collections import defaultdict
from env import DATABASE_URL

DB_URL = DATABASE_URL

# Comprehensive Romanian stopwords for news text.
ROMANIAN_STOPWORDS = [
    'un', 'o', 'al', 'ale', 'ai', 'cel', 'cea', 'cei', 'cele',
    'unui', 'unei', 'unor', 'unii', 'unele', 'in', 'în', 'la', 'pe', 'de', 'cu', 'din', 'spre', 'prin',
    'despre', 'intre', 'între', 'dupa', 'după', 'inainte', 'înainte',
    'sub', 'peste', 'fata', 'față', 'langa', 'lângă', 'pentru',
    'contra', 'fara', 'fără', 'pana', 'până', 'dintre', 'versus',
    'si', 'și', 'sau', 'dar', 'ci', 'ca', 'că', 'daca', 'dacă',
    'desi', 'deși', 'cand', 'când', 'unde', 'cum', 'care', 'fie',
    'ori', 'nici', 'atat', 'atât', 'cat', 'cât', 'deci', 'totusi',
    'totuși', 'insa', 'însă', 'asadar', 'așadar',
    'eu', 'tu', 'el', 'ea', 'noi', 'voi', 'ei', 'ele',
    'il', 'îl', 'ii', 'îi', 'le', 'ma', 'mă', 'te', 'se', 'ne',
    'va', 'vă', 'imi', 'îmi', 'iti', 'îți', 'lui', 'lor',
    'meu', 'mea', 'tau', 'tău', 'ta', 'sau', 'său', 'sa',
    'acesta', 'aceasta', 'acestia', 'aceștia', 'acestea',
    'acel', 'acea', 'acei', 'acele', 'acelasi', 'același',
    'este', 'esti', 'ești', 'sunt', 'suntem', 'sunteti', 'sunteți',
    'fi', 'era', 'eram', 'erai', 'erati', 'erați', 'erau',
    'au', 'am', 'ai', 'ati', 'ați', 'va', 'vor', 'voi',
    'poate', 'trebuie', 'fost', 'fie', 'fiu', 'fii',
    'are', 'avem', 'aveti', 'aveți', 'aveau', 'aveam',
    'sa', 'să', 'ar', 'as', 'aș',
    'mai', 'nu', 'tot', 'deja', 'acum', 'inca', 'încă',
    'chiar', 'doar', 'tocmai', 'prea', 'foarte', 'astfel',
    'apoi', 'atunci', 'acolo', 'aici', 'asa', 'așa',
    'atat', 'atât', 'cât', 'cat', 'cum',
    'an', 'ani', 'zi', 'zile', 'ora', 'ore', 'luna', 'luni',
    'saptamana', 'săptămână', 'ieri', 'azi', 'maine', 'mâine',
    'astazi', 'astăzi', 'miercuri', 'joi', 'vineri', 'sambata',
    'sâmbătă', 'duminica', 'duminică', 'luni', 'marti', 'marți',
    'mii', 'sute', 'milioane', 'miliarde', 'procente', 'procent',
    'foto', 'video', 'live', 'exclusiv', 'breaking', 'update',
    'stire', 'știre', 'reportaj', 'interviu', 'editorial',
    'spus', 'declarat', 'anuntat', 'anunțat', 'precizat',
    'transmis', 'afirmat', 'mentionat', 'menționat',
    'aratat', 'arătat', 'explicat', 'adaugat', 'adăugat',
]

def get_latest_run_id(cursor) -> int:
    cursor.execute("SELECT MAX(id) FROM cluster_runs WHERE completed_at IS NOT NULL")
    run_id = cursor.fetchone()[0]
    if run_id is None:
        raise ValueError("No completed cluster runs found in database.")
    return run_id

# --- TOPIC LEVEL FUNCTIONS (ORIGINAL) ---

def fetch_cluster_corpus(cursor, run_id: int) -> dict:
    print("  Fetching topic cluster title corpus...")
    cursor.execute("""
        SELECT
            a.cluster_id,
            STRING_AGG(a.title, ' ')        AS title_corpus,
            COUNT(*)                         AS article_count,
            COUNT(DISTINCT a.outlet_id)      AS outlet_count,
            MIN(a.published_at)::date        AS date_from,
            MAX(a.published_at)::date        AS date_to
        FROM articles a
        WHERE a.cluster_run_id = %s
          AND a.cluster_id IS NOT NULL
          AND a.title IS NOT NULL
        GROUP BY a.cluster_id
        ORDER BY a.cluster_id
    """, (run_id,))
    result = {}
    for row in cursor.fetchall():
        result[row[0]] = {'corpus': row[1], 'article_count': row[2], 'outlet_count': row[3], 'date_from': row[4], 'date_to': row[5]}
    return result

def fetch_top_entities_per_cluster(cursor, run_id: int) -> dict:
    print("  Fetching top entities per topic cluster...")
    cursor.execute("""
        SELECT
            a.cluster_id, ae.entity_text, COUNT(*) AS mention_count
        FROM article_entities ae
        JOIN articles a ON ae.article_id = a.id
        WHERE a.cluster_run_id = %s AND a.cluster_id IS NOT NULL
          AND ae.entity_label IN ('PERSON', 'ORGANIZATION', 'GPE')
          AND LENGTH(ae.entity_text) >= 3
        GROUP BY a.cluster_id, ae.entity_text
        ORDER BY a.cluster_id, COUNT(*) DESC
    """, (run_id,))
    entities = defaultdict(list)
    for cluster_id, entity_text, count in cursor.fetchall():
        entities[cluster_id].append(entity_text)
    return {cid: ents[:5] for cid, ents in entities.items()}

def run_tfidf(cluster_corpus: dict) -> dict:
    print("  Running TF-IDF vectorisation for topic clusters...")
    cluster_ids = list(cluster_corpus.keys())
    documents   = [cluster_corpus[cid]['corpus'] for cid in cluster_ids]
    vectorizer = TfidfVectorizer(max_features=40000, ngram_range=(1, 2), min_df=3, max_df=0.65, stop_words=ROMANIAN_STOPWORDS, token_pattern=r'(?u)\b[a-zA-ZÀ-ÿăîâșțĂÎÂȘȚ]{3,}\b', sublinear_tf=True)
    tfidf_matrix  = vectorizer.fit_transform(documents)
    feature_names = vectorizer.get_feature_names_out()
    labels = {}
    for i, cluster_id in enumerate(cluster_ids):
        scores     = tfidf_matrix[i].toarray()[0]
        top_idx    = np.argsort(scores)[-7:][::-1]
        top_terms  = [feature_names[j] for j in top_idx if scores[j] > 0]
        labels[cluster_id] = top_terms[:5]
    return labels

# --- EVENT LEVEL FUNCTIONS (NEW) ---

def fetch_event_cluster_corpus(cursor, run_id: int) -> dict:
    print("  Fetching event sub-cluster title corpus...")
    cursor.execute("""
        SELECT
            a.sub_cluster_id,
            STRING_AGG(a.title, ' ')        AS title_corpus,
            COUNT(*)                         AS article_count,
            COUNT(DISTINCT a.outlet_id)      AS outlet_count,
            MIN(a.published_at)::date        AS date_from,
            MAX(a.published_at)::date        AS date_to
        FROM articles a
        WHERE a.cluster_run_id = %s
          AND a.sub_cluster_id IS NOT NULL
          AND a.title IS NOT NULL
        GROUP BY a.sub_cluster_id
        ORDER BY a.sub_cluster_id
    """, (run_id,))
    result = {}
    for row in cursor.fetchall():
        result[row[0]] = {'corpus': row[1], 'article_count': row[2], 'outlet_count': row[3], 'date_from': row[4], 'date_to': row[5]}
    return result

def fetch_top_entities_per_event_cluster(cursor, run_id: int) -> dict:
    print("  Fetching top entities per event sub-cluster...")
    cursor.execute("""
        SELECT
            a.sub_cluster_id, ae.entity_text, COUNT(*) AS mention_count
        FROM article_entities ae
        JOIN articles a ON ae.article_id = a.id
        WHERE a.cluster_run_id = %s AND a.sub_cluster_id IS NOT NULL
          AND ae.entity_label IN ('PERSON', 'ORGANIZATION', 'GPE')
          AND LENGTH(ae.entity_text) >= 3
        GROUP BY a.sub_cluster_id, ae.entity_text
        ORDER BY a.sub_cluster_id, COUNT(*) DESC
    """, (run_id,))
    entities = defaultdict(list)
    for cluster_id, entity_text, count in cursor.fetchall():
        entities[cluster_id].append(entity_text)
    return {cid: ents[:5] for cid, ents in entities.items()}

def run_tfidf_events(cluster_corpus: dict) -> dict:
    print("  Running TF-IDF vectorisation for event sub-clusters...")
    cluster_ids = list(cluster_corpus.keys())
    documents   = [cluster_corpus[cid]['corpus'] for cid in cluster_ids]
    vectorizer = TfidfVectorizer(max_features=40000, ngram_range=(1, 2), min_df=1, max_df=0.85, stop_words=ROMANIAN_STOPWORDS, token_pattern=r'(?u)\b[a-zA-ZÀ-ÿăîâșțĂÎÂȘȚ]{3,}\b', sublinear_tf=True)
    tfidf_matrix  = vectorizer.fit_transform(documents)
    feature_names = vectorizer.get_feature_names_out()
    labels = {}
    for i, cluster_id in enumerate(cluster_ids):
        scores     = tfidf_matrix[i].toarray()[0]
        top_idx    = np.argsort(scores)[-7:][::-1]
        top_terms  = [feature_names[j] for j in top_idx if scores[j] > 0]
        labels[cluster_id] = top_terms[:5]
    return labels

def label_event_clusters(conn):
    cursor = conn.cursor()
    run_id = get_latest_run_id(cursor)
    print(f"[LABELS] Generating labels for event sub-clusters in run {run_id}...\n")
    
    cluster_corpus = fetch_event_cluster_corpus(cursor, run_id)
    if not cluster_corpus:
        print("[LABELS] No pending event sub-clusters found to label.")
        return
        
    top_entities   = fetch_top_entities_per_event_cluster(cursor, run_id)
    tfidf_labels   = run_tfidf_events(cluster_corpus)

    rows = []
    for cluster_id, terms in tfidf_labels.items():
        entities   = top_entities.get(cluster_id, [])
        label_text = build_label_text(terms, entities)
        info       = cluster_corpus[cluster_id]
        rows.append((terms, entities, label_text, cluster_id, run_id))

    cursor.executemany("""
        UPDATE cluster_labels
        SET top_tfidf_terms = %s,
            top_entities    = %s,
            label_text      = %s
        WHERE cluster_id      = %s
          AND cluster_run_id  = %s
          AND label_text      = 'Pending Event Label...'
    """, rows)

    conn.commit()
    print(f"[LABELS] Event labeling complete. {len(rows)} sub-clusters labeled.\n")
    cursor.close()

# --- UTILS & MAIN ---

def build_label_text(tfidf_terms: list, entities: list) -> str:
    seen = set()
    parts = []
    for item in entities[:3]:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            parts.append(item)
    for term in tfidf_terms:
        key = term.lower()
        if key not in seen and len(parts) < 5:
            seen.add(key)
            parts.append(term)
    return ', '.join(parts) if parts else 'fără etichetă'

def main():
    conn   = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    register_vector(conn)

    run_id = get_latest_run_id(cursor)
    print(f"[LABELS] Generating labels for TOPIC cluster run {run_id}...\n")

    cluster_corpus  = fetch_cluster_corpus(cursor, run_id)
    top_entities    = fetch_top_entities_per_cluster(cursor, run_id)
    tfidf_labels    = run_tfidf(cluster_corpus)

    print("  Assembling and saving TOPIC labels...")
    rows = []
    for cluster_id, terms in tfidf_labels.items():
        entities    = top_entities.get(cluster_id, [])
        label_text  = build_label_text(terms, entities)
        info        = cluster_corpus[cluster_id]
        rows.append((cluster_id, run_id, terms, entities, label_text, info['article_count'], info['outlet_count'], info['date_from'], info['date_to']))

    cursor.executemany("""
        INSERT INTO cluster_labels
            (cluster_id, cluster_run_id, top_tfidf_terms, top_entities,
             label_text, article_count, outlet_count, date_from, date_to)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (cluster_run_id, cluster_id) DO UPDATE SET
            top_tfidf_terms = EXCLUDED.top_tfidf_terms,
            top_entities    = EXCLUDED.top_entities,
            label_text      = EXCLUDED.label_text,
            article_count   = EXCLUDED.article_count,
            outlet_count    = EXCLUDED.outlet_count,
            date_from       = EXCLUDED.date_from,
            date_to         = EXCLUDED.date_to
    """, rows)

    conn.commit()
    print("\n[LABELS] Topic labeling Complete.\n")
    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
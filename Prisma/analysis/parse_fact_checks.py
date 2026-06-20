import psycopg2
from pgvector.psycopg2 import register_vector
import re
import time
from env import DATABASE_URL

DB_URL = DATABASE_URL

VERDICT_MAP = {
    # ── Factual verdicts ──
    'FALS':                     ('false',            'verdict'),
    'PARȚIAL FALS':             ('partially_false',  'verdict'),
    'PARTIAL FALS':             ('partially_false',  'verdict'),
    'ADEVĂRAT':                 ('true',             'verdict'),
    'ADEVARAT':                 ('true',             'verdict'),
    'PARȚIAL ADEVĂRAT':         ('partially_true',   'verdict'),
    'PARTIAL ADEVARAT':         ('partially_true',   'verdict'),
    'TRUNCHIAT':                ('truncated',        'verdict'),
    'CONTEXT LIPSĂ':            ('missing_context',  'verdict'),
    'CONTEXT LIPSA':            ('missing_context',  'verdict'),
    'LIPSĂ CONTEXT':            ('missing_context',  'verdict'),
    'LIPSA CONTEXT':            ('missing_context',  'verdict'),
    'SCAM':                     ('scam',             'digital_malice'),
    'DEEPFAKE':                 ('deepfake',         'synthetic'),
    'DEEP FAKE':                ('deepfake',         'synthetic'),
    'TEORIA CONSPIRAȚIEI':      ('conspiracy_theory', 'narrative'),
    'TEORIA CONSPIRATIEI':      ('conspiracy_theory', 'narrative'),
    'SATIRĂ':                   ('satire',           'context'),
    'SATIRA':                   ('satire',           'context'),

    # ── Veridica verdicts ──
    'FAKE NEWS':                ('fake_news',        'verdict'),
    'FAKE-NEWS':                ('fake_news',        'verdict'),
    'PROPAGANDĂ DE RĂZBOI':     ('war_propaganda',   'narrative'),
    'PROPAGANDA DE RAZBOI':     ('war_propaganda',   'narrative'),
    'DEZINFORMARE':             ('disinformation',   'verdict'),

    'IMPOSIBIL DE VERIFICAT':       ('unverifiable',     'verdict'),
    'ERATĂ- IMPOSIBIL DE VERIFICAT':('unverifiable',     'verdict'),
    'PARTIAL ADEVĂRAT':             ('partially_true',   'verdict'),
    'CONTEXT LISPĂ':                ('missing_context',  'verdict'),
    'IMAGINI ALTERATE CU IA':       ('ai_edited',        'synthetic'),
    'FOTOGRAFIE AI':                ('ai_edited',        'synthetic'),
    'POSTARE GENERATĂ ARTIFICIAL':  ('ai_generated',     'synthetic'),
    'EDITAT CU IA':                 ('ai_edited',        'synthetic'),
    'FOTOGRAFIE TRUCATĂ':           ('doctored_photo',   'synthetic')
}

VERDICT_TOKENS = sorted(VERDICT_MAP.keys(), key=len, reverse=True)

VERDICT_PATTERN = re.compile(
    r'^(' + '|'.join(re.escape(v) for v in VERDICT_TOKENS) + r')\s*(?:[|:I]\s*)?(.+)$',
    re.IGNORECASE
)


def parse_title(title: str) -> dict | None:
    if not title:
        return None

    title_clean = title.strip()
    match = VERDICT_PATTERN.match(title_clean)

    if not match:
        return None

    raw_token  = match.group(1).strip().upper()
    claim_text = match.group(2).strip()

    if raw_token in VERDICT_MAP:
        verdict, verdict_type = VERDICT_MAP[raw_token]
        return {
            'verdict':      verdict,
            'verdict_type': verdict_type,
            'claim_text':   claim_text,
            'raw_verdict':  raw_token,
        }

    return None


def main():
    conn   = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    register_vector(conn)

    cursor.execute("""
        SELECT a.id, a.outlet_id, a.title, a.published_at
        FROM articles a
        JOIN outlets o ON a.outlet_id = o.id
        WHERE o.outlet_type = 'fact_checker'
          AND a.title IS NOT NULL
        ORDER BY a.published_at ASC
    """)
    rows = cursor.fetchall()
    print(f"[FACT-CHECK] Scanning {len(rows):,} articles from fact-checker outlets...\n")

    parsed   = 0
    skipped  = 0
    verdicts = {}  

    insert_rows = []
    for article_id, outlet_id, title, published_at in rows:
        result = parse_title(title)
        if result:
            insert_rows.append((
                article_id,
                outlet_id,
                result['verdict'],
                result['verdict_type'],
                result['claim_text'],
                result['raw_verdict'],
                published_at,
            ))
            verdicts[result['verdict']] = verdicts.get(result['verdict'], 0) + 1
            parsed += 1
        else:
            skipped += 1

    if insert_rows:
        cursor.executemany("""
            INSERT INTO fact_checks
                (article_id, outlet_id, verdict, verdict_type,
                 claim_text, raw_verdict, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (article_id) DO UPDATE SET
                verdict      = EXCLUDED.verdict,
                verdict_type = EXCLUDED.verdict_type,
                claim_text   = EXCLUDED.claim_text,
                raw_verdict  = EXCLUDED.raw_verdict
        """, insert_rows)
        conn.commit()

    print(f"  Parsed as fact-checks:  {parsed:,}")
    print(f"  Skipped (no verdict):   {skipped:,}")
    print(f"  Parse rate:              {parsed/(parsed+skipped)*100:.1f}%\n")

    print(f"  {'Verdict':<25} {'Count':>6}")
    print(f"  {'-'*32}")
    for verdict, count in sorted(verdicts.items(), key=lambda x: -x[1]):
        print(f"  {verdict:<25} {count:>6}")

    print(f"\n  Sample non-verdict titles (first 10 skipped):")
    cursor.execute("""
        SELECT a.title
        FROM articles a
        JOIN outlets o ON a.outlet_id = o.id
        WHERE o.outlet_type = 'fact_checker'
          AND a.id NOT IN (SELECT article_id FROM fact_checks)
        LIMIT 10
    """)
    for i, (title,) in enumerate(cursor.fetchall(), 1):
        print(f"    {i:>2}. {title[:120]}")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    main()
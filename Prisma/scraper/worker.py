import os
import time
import random
import psycopg2
import hashlib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from lxml import html
from outlet_rules import RULES

def _fail(var):
    raise EnvironmentError(f"Required env var '{var}' not set")

DB_PARAMS = {
    "dbname":   os.getenv("DB_NAME")     or _fail("DB_NAME"),
    "user":     os.getenv("DB_USER")     or _fail("DB_USER"),
    "password": os.getenv("DB_PASSWORD") or _fail("DB_PASSWORD"),
    "host":     os.getenv("DB_HOST", "postgres_db"),
    "port":     5432,
}
OUTLET_ID = int(os.getenv("OUTLET_ID", "12"))

# --- Robust User-Agent Rotation ---
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1'
]

# --- RESILIENT SESSION CONFIGURATION FOR WORKER ---
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[500, 502, 503, 504],
    raise_on_status=False
)
session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
session.mount("http://", HTTPAdapter(max_retries=retry_strategy))

def process_next_article(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, url FROM crawl_queue 
        WHERE status = 'pending' AND outlet_id = %s
        ORDER BY priority ASC, id ASC 
        LIMIT 1 FOR UPDATE SKIP LOCKED;
    """, (OUTLET_ID,))
    task = cur.fetchone()

    if not task:
        return False

    q_id, url = task
    config = RULES[OUTLET_ID]
    xpaths = config["worker_xpaths"]
    
    cur.execute("UPDATE crawl_queue SET status = 'processing', last_attempt = NOW() WHERE id = %s", (q_id,))
    conn.commit()

    try:
        # JITTER: Wait 5 to 15 seconds to emulate human reading speed
        time.sleep(random.uniform(5.0, 15.0)) 
        
        # Select a random User-Agent for this request
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        
        resp = session.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        
        utf8_parser = html.HTMLParser(encoding='utf-8')
        tree = html.fromstring(resp.content, parser=utf8_parser)
        
        title_elem = tree.xpath(xpaths["title"])
        title = title_elem[0].strip() if title_elem else "Unknown Title"
        
        content_list = tree.xpath(xpaths["content"])
        content = " ".join([text.strip() for text in content_list if text.strip()])
        
        author_elem = tree.xpath(xpaths.get("author", "")) if xpaths.get("author") else None
        author = author_elem[0].strip() if author_elem else config["name"]
            
        date_elems = tree.xpath(xpaths["date"])
        parsed_datetime = None
        
        if date_elems:
            if isinstance(date_elems, list) and len(date_elems) > 1:
                joined_text = " ".join([str(e).strip() for e in date_elems if str(e).strip()])
                if joined_text: date_elems.insert(0, joined_text)

            for el in date_elems:
                text_val = str(el).strip()
                if not text_val: continue
                parsed_attempt = config["date_parser"](text_val)
                if parsed_attempt:
                    parsed_datetime = parsed_attempt
                    break

        if parsed_datetime:
            cur.execute("""
                INSERT INTO articles (outlet_id, url, url_hash, title, content_text, authors, published_at, queue_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url_hash) DO NOTHING
            """, (
                OUTLET_ID, url, hashlib.md5(url.encode()).hexdigest(), 
                title, content, [author], 
                parsed_datetime, q_id
            ))
            cur.execute("UPDATE crawl_queue SET status = 'completed' WHERE id = %s", (q_id,))
            print(f"✅ Outlet {OUTLET_ID} Worker: SAVED {url}")
        else:
            cur.execute("UPDATE crawl_queue SET status = 'failed' WHERE id = %s", (q_id,))
            print(f"❌ Outlet {OUTLET_ID} Worker: PARSE FAILED for {url}")

    except Exception as e:
        cur.execute("UPDATE crawl_queue SET status = 'failed', retry_count = retry_count + 1 WHERE id = %s", (q_id,))
        print(f"⚠️ Outlet {OUTLET_ID} Worker Error on {url}: {e}")
    
    conn.commit()
    return True

if __name__ == "__main__":
    print(f"Worker for Outlet {OUTLET_ID} started.")
    conn = psycopg2.connect(**DB_PARAMS)
    while True:
        work_done = process_next_article(conn)
        if not work_done:
            time.sleep(60)
import os
import time
import random
import psycopg2
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from lxml import html
import hashlib
from datetime import datetime, timedelta
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

# --- User Agents ---
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0'
]

# --- RESILIENT SESSION CONFIGURATION ---
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[500, 502, 503, 504],
    raise_on_status=False
)
session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
session.mount("http://", HTTPAdapter(max_retries=retry_strategy))


def get_url_hash(url):
    return hashlib.md5(url.encode('utf-8')).hexdigest()


def discover_page(conn, task_id, target_val, cat_key):
    STOP_DATE = (datetime.now() - timedelta(days=2)).date()

    cur = conn.cursor()
    config = RULES[OUTLET_ID]

    cur.execute("UPDATE backfill_tasks SET status = 'processing', updated_at = NOW() WHERE id = %s", (task_id,))
    conn.commit()

    try:
        urls_to_scrape = []
        if config["discover_type"] == "category_crawl":
            page_num = int(target_val)
            if config.get("pagination_style") == "query":
                url = f"{cat_key}?page={page_num}" if page_num > 1 else cat_key
            elif config.get("pagination_style") == "path_page":
                # Handle Gazeta de Sud style: /page/2/
                url = f"{cat_key}/page/{page_num}/" if page_num > 1 else cat_key
            else:
                url = f"{cat_key}/{page_num}" if page_num > 1 else cat_key
            urls_to_scrape = [url]
        else:
            date_obj = datetime.strptime(target_val, "%Y-%m-%d")
            next_date_obj = date_obj + timedelta(days=1)
            base_urls = config["archive_base_url"]
            if isinstance(base_urls, str):
                base_urls = [base_urls]
            urls_to_scrape = [
                b_url.format(
                    date=target_val, year=date_obj.strftime("%Y"),
                    month=date_obj.strftime("%m"), day=date_obj.strftime("%d"),
                    next_date=next_date_obj.strftime("%Y-%m-%d")
                ) for b_url in base_urls
            ]

        raw_links = []
        for scan_url in urls_to_scrape:
            print(f"Outlet {OUTLET_ID} Discoverer Scanning: {scan_url}")
            time.sleep(random.uniform(2.0, 4.0))

            headers = {'User-Agent': random.choice(USER_AGENTS)}
            resp = session.get(scan_url, headers=headers, timeout=30)
            resp.raise_for_status()

            if config["discover_type"] == "json_api":
                posts = resp.json()
                raw_links.extend([post.get("link") for post in posts if post.get("link")])
            else:
                utf8_parser = html.HTMLParser(encoding='utf-8')
                tree = html.fromstring(resp.content, parser=utf8_parser)
                xpath_rule = config.get("discover_xpath") or config.get("item_xpath")
                items = tree.xpath(xpath_rule)

                for item in items:
                    if isinstance(item, str):
                        raw_links.append(item)
                    else:
                        link_nodes = item.xpath(config["link_xpath"])
                        if link_nodes:
                            raw_links.append(link_nodes[0])

            # Process and insert links into the crawl queue
            validator = config.get("link_validator", lambda x: True)
            clean_links = []
            for link in list(set(raw_links)):
                if link.startswith('/'):
                    base_domain = scan_url.split('/')[2]
                    link = f"https://{base_domain}{link}"

                if validator(link):
                    clean_links.append(link)
                    u_hash = get_url_hash(link)
                    cur.execute("""
                        INSERT INTO crawl_queue (outlet_id, url, url_hash, priority)
                        VALUES (%s, %s, %s, 10)
                        ON CONFLICT (url_hash) DO NOTHING;
                    """, (OUTLET_ID, link, u_hash))

        # --- THE SMART PROBE (Kill Switch for Categories) ---
        if config["discover_type"] == "category_crawl" and clean_links:
            reached_stop_date = False

            # Loop backward through the links to find the oldest article on the page
            for probe_link in reversed(clean_links):
                try:
                    print(f"Outlet {OUTLET_ID} Probing Boundary Date on: {probe_link}")
                    time.sleep(random.uniform(1.5, 3.0))

                    probe_headers = {'User-Agent': random.choice(USER_AGENTS)}
                    probe_resp = session.get(probe_link, headers=probe_headers, timeout=30)
                    utf8_parser = html.HTMLParser(encoding='utf-8')
                    probe_tree = html.fromstring(probe_resp.content, parser=utf8_parser)
                    date_elems = probe_tree.xpath(config["worker_xpaths"]["date"])

                    parsed_boundary_date = None
                    if date_elems:
                        if isinstance(date_elems, list) and len(date_elems) > 1:
                            joined_text = " ".join([str(e).strip() for e in date_elems if str(e).strip()])
                            if joined_text:
                                date_elems.insert(0, joined_text)

                        for el in date_elems:
                            text_val = str(el).strip()
                            if not text_val:
                                continue
                            parsed_attempt = config["date_parser"](text_val)
                            if parsed_attempt:
                                parsed_boundary_date = parsed_attempt.date()
                                break

                    if parsed_boundary_date:
                        print(f"--> Boundary Date Found: {parsed_boundary_date} | Kill-switch at: {STOP_DATE}")
                        if parsed_boundary_date < STOP_DATE:
                            reached_stop_date = True
                        break  # Successfully found a date, stop probing
                except Exception as e:
                    print(f"Probe failed on {probe_link}. Error: {repr(e)}")
                    continue

            # Spawning decision
            if not reached_stop_date:
                next_page = int(target_val) + 1
                cur.execute("""
                    INSERT INTO backfill_tasks (outlet_id, target_value, category_key, status)
                    VALUES (%s, %s, %s, 'pending')
                    ON CONFLICT (outlet_id, target_value, category_key) DO NOTHING;
                """, (OUTLET_ID, str(next_page), cat_key))
            else:
                print(f"🛑 Outlet {OUTLET_ID} Reached kill-switch date ({STOP_DATE}). Halting category chain.")

        cur.execute("UPDATE backfill_tasks SET status = 'completed' WHERE id = %s", (task_id,))
        conn.commit()

    except Exception as e:
        conn.rollback()
        cur.execute("UPDATE backfill_tasks SET status = 'failed' WHERE id = %s", (task_id,))
        conn.commit()
        print(f"Error processing task {task_id}: {e}")


if __name__ == "__main__":
    print(f"Discoverer for Outlet {OUTLET_ID} starting...")
    conn = psycopg2.connect(**DB_PARAMS)

    with conn.cursor() as cur:
        cur.execute("SELECT heal_stuck_tasks();")
    conn.commit()

    while True:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, target_value, category_key FROM backfill_tasks
                WHERE outlet_id = %s AND status = 'pending'
                ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED;
            """, (OUTLET_ID,))
            task = cur.fetchone()

        if task:
            discover_page(conn, *task)
        else:
            conn.rollback()
            print(f"Outlet {OUTLET_ID} Discoverer: No tasks. Idling 1 min...")
            time.sleep(60)
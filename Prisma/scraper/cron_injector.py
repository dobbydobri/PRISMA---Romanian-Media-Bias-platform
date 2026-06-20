import os
import time
import psycopg2
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

def inject_front_pages():
    conn = None
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        cur.execute("DELETE FROM backfill_tasks WHERE status IN ('completed', 'failed');")

        injected_count = 0
        skipped_count = 0

        for outlet_id, config in RULES.items():
            if config["discover_type"] == "category_crawl":
                for base_category in config["base_categories"]:

                    cur.execute("""
                        INSERT INTO backfill_tasks (outlet_id, target_value, category_key, status)
                        SELECT %s, '1', %s, 'pending'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM backfill_tasks
                            WHERE outlet_id = %s
                            AND category_key = %s
                            AND status IN ('pending', 'processing')
                        )
                        ON CONFLICT (outlet_id, target_value, category_key) DO NOTHING;
                    """, (outlet_id, base_category, outlet_id, base_category))

                    if cur.rowcount > 0:
                        injected_count += 1
                    else:
                        skipped_count += 1

        conn.commit()
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✓ Cycle complete. "
            f"Injected: {injected_count} | Skipped (still active): {skipped_count}"
        )

    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✗ Injection failed: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    print("Starting 3-Hour Cron Injector...")
    # Fire an immediate injection on startup so discoverers wake up right away
    inject_front_pages()

    while True:
        time.sleep(3 * 60 * 60)  # Sleep for 3 hours
        inject_front_pages()
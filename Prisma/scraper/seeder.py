import psycopg2
from datetime import datetime, timedelta
from outlet_rules import RULES
import os
from dotenv import load_dotenv
load_dotenv()

def _fail(var):
    raise EnvironmentError(f"Required env var '{var}' not set")

DB_PARAMS = {
    "dbname":   os.getenv("DB_NAME", "media_bias_db"),
    "user":     os.getenv("DB_USER") or _fail("DB_USER"),
    "password": os.getenv("DB_PASSWORD") or _fail("DB_PASSWORD"),
    "host":     "localhost",
    "port":     5433,
}

def seed_production_backfill():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    
    # --- CONFIGURATION ---
    start_date = datetime(2024, 1, 1)
    end_date = datetime.now()
    
    print(f"🚀 Starting Production Seed: {start_date.date()} to {end_date.date()}")

    # --- 1. Seed Date-Based Outlets (Group A: IDs 1, 2, 3) ---
    date_outlets = [1, 2, 3]
    for o_id in date_outlets:
        current = start_date
        print(f"Adding dates for Outlet {o_id} ({RULES[o_id]['name']})...")
        
        batch_tasks = []
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            batch_tasks.append((o_id, date_str))
            current += timedelta(days=1)
        
        # Using execute_batch or many-inserts is faster for 800+ days
        cur.executemany("""
            INSERT INTO backfill_tasks (outlet_id, target_value)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
        """, batch_tasks)
        conn.commit()
    
    # --- 2. Seed Category-Based Outlets (Group B: IDs 4, 5, 6) ---
    category_outlets = [4, 5, 6]
    for o_id in category_outlets:
        config = RULES[o_id]
        print(f"Verifying initial categories for {config['name']}...")
        for cat_url in config["base_categories"]:
            cur.execute("""
                INSERT INTO backfill_tasks (outlet_id, target_value, category_key)
                VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
            """, (o_id, "1", cat_url))

    conn.commit()
    cur.close()
    conn.close()
    print("\n✅ Production Seeding Complete! Your background workers are now officially busy.")

if __name__ == "__main__":
    seed_production_backfill()
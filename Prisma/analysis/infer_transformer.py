import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import psycopg2
import psycopg2.extras
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer
from env import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DB_URL = DATABASE_URL
MODEL_DIR = Path("transformer_model")
BATCH_SIZE = 64
MAX_SEQ_LEN = 512
HEAD_TOKENS = 380
TAIL_TOKENS = 100
DB_BATCH = 500


# ── Model (must match training) ──────────────────────────────────────────────

class MultiTaskBiasClassifier(torch.nn.Module):
    """Must match training architecture exactly."""

    def __init__(self, model_name, axes_config, dropout=0.1):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name)
        hidden_size = self.backbone.config.hidden_size
        self.dropout = torch.nn.Dropout(dropout)
        self.axes_config = axes_config  # list of dicts from config.json

        self.heads = torch.nn.ModuleDict({
            ac["name"]: torch.nn.Linear(hidden_size, len(ac["classes"]))
            for ac in axes_config
        })

    def forward(self, input_ids, attention_mask):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        cls_repr = self.dropout(outputs.last_hidden_state[:, 0, :])
        return {
            ac["name"]: self.heads[ac["name"]](cls_repr)
            for ac in self.axes_config
        }


# ── Tokenization (head + tail, matches training) ─────────────────────────────

def encode_batch(titles, bodies, tokenizer):
    """Tokenize a batch with head+tail strategy."""
    all_input_ids = []
    all_attention = []

    for title, body in zip(titles, bodies):
        title = title or ""
        body = body or ""

        title_enc = tokenizer(title, add_special_tokens=False, truncation=False)
        title_ids = title_enc["input_ids"]

        body_enc = tokenizer(body, add_special_tokens=False, truncation=False)
        body_ids = body_enc["input_ids"]

        special_tokens = 3
        title_budget = min(len(title_ids), 60)
        body_budget = MAX_SEQ_LEN - special_tokens - title_budget

        if len(body_ids) <= body_budget:
            body_selected = body_ids
        else:
            head_len = min(HEAD_TOKENS, body_budget - TAIL_TOKENS)
            tail_len = body_budget - head_len
            body_selected = body_ids[:head_len] + body_ids[-tail_len:]

        cls_id = tokenizer.cls_token_id
        sep_id = tokenizer.sep_token_id

        input_ids = (
            [cls_id]
            + title_ids[:title_budget]
            + [sep_id]
            + body_selected
            + [sep_id]
        )

        attention_mask = [1] * len(input_ids)
        pad_len = MAX_SEQ_LEN - len(input_ids)
        if pad_len > 0:
            input_ids += [tokenizer.pad_token_id] * pad_len
            attention_mask += [0] * pad_len

        all_input_ids.append(input_ids)
        all_attention.append(attention_mask)

    return {
        "input_ids": torch.tensor(all_input_ids, dtype=torch.long),
        "attention_mask": torch.tensor(all_attention, dtype=torch.long),
    }


# ── Database operations ──────────────────────────────────────────────────────

def ensure_columns_exist(conn, axes_config):
    """Add transformer prediction columns if they don't exist."""
    cur = conn.cursor()
    for ac in axes_config:
        col_pred = f"tf_{ac['name']}"
        col_prob = f"tf_{ac['name']}_prob"
        col_conf = f"tf_{ac['name']}_conf"

        for col, dtype in [(col_pred, "TEXT"), (col_prob, "JSONB"), (col_conf, "REAL")]:
            cur.execute(f"""
                DO $$
                BEGIN
                    ALTER TABLE articles ADD COLUMN IF NOT EXISTS {col} {dtype};
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)

    conn.commit()
    cur.close()
    log.info("Database columns verified.")


def fetch_articles(conn, rescore: bool):
    """Fetch articles for inference."""
    where = "" if rescore else "AND tf_gov_stance IS NULL"

    cur = conn.cursor(name="inference_cursor", cursor_factory=psycopg2.extras.DictCursor)
    cur.itersize = DB_BATCH

    cur.execute(f"""
        SELECT id, title, content_text
        FROM articles
        WHERE content_text IS NOT NULL
          AND LENGTH(content_text) >= 200
          {where}
        ORDER BY id
    """)
    return cur


def store_predictions(conn, batch_results: list[dict], axes_config):
    """Write predictions to database."""
    if not batch_results:
        return

    cur = conn.cursor()

    set_parts = []
    for ac in axes_config:
        set_parts.append(f"tf_{ac['name']} = %(tf_{ac['name']})s")
        set_parts.append(f"tf_{ac['name']}_prob = %(tf_{ac['name']}_prob)s")
        set_parts.append(f"tf_{ac['name']}_conf = %(tf_{ac['name']}_conf)s")
    set_clause = ", ".join(set_parts)

    query = f"UPDATE articles SET {set_clause} WHERE id = %(id)s"
    psycopg2.extras.execute_batch(cur, query, batch_results, page_size=DB_BATCH)
    conn.commit()
    cur.close()


# ── Main inference loop ──────────────────────────────────────────────────────

def run_inference(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Device: {device}")

    with open(MODEL_DIR / "config.json") as f:
        config = json.load(f)

    axes_config = config["axes"]
    model_name = config["model_name"]

    log.info("Loading model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR / "tokenizer")
    model = MultiTaskBiasClassifier(model_name, axes_config)
    model.load_state_dict(
        torch.load(MODEL_DIR / "best_model.pt", map_location=device, weights_only=True)
    )
    model.to(device)
    model.eval()
    log.info("Model loaded.")

    conn = psycopg2.connect(DB_URL)
    ensure_columns_exist(conn, axes_config)

    cur = conn.cursor()
    where = "" if args.rescore else "AND tf_gov_stance IS NULL"
    cur.execute(f"""
        SELECT COUNT(*) FROM articles
        WHERE content_text IS NOT NULL AND LENGTH(content_text) >= 200 {where}
    """)
    total = cur.fetchone()[0]
    cur.close()
    log.info(f"Articles to score: {total:,}")

    if total == 0:
        log.info("Nothing to do.")
        conn.close()
        return

    article_cursor = fetch_articles(conn, args.rescore)
    processed = 0
    start = time.time()

    batch_ids = []
    batch_titles = []
    batch_bodies = []
    db_batch = []

    for row in article_cursor:
        batch_ids.append(row["id"])
        batch_titles.append(row["title"])
        batch_bodies.append(row["content_text"])

        if len(batch_ids) >= BATCH_SIZE:
            results = _predict_batch(
                batch_ids, batch_titles, batch_bodies,
                model, tokenizer, axes_config, device
            )
            db_batch.extend(results)

            if len(db_batch) >= DB_BATCH:
                if not args.dry_run:
                    store_predictions(conn, db_batch, axes_config)
                processed += len(db_batch)
                db_batch = []

                elapsed = time.time() - start
                rate = processed / elapsed if elapsed > 0 else 0
                log.info(f"  {processed:,} / {total:,}  ({rate:.0f} art/sec)")

            batch_ids, batch_titles, batch_bodies = [], [], []

    if batch_ids:
        results = _predict_batch(
            batch_ids, batch_titles, batch_bodies,
            model, tokenizer, axes_config, device
        )
        db_batch.extend(results)

    if db_batch:
        if not args.dry_run:
            store_predictions(conn, db_batch, axes_config)
        processed += len(db_batch)

    article_cursor.close()
    conn.close()

    elapsed = time.time() - start
    log.info(f"\nComplete. {processed:,} articles scored in {elapsed:.1f}s "
             f"({processed / elapsed:.0f} art/sec)")


def _predict_batch(ids, titles, bodies, model, tokenizer, axes_config, device):
    encoding = encode_batch(titles, bodies, tokenizer)
    input_ids = encoding["input_ids"].to(device)
    attention_mask = encoding["attention_mask"].to(device)

    use_cuda = device.type == "cuda"
    with torch.no_grad(), torch.amp.autocast("cuda", enabled=use_cuda):
        logits = model(input_ids, attention_mask)

    results = []
    for i, art_id in enumerate(ids):
        row = {"id": art_id}

        for ac in axes_config:
            probs = F.softmax(logits[ac["name"]][i], dim=-1).cpu().numpy()
            pred_idx = int(probs.argmax())
            pred_label = ac["classes"][pred_idx]
            confidence = float(probs[pred_idx])

            row[f"tf_{ac['name']}"] = pred_label
            row[f"tf_{ac['name']}_prob"] = json.dumps(
                {ac["classes"][j]: round(float(probs[j]), 4)
                 for j in range(len(ac["classes"]))},
                ensure_ascii=False
            )
            row[f"tf_{ac['name']}_conf"] = round(confidence, 4)

        results.append(row)

    return results


# ── Sanity check ─────────────────────────────────────────────────────────────

def print_outlet_summary(args):
    """Print per-outlet prediction distributions after inference."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    with open(MODEL_DIR / "config.json") as f:
        axes_config = json.load(f)["axes"]

    for ac in axes_config:
        col = f"tf_{ac['name']}"
        cur.execute(f"""
            SELECT o.name, o.outlet_type, {col}, COUNT(*)
            FROM articles a
            JOIN outlets o ON a.outlet_id = o.id
            WHERE {col} IS NOT NULL
            GROUP BY o.name, o.outlet_type, {col}
            ORDER BY o.name, {col}
        """)
        rows = cur.fetchall()
        if not rows:
            continue

        print(f"\n{'═' * 70}")
        print(f"  {ac['name']} — per-outlet distribution")
        print(f"{'═' * 70}")

        from collections import defaultdict
        outlet_dist = defaultdict(lambda: defaultdict(int))
        outlet_types = {}
        for outlet, otype, label, count in rows:
            outlet_dist[outlet][label] = count
            outlet_types[outlet] = otype

        classes = ac["classes"]
        header = f"{'Outlet':<25} {'Type':<20} " + "".join(f"{c:>14}" for c in classes)
        print(header)
        print("-" * len(header))

        for outlet in sorted(outlet_dist):
            total = sum(outlet_dist[outlet].values())
            parts = []
            for c in classes:
                n = outlet_dist[outlet].get(c, 0)
                pct = n / total * 100 if total else 0
                parts.append(f"{n:>5} ({pct:4.1f}%)")
            print(f"{outlet:<25} {outlet_types[outlet]:<20} {''.join(parts)}")

    cur.close()
    conn.close()


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PRISMA transformer inference")
    parser.add_argument("--rescore", action="store_true",
                        help="Rescore all articles (not just unscored)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run inference without writing to DB")
    parser.add_argument("--summary", action="store_true",
                        help="Print per-outlet distribution summary")
    args = parser.parse_args()

    if args.summary:
        print_outlet_summary(args)
    else:
        run_inference(args)
import argparse
import json
import logging
import time
from collections import defaultdict
from pathlib import Path

import psycopg2
import psycopg2.extras
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer, logging as hf_logging
from env import DATABASE_URL

hf_logging.set_verbosity_error()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DB_URL      = DATABASE_URL
MODEL_DIR   = Path("transformer_model")
BATCH_SIZE  = 64        
PAGE_SIZE   = 500       
DB_BATCH    = 500       
MAX_SEQ_LEN = 512
HEAD_TOKENS = 380
TAIL_TOKENS = 100


# ── Model (must match training architecture exactly) ─────────────────────────

class MultiTaskBiasClassifier(torch.nn.Module):
    def __init__(self, model_name, axes_config, dropout=0.1):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name)
        hidden_size = self.backbone.config.hidden_size
        self.dropout = torch.nn.Dropout(dropout)
        self.axes_config = axes_config

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


# ── Tokenization ──────────────────────────────────────────────────────────────

def encode_batch(titles, bodies, tokenizer):
    """Head+tail tokenization — must match training exactly."""
    all_input_ids = []
    all_attention  = []

    for title, body in zip(titles, bodies):
        title = title or ""
        body  = body  or ""

        title_ids = tokenizer(title, add_special_tokens=False, truncation=False)["input_ids"]
        body_ids  = tokenizer(body,  add_special_tokens=False, truncation=False)["input_ids"]

        title_budget = min(len(title_ids), 60)
        body_budget  = MAX_SEQ_LEN - 3 - title_budget  

        if len(body_ids) <= body_budget:
            body_selected = body_ids
        else:
            head_len = min(HEAD_TOKENS, body_budget - TAIL_TOKENS)
            tail_len = body_budget - head_len
            body_selected = body_ids[:head_len] + body_ids[-tail_len:]

        input_ids = (
            [tokenizer.cls_token_id]
            + title_ids[:title_budget]
            + [tokenizer.sep_token_id]
            + body_selected
            + [tokenizer.sep_token_id]
        )
        attention_mask = [1] * len(input_ids)

        pad_len = MAX_SEQ_LEN - len(input_ids)
        if pad_len > 0:
            input_ids      += [tokenizer.pad_token_id] * pad_len
            attention_mask += [0] * pad_len

        all_input_ids.append(input_ids)
        all_attention.append(attention_mask)

    return {
        "input_ids":      torch.tensor(all_input_ids, dtype=torch.long),
        "attention_mask": torch.tensor(all_attention,  dtype=torch.long),
    }


# ── Database helpers ──────────────────────────────────────────────────────────

def ensure_columns_exist(conn, axes_config):
    """Create tf_ columns if they don't already exist."""
    cur = conn.cursor()
    for ac in axes_config:
        for col, dtype in [
            (f"tf_{ac['name']}",      "TEXT"),
            (f"tf_{ac['name']}_prob", "JSONB"),
            (f"tf_{ac['name']}_conf", "REAL"),
        ]:
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


def fetch_page(conn, last_id: int, rescore: bool) -> list[dict]:
    where_rescore = "" if rescore else "AND tf_gov_stance IS NULL"
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(f"""
        SELECT id, title, content_text
        FROM articles
        WHERE id > %s
          AND content_text IS NOT NULL
          AND LENGTH(content_text) >= 200
          AND COALESCE(is_excluded, false) = false
          {where_rescore}
        ORDER BY id
        LIMIT %s
    """, (last_id, PAGE_SIZE))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def store_predictions(conn, batch_results: list[dict], axes_config):
    """Write a batch of predictions to the database."""
    if not batch_results:
        return
    set_parts = []
    for ac in axes_config:
        set_parts.append(f"tf_{ac['name']} = %(tf_{ac['name']})s")
        set_parts.append(f"tf_{ac['name']}_prob = %(tf_{ac['name']}_prob)s")
        set_parts.append(f"tf_{ac['name']}_conf = %(tf_{ac['name']}_conf)s")

    query = f"UPDATE articles SET {', '.join(set_parts)} WHERE id = %(id)s"
    cur = conn.cursor()
    psycopg2.extras.execute_batch(cur, query, batch_results, page_size=DB_BATCH)
    conn.commit()
    cur.close()


# ── Batch prediction ──────────────────────────────────────────────────────────

def predict_batch(ids, titles, bodies, model, tokenizer, axes_config, device):
    encoding       = encode_batch(titles, bodies, tokenizer)
    input_ids      = encoding["input_ids"].to(device)
    attention_mask = encoding["attention_mask"].to(device)

    use_cuda = device.type == "cuda"
    with torch.no_grad(), torch.amp.autocast("cuda", enabled=use_cuda):
        logits = model(input_ids, attention_mask)

    results = []
    for i, art_id in enumerate(ids):
        row = {"id": art_id}
        for ac in axes_config:
            probs      = F.softmax(logits[ac["name"]][i], dim=-1).cpu().numpy()
            pred_idx   = int(probs.argmax())
            pred_label = ac["classes"][pred_idx]
            confidence = float(probs[pred_idx])

            row[f"tf_{ac['name']}"]      = pred_label
            row[f"tf_{ac['name']}_prob"] = json.dumps(
                {ac["classes"][j]: round(float(probs[j]), 4)
                 for j in range(len(ac["classes"]))},
                ensure_ascii=False,
            )
            row[f"tf_{ac['name']}_conf"] = round(confidence, 4)
        results.append(row)

    return results


# ── Main inference loop ───────────────────────────────────────────────────────

def run_inference(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Device: {device}")

    with open(MODEL_DIR / "config.json") as f:
        config = json.load(f)
    axes_config = config["axes"]
    model_name  = config["model_name"]

    log.info("Loading model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR / "tokenizer")
    model     = MultiTaskBiasClassifier(model_name, axes_config)
    model.load_state_dict(
        torch.load(MODEL_DIR / "best_model.pt", map_location=device, weights_only=True)
    )
    model.to(device)
    model.eval()
    log.info("Model loaded.")

    conn = psycopg2.connect(DB_URL)
    ensure_columns_exist(conn, axes_config)

    where_rescore = "" if args.rescore else "AND tf_gov_stance IS NULL"
    cur = conn.cursor()
    cur.execute(f"""
        SELECT COUNT(*) FROM articles
        WHERE content_text IS NOT NULL
          AND LENGTH(content_text) >= 200
          AND COALESCE(is_excluded, false) = false
          {where_rescore}
    """)
    total = cur.fetchone()[0]
    cur.close()
    log.info(f"Articles to score: {total:,}")

    if total == 0:
        log.info("Nothing to do.")
        conn.close()
        return

    processed  = 0
    last_id    = 0
    db_buffer  = []
    start      = time.time()

    while True:
        page = fetch_page(conn, last_id, args.rescore)
        if not page:
            break

        last_id = page[-1]["id"]

        for offset in range(0, len(page), BATCH_SIZE):
            gpu_batch  = page[offset: offset + BATCH_SIZE]
            ids        = [r["id"]           for r in gpu_batch]
            titles     = [r["title"]        for r in gpu_batch]
            bodies     = [r["content_text"] for r in gpu_batch]

            results = predict_batch(ids, titles, bodies, model, tokenizer, axes_config, device)
            db_buffer.extend(results)

        if not args.dry_run:
            store_predictions(conn, db_buffer, axes_config)

        processed += len(db_buffer)
        db_buffer  = []

        elapsed = time.time() - start
        rate    = processed / elapsed if elapsed > 0 else 0
        log.info(f"  {processed:,} / {total:,}  ({rate:.0f} art/sec)")

    conn.close()

    elapsed = time.time() - start
    log.info(
        f"\nComplete. {processed:,} articles scored in {elapsed:.1f}s "
        f"({processed / elapsed:.0f} art/sec)"
    )


# ── Outlet summary ────────────────────────────────────────────────────────────

def print_outlet_summary(args):
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

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

        outlet_dist  = defaultdict(lambda: defaultdict(int))
        outlet_types = {}
        for outlet, otype, label, count in rows:
            outlet_dist[outlet][label] = count
            outlet_types[outlet] = otype

        classes = ac["classes"]
        header  = f"{'Outlet':<25} {'Type':<20} " + "".join(f"{c:>16}" for c in classes)
        print(header)
        print("-" * len(header))

        for outlet in sorted(outlet_dist):
            total = sum(outlet_dist[outlet].values())
            parts = []
            for c in classes:
                n   = outlet_dist[outlet].get(c, 0)
                pct = n / total * 100 if total else 0
                parts.append(f"{n:>5} ({pct:4.1f}%)")
            print(f"{outlet:<25} {outlet_types[outlet]:<20} {''.join(parts)}")

    cur.close()
    conn.close()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PRISMA transformer inference")
    parser.add_argument("--rescore",  action="store_true",
                        help="Rescore all articles, not just unscored ones")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Run inference without writing to DB")
    parser.add_argument("--summary",  action="store_true",
                        help="Print per-outlet distribution summary")
    args = parser.parse_args()

    if args.summary:
        print_outlet_summary(args)
    else:
        run_inference(args)
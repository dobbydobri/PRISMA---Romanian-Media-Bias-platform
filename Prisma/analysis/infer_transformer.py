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

# Outlets excluded from stance and eu_orientation inference —
# fact-checkers don't produce editorial framing toward political actors
FACTCHECKER_OUTLETS = {'Factual', 'Veridica'}

# Axes that should not be inferred for fact-checker outlets
FACTCHECKER_EXCLUDED_AXES = {'stance', 'eu_orientation'}


# ── Model (must match training architecture exactly) ──────────────────────────

class MultiTaskBiasClassifier(torch.nn.Module):
    def __init__(self, model_name, axes_config, dropout=0.1):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name)
        hidden_size   = self.backbone.config.hidden_size
        self.dropout  = torch.nn.Dropout(dropout)
        # Stance head uses higher dropout — must match training
        self.stance_dropout = torch.nn.Dropout(0.3)
        self.axes_config    = axes_config

        self.heads = torch.nn.ModuleDict({
            ac["name"]: torch.nn.Linear(hidden_size, len(ac["classes"]))
            for ac in axes_config
        })

    def forward(self, input_ids, attention_mask):
        outputs  = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        cls_repr = outputs.last_hidden_state[:, 0, :]
        result   = {}
        for ac in self.axes_config:
            if ac["name"] == "stance":
                result[ac["name"]] = self.heads[ac["name"]](self.stance_dropout(cls_repr))
            else:
                result[ac["name"]] = self.heads[ac["name"]](self.dropout(cls_repr))
        return result


# ── Tokenization ──────────────────────────────────────────────────────────────

def encode_batch(titles, bodies, tokenizer):
    """Head+tail tokenization — must match training exactly."""
    all_input_ids = []
    all_attention = []

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
    """Verify v4 tf_ columns exist — created by migration SQL, this is a safety check."""
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
    """Fetch a page of articles with their outlet name for fact-checker filtering."""
    where_rescore = "" if rescore else "AND a.tf_register IS NULL"
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(f"""
        SELECT a.id, a.title, a.content_text, o.name AS outlet
        FROM articles a
        JOIN outlets o ON a.outlet_id = o.id
        WHERE a.id > %s
          AND a.content_text IS NOT NULL
          AND LENGTH(a.content_text) >= 200
          AND NOT COALESCE(a.is_excluded, false)
          {where_rescore}
        ORDER BY a.id
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

def predict_batch(rows, model, tokenizer, axes_config, device):
    """
    Run inference on a batch. Fact-checker outlets get NULL for
    stance and eu_orientation — these axes are not meaningful for
    verification journalism.
    """
    ids     = [r["id"]           for r in rows]
    titles  = [r["title"]        for r in rows]
    bodies  = [r["content_text"] for r in rows]
    outlets = [r["outlet"]       for r in rows]

    encoding       = encode_batch(titles, bodies, tokenizer)
    input_ids      = encoding["input_ids"].to(device)
    attention_mask = encoding["attention_mask"].to(device)

    use_cuda = device.type == "cuda"
    with torch.no_grad(), torch.amp.autocast("cuda", enabled=use_cuda):
        logits = model(input_ids, attention_mask)

    results = []
    for i, art_id in enumerate(ids):
        is_factchecker = outlets[i] in FACTCHECKER_OUTLETS
        row = {"id": art_id}

        for ac in axes_config:
            axis_name = ac["name"]

            # Fact-checkers: null out stance and eu_orientation
            if is_factchecker and axis_name in FACTCHECKER_EXCLUDED_AXES:
                row[f"tf_{axis_name}"]      = None
                row[f"tf_{axis_name}_prob"] = None
                row[f"tf_{axis_name}_conf"] = None
                continue

            probs      = F.softmax(logits[axis_name][i], dim=-1).cpu().numpy()
            pred_idx   = int(probs.argmax())
            pred_label = ac["classes"][pred_idx]
            confidence = float(probs[pred_idx])

            row[f"tf_{axis_name}"]      = pred_label
            row[f"tf_{axis_name}_prob"] = json.dumps(
                {ac["classes"][j]: round(float(probs[j]), 4)
                 for j in range(len(ac["classes"]))},
                ensure_ascii=False,
            )
            row[f"tf_{axis_name}_conf"] = round(confidence, 4)

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
    tokenizer.model_max_length = 1_000_000  # suppress length warnings
    model = MultiTaskBiasClassifier(model_name, axes_config)
    model.load_state_dict(
        torch.load(MODEL_DIR / "best_model.pt", map_location=device, weights_only=True)
    )
    model.to(device)
    model.eval()
    log.info("Model loaded.")

    conn = psycopg2.connect(DB_URL)
    ensure_columns_exist(conn, axes_config)

    # Count articles to score
    where_rescore = "" if args.rescore else "AND tf_register IS NULL"
    cur = conn.cursor()
    cur.execute(f"""
        SELECT COUNT(*) FROM articles
        WHERE content_text IS NOT NULL
          AND LENGTH(content_text) >= 200
          AND NOT COALESCE(is_excluded, false)
          {where_rescore}
    """)
    total = cur.fetchone()[0]
    cur.close()
    log.info(f"Articles to score: {total:,}")

    if total == 0:
        log.info("Nothing to do.")
        conn.close()
        return

    processed = 0
    last_id   = 0
    db_buffer = []
    start     = time.time()

    while True:
        page = fetch_page(conn, last_id, args.rescore)
        if not page:
            break

        last_id = page[-1]["id"]

        for offset in range(0, len(page), BATCH_SIZE):
            gpu_batch = page[offset: offset + BATCH_SIZE]
            results   = predict_batch(gpu_batch, model, tokenizer, axes_config, device)
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
        header  = (f"{'Outlet':<25} {'Type':<20} "
                   + "".join(f"{c:>16}" for c in classes))
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
    parser = argparse.ArgumentParser(description="PRISMA v4 transformer inference")
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
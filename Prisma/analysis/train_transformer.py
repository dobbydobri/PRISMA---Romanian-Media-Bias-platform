import argparse
import json
import logging
import random
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import psycopg2
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup
from env import DATABASE_URL

# ── Configuration ─────────────────────────────────────────────────────────────

DB_URL     = DATABASE_URL
MODEL_NAME = "xlm-roberta-base"
OUTPUT_DIR = Path("transformer_model")
MAX_SEQ_LEN  = 512
HEAD_TOKENS  = 380
TAIL_TOKENS  = 100

BATCH_SIZE       = 8
GRAD_ACCUM_STEPS = 2        
LEARNING_RATE    = 2e-5
WEIGHT_DECAY     = 0.01
WARMUP_STEPS     = 400
MAX_EPOCHS       = 8
PATIENCE         = 3
SEED             = 42

TEST_OUTLETS = ["Buletin de Bucuresti", "Gazeta de Sud"]
VAL_OUTLETS  = ["Arad24", "Factual"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Axis definitions ──────────────────────────────────────────────────────────

@dataclass
class AxisConfig:
    name: str
    classes: list[str]
    loss_type: str = "focal"       
    task_weight: float = 1.0
    focal_gamma: float = 2.0
    db_column: str = ""

    def __post_init__(self):
        if not self.db_column:
            self.db_column = self.name
        self.label2id = {c: i for i, c in enumerate(self.classes)}
        self.id2label = {i: c for i, c in enumerate(self.classes)}
        self.num_classes = len(self.classes)


AXES = [
    AxisConfig(
        name="gov_stance",
        classes=["critic", "neutru", "favorabil"],
        loss_type="focal",
        task_weight=1.5,          
        focal_gamma=2.5,           
        db_column="llm_gov_stance",
    ),
    AxisConfig(
        name="framing",
        classes=["critic", "favorabil", "investigativ"],
        loss_type="ce",            
        task_weight=1.0,
        db_column="llm_framing",
    ),
    AxisConfig(
        name="sovereignism",
        classes=["cadru_suveranist", "neutru"],
        loss_type="ce",
        task_weight=1.0,
        db_column="llm_sovereignism",
    ),
    AxisConfig(
        name="topic",
        classes=[
            "politics", "social", "culture", "economy",
            "foreign_affairs", "health", "environment",
            "justice", "technology",
        ],
        loss_type="ce",
        task_weight=0.8,
        db_column="llm_topic",
    ),
]


# ── Label mapping ─────────────────────────────────────────────────────────────

LABEL_MAP = {
    "gov_stance": {
        "critic":    "critic",
        "neutru":    "neutru",
        "favorabil": "favorabil",
    },
    "framing": {
        "critic":       "critic",
        "favorabil":    "favorabil",
        "investigativ": "investigativ",
    },
    "sovereignism": {
        "cadru_suveranist":    "cadru_suveranist",
        "neutru":              "neutru",
        "cadru_integrationist": "neutru",  
    },
    "topic": {
        "politics":       "politics",
        "social":         "social",
        "culture":        "culture",
        "economy":        "economy",
        "foreign_affairs": "foreign_affairs",
        "health":         "health",
        "environment":    "environment",
        "justice":        "justice",
        "technology":     "technology",
    },
}


# ── Utilities ─────────────────────────────────────────────────────────────────

def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def build_oversampler(articles: list[dict], axes: list[AxisConfig]) -> WeightedRandomSampler:
    """
    Proportional oversampling for gov_stance minority classes.
    favorabil (677) gets ~7x weight vs neutru (4701).
    critic (1353) gets ~3.5x weight vs neutru.
    Other axes are balanced enough to not need oversampling.
    """
    weights = []
    # Find gov_stance axis
    gov_axis = next(a for a in axes if a.name == "gov_stance")

    for art in articles:
        label_id = art["labels"]["gov_stance"]
        label_name = gov_axis.id2label[label_id]
        if label_name == "favorabil":
            weights.append(7.0)
        elif label_name == "critic":
            weights.append(3.5)
        else:
            weights.append(1.0)

    return WeightedRandomSampler(
        weights=weights,
        num_samples=len(articles),
        replacement=True,
    )


def compute_class_weights(labels: list[int], num_classes: int) -> torch.Tensor:
    """Inverse-frequency class weights, normalised so mean = 1."""
    counts = Counter(labels)
    total = len(labels)
    weights = []
    for c in range(num_classes):
        count = max(counts.get(c, 0), 1)
        weights.append(total / (num_classes * count))
    w = torch.tensor(weights, dtype=torch.float32)
    return w / w.sum() * num_classes


# ── Focal loss ────────────────────────────────────────────────────────────────

class FocalLoss(nn.Module):
    def __init__(self, alpha: Optional[torch.Tensor] = None, gamma: float = 2.0):
        super().__init__()
        self.gamma = gamma
        self.register_buffer("alpha", alpha)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce = F.cross_entropy(logits, targets, weight=self.alpha, reduction="none")
        pt = torch.exp(-ce)
        loss = ((1 - pt) ** self.gamma) * ce
        return loss.mean()


# ── Data loading ──────────────────────────────────────────────────────────────

def load_labeled_data(axes: list[AxisConfig]) -> list[dict]:
    """Load articles that have all 4 axes labeled."""
    axis_cols = ", ".join(f"a.{a.db_column}" for a in axes)

    query = f"""
        SELECT a.id, a.title, a.content_text, o.name AS outlet,
               {axis_cols}
        FROM articles a
        JOIN outlets o ON a.outlet_id = o.id
        WHERE a.llm_gov_stance IS NOT NULL
          AND a.llm_framing IS NOT NULL
          AND a.llm_sovereignism IS NOT NULL
          AND a.llm_topic IS NOT NULL
          AND a.content_text IS NOT NULL
          AND COALESCE(a.is_excluded, false) = false
          AND LENGTH(a.content_text) >= 200
    """

    log.info("Loading labeled articles from database...")
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(query)
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()

    articles = [dict(zip(columns, row)) for row in rows]
    log.info(f"Loaded {len(articles):,} labeled articles.")
    return articles


def map_labels(articles: list[dict], axes: list[AxisConfig]) -> list[dict]:
    """Apply label mapping and filter out unmappable rows."""
    valid = []
    dropped = 0
    drop_reasons = Counter()

    for art in articles:
        labels = {}
        skip = False

        for axis in axes:
            raw_val = art.get(axis.db_column)
            if raw_val is None:
                skip = True
                drop_reasons[f"{axis.name}:null"] += 1
                break

            raw_val = str(raw_val).strip().lower()

            mapping = LABEL_MAP.get(axis.name, {})
            if mapping:
                mapped = mapping.get(raw_val)
                if mapped is None:
                    skip = True
                    drop_reasons[f"{axis.name}:{raw_val}"] += 1
                    break
            else:
                mapped = raw_val

            if mapped not in axis.label2id:
                skip = True
                drop_reasons[f"{axis.name}:{mapped}_not_in_classes"] += 1
                break

            labels[axis.name] = axis.label2id[mapped]

        if skip:
            dropped += 1
            continue

        art["labels"] = labels
        valid.append(art)

    log.info(f"After label mapping: {len(valid):,} valid, {dropped:,} dropped.")
    if drop_reasons:
        for reason, count in drop_reasons.most_common(10):
            log.info(f"  drop reason: {reason} ({count})")
    return valid


def split_by_outlet(articles: list[dict], test_outlets: list[str],
                    val_outlets: list[str]) -> tuple[list, list, list]:
    """Split data by outlet for honest cross-outlet evaluation."""
    train, val, test = [], [], []
    for art in articles:
        outlet = art["outlet"]
        if outlet in test_outlets:
            test.append(art)
        elif outlet in val_outlets:
            val.append(art)
        else:
            train.append(art)

    log.info(f"Split: train={len(train):,}  val={len(val):,}  test={len(test):,}")

    # Log per-split class distributions for gov_stance
    gov_axis = next(a for a in AXES if a.name == "gov_stance")
    for name, data in [("train", train), ("val", val), ("test", test)]:
        counts = Counter(gov_axis.id2label[art["labels"]["gov_stance"]] for art in data)
        log.info(f"  {name} gov_stance: {dict(counts)}")

    return train, val, test


# ── Dataset ───────────────────────────────────────────────────────────────────

class BiasDataset(Dataset):
    def __init__(self, articles: list[dict], tokenizer, axes: list[AxisConfig]):
        self.articles = articles
        self.tokenizer = tokenizer
        self.axes = axes

    def __len__(self):
        return len(self.articles)

    def __getitem__(self, idx):
        art = self.articles[idx]
        title = art["title"] or ""
        body = art["content_text"] or ""

        encoding = self._encode_head_tail(title, body)
        label_ids = [art["labels"][axis.name] for axis in self.axes]

        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": torch.tensor(label_ids, dtype=torch.long),
        }

    def _encode_head_tail(self, title: str, body: str) -> dict:
        """
        [CLS] title [SEP] body_head ... body_tail [SEP]
        Captures both the opening lede (framing, stance) and closing
        editorial voice within 512 tokens.
        """
        title_enc = self.tokenizer(title, add_special_tokens=False, truncation=False)
        title_ids = title_enc["input_ids"]

        body_enc = self.tokenizer(body, add_special_tokens=False, truncation=False)
        body_ids = body_enc["input_ids"]

        special_tokens = 3  # CLS, SEP, SEP
        title_budget = min(len(title_ids), 60)
        body_budget = MAX_SEQ_LEN - special_tokens - title_budget

        if len(body_ids) <= body_budget:
            body_selected = body_ids
        else:
            head_len = min(HEAD_TOKENS, body_budget - TAIL_TOKENS)
            tail_len = body_budget - head_len
            body_selected = body_ids[:head_len] + body_ids[-tail_len:]

        cls_id = self.tokenizer.cls_token_id
        sep_id = self.tokenizer.sep_token_id

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
            input_ids += [self.tokenizer.pad_token_id] * pad_len
            attention_mask += [0] * pad_len

        return {
            "input_ids": torch.tensor([input_ids], dtype=torch.long),
            "attention_mask": torch.tensor([attention_mask], dtype=torch.long),
        }


# ── Model ─────────────────────────────────────────────────────────────────────

class MultiTaskBiasClassifier(nn.Module):
    """XLM-RoBERTa backbone with independent classification heads per axis."""

    def __init__(self, model_name: str, axes: list[AxisConfig], dropout: float = 0.1):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name)
        self.backbone.gradient_checkpointing_enable()

        hidden_size = self.backbone.config.hidden_size  
        self.dropout = nn.Dropout(dropout)
        self.axes = axes

        self.heads = nn.ModuleDict({
            axis.name: nn.Linear(hidden_size, axis.num_classes)
            for axis in axes
        })

    def forward(self, input_ids, attention_mask):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        cls_repr = self.dropout(outputs.last_hidden_state[:, 0, :])

        logits = {
            axis.name: self.heads[axis.name](cls_repr)
            for axis in self.axes
        }
        return logits


# ── Training ──────────────────────────────────────────────────────────────────

def build_loss_functions(axes: list[AxisConfig], train_articles: list[dict],
                         device: torch.device) -> dict:
    """Build per-axis loss functions with class weights."""
    losses = {}
    for axis in axes:
        labels = [art["labels"][axis.name] for art in train_articles]
        weights = compute_class_weights(labels, axis.num_classes).to(device)

        if axis.loss_type == "focal":
            losses[axis.name] = FocalLoss(alpha=weights, gamma=axis.focal_gamma)
        else:
            losses[axis.name] = nn.CrossEntropyLoss(weight=weights)

    return losses


def evaluate(model, dataloader, axes, device) -> dict:
    """Compute per-axis macro F1 on a dataset."""
    model.eval()
    all_preds = {a.name: [] for a in axes}
    all_labels = {a.name: [] for a in axes}

    with torch.no_grad():
        for batch in dataloader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            logits = model(input_ids, attention_mask)

            for i, axis in enumerate(axes):
                preds = logits[axis.name].argmax(dim=-1).cpu().tolist()
                golds = labels[:, i].cpu().tolist()
                all_preds[axis.name].extend(preds)
                all_labels[axis.name].extend(golds)

    from sklearn.metrics import f1_score
    results = {}
    for axis in axes:
        f1 = f1_score(all_labels[axis.name], all_preds[axis.name],
                      average="macro", zero_division=0)
        results[axis.name] = f1

    results["avg_f1"] = np.mean(list(results.values()))
    return results, all_preds, all_labels


def print_classification_reports(axes, all_preds, all_labels):
    from sklearn.metrics import classification_report
    for axis in axes:
        print(f"\n{'═' * 60}")
        print(f"  {axis.name}")
        print(f"{'═' * 60}")
        print(classification_report(
            all_labels[axis.name],
            all_preds[axis.name],
            target_names=axis.classes,
            digits=3,
            zero_division=0,
        ))


def train(args):
    set_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Device: {device}")

    # Load and prepare data
    raw_articles = load_labeled_data(AXES)
    articles = map_labels(raw_articles, AXES)

    # Print class distributions
    log.info("\n  Class distributions after mapping:")
    for axis in AXES:
        counts = Counter(art["labels"][axis.name] for art in articles)
        dist = "  ".join(f"{axis.id2label[k]}:{v}" for k, v in sorted(counts.items()))
        log.info(f"    {axis.name}: {dist}")

    # Split by outlet
    train_data, val_data, test_data = split_by_outlet(
        articles, TEST_OUTLETS, VAL_OUTLETS
    )

    # Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    train_ds = BiasDataset(train_data, tokenizer, AXES)
    val_ds   = BiasDataset(val_data, tokenizer, AXES)
    test_ds  = BiasDataset(test_data, tokenizer, AXES)

    sampler = build_oversampler(train_data, AXES)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=sampler,
                              num_workers=0, pin_memory=True)
    val_loader   = DataLoader(val_ds, batch_size=BATCH_SIZE * 2, shuffle=False,
                              num_workers=0, pin_memory=True)
    test_loader  = DataLoader(test_ds, batch_size=BATCH_SIZE * 2, shuffle=False,
                              num_workers=0, pin_memory=True)

    # Model
    model = MultiTaskBiasClassifier(MODEL_NAME, AXES).to(device)
    log.info(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

    # Optimizer + scheduler
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE,
                                  weight_decay=WEIGHT_DECAY)
    total_steps = (len(train_loader) // GRAD_ACCUM_STEPS) * MAX_EPOCHS
    scheduler = get_linear_schedule_with_warmup(optimizer, WARMUP_STEPS, total_steps)

    # Loss functions
    loss_fns = build_loss_functions(AXES, train_data, device)

    # Training loop
    scaler = torch.amp.GradScaler("cuda")
    best_f1 = 0.0
    patience_counter = 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        epoch_loss = 0.0
        optimizer.zero_grad()

        for step, batch in enumerate(train_loader, 1):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            with torch.amp.autocast("cuda"):
                logits = model(input_ids, attention_mask)

                total_loss = torch.tensor(0.0, device=device)
                for i, axis in enumerate(AXES):
                    axis_labels = labels[:, i]
                    axis_logits = logits[axis.name]
                    axis_loss = loss_fns[axis.name](axis_logits, axis_labels)
                    total_loss = total_loss + axis.task_weight * axis_loss

                total_loss = total_loss / GRAD_ACCUM_STEPS

            scaler.scale(total_loss).backward()

            if step % GRAD_ACCUM_STEPS == 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scale_before = scaler.get_scale()
                scaler.step(optimizer)
                scaler.update()
                scale_after = scaler.get_scale()
                if scale_after >= scale_before:
                    scheduler.step()
                optimizer.zero_grad()

            epoch_loss += total_loss.item() * GRAD_ACCUM_STEPS

        avg_loss = epoch_loss / len(train_loader)

        # Validation
        val_results, _, _ = evaluate(model, val_loader, AXES, device)
        val_f1 = val_results["avg_f1"]

        log.info(
            f"Epoch {epoch}/{MAX_EPOCHS}  loss={avg_loss:.4f}  "
            f"val_avg_F1={val_f1:.4f}  "
            + "  ".join(f"{a.name}={val_results[a.name]:.3f}" for a in AXES)
        )

        # Early stopping
        if val_f1 > best_f1:
            best_f1 = val_f1
            patience_counter = 0
            torch.save(model.state_dict(), OUTPUT_DIR / "best_model.pt")
            tokenizer.save_pretrained(OUTPUT_DIR / "tokenizer")
            config = {
                "model_name": MODEL_NAME,
                "axes": [
                    {"name": a.name, "classes": a.classes, "db_column": a.db_column}
                    for a in AXES
                ],
            }
            with open(OUTPUT_DIR / "config.json", "w") as f:
                json.dump(config, f, indent=2)
            log.info(f"  ↑ New best model saved (F1={best_f1:.4f})")
        else:
            patience_counter += 1
            if patience_counter >= PATIENCE:
                log.info(f"Early stopping at epoch {epoch}.")
                break

    # Final test evaluation
    log.info("\n" + "=" * 60)
    log.info("Final evaluation on test set (held-out outlets)")
    log.info("=" * 60)

    model.load_state_dict(torch.load(OUTPUT_DIR / "best_model.pt", weights_only=True))
    test_results, test_preds, test_labels = evaluate(model, test_loader, AXES, device)

    log.info(f"Test avg F1: {test_results['avg_f1']:.4f}")
    for axis in AXES:
        log.info(f"  {axis.name}: {test_results[axis.name]:.4f}")

    print_classification_reports(AXES, test_preds, test_labels)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PRISMA multi-task bias classifier")
    parser.add_argument("--evaluate-only", action="store_true",
                        help="Only evaluate the saved model on test set")
    args = parser.parse_args()

    if args.evaluate_only:
        set_seed(SEED)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        raw_articles = load_labeled_data(AXES)
        articles = map_labels(raw_articles, AXES)

        _, _, test_data = split_by_outlet(articles, TEST_OUTLETS, VAL_OUTLETS)

        tokenizer   = AutoTokenizer.from_pretrained(OUTPUT_DIR / "tokenizer")
        test_ds     = BiasDataset(test_data, tokenizer, AXES)
        test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE * 2,
                                 shuffle=False, num_workers=0)

        model = MultiTaskBiasClassifier(MODEL_NAME, AXES).to(device)
        model.load_state_dict(
            torch.load(OUTPUT_DIR / "best_model.pt",
                       map_location=device, weights_only=True)
        )

        log.info("Evaluating saved model on test set...")
        test_results, test_preds, test_labels = evaluate(model, test_loader, AXES, device)

        log.info(f"Test avg F1: {test_results['avg_f1']:.4f}")
        for axis in AXES:
            log.info(f"  {axis.name}: {test_results[axis.name]:.4f}")

        print_classification_reports(AXES, test_preds, test_labels)
    else:
        train(args)
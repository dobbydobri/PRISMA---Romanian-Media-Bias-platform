import os
import sys
import time
import subprocess
import logging
import argparse
import atexit
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from env import DATABASE_URL, OLLAMA_BASE_URL

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ROOT    = Path(__file__).resolve().parent.parent   
COMPOSE_ROOT    = PROJECT_ROOT.parent                      
PID_FILE        = COMPOSE_ROOT / "coordinator.pid"
LOG_FILE        = COMPOSE_ROOT / "coordinator.log"

DB_URL = DATABASE_URL

OLLAMA_HOST = OLLAMA_BASE_URL

GPU_SERVICES = ["embedder_service", "full_text_ner", "query_embedder"]

# Schedule intervals
FAST_CYCLE_HOURS      = 3       
CLUSTER_RUN_HOUR      = 22      
CLUSTER_EVERY_N_DAYS  = 1       
GRAPH_EVERY_N_DAYS    = 3       
POLL_INTERVAL_SECS  = 300     

# Script locations (relative to PROJECT_ROOT)
SCRIPTS = {
    "nlp_pipeline":          "analysis/nlp_pipeline.py",
    "infer_transformer":     "analysis/infer_transformer.py",

    "topical_cluster":       "clustering/topical_cluster.py",
    "cluster_events":        "clustering/cluster_events.py",
    "cluster_labels":        "clustering/cluster_labels.py",
    "cluster_centroids":     "search/build_cluster_centroids.py",

    "event_summaries":       "summaries/generate_event_summaries.py",

    "coverage_metrics":      "coverage/build_coverage_metrics.py",
    "event_diffusion":       "diffusion/build_event_diffusion.py",

    "graph_builder":         "graph/graph_builder.py",
}

# Which scripts are placeholders (not yet implemented)
PLACEHOLDERS = {
    "nlp_pipeline",
    "infer_transformer",
    "coverage_metrics",
    "event_diffusion",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("coordinator")


# ── State tracking ────────────────────────────────────────────────────────────

class CycleState:
    """Tracks when each cycle type last ran."""

    def __init__(self):
        self.last_fast_cycle: datetime | None = None
        self.last_cluster_date: datetime | None = None  
        self.last_graph_date: datetime | None = None

    def fast_due(self) -> bool:
        if self.last_fast_cycle is None:
            return True
        return datetime.now() - self.last_fast_cycle >= timedelta(hours=FAST_CYCLE_HOURS)

    def cluster_due(self) -> bool:
        now = datetime.now()
        if now.hour != CLUSTER_RUN_HOUR:
            return False
        today = now.date()
        if self.last_cluster_date == today:
            return False  
        if self.last_cluster_date is None:
            return True
        days_since = (today - self.last_cluster_date).days
        return days_since >= CLUSTER_EVERY_N_DAYS

    def graph_due(self) -> bool:
        now = datetime.now()
        if now.hour != CLUSTER_RUN_HOUR:
            return False  
        today = now.date()
        if self.last_graph_date == today:
            return False
        if self.last_graph_date is None:
            return True
        days_since = (today - self.last_graph_date).days
        return days_since >= GRAPH_EVERY_N_DAYS


# ── DB helpers ────────────────────────────────────────────────────────────────

def count_unscored_articles() -> int:
    """Count articles that have embeddings but no transformer predictions yet."""
    try:
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM articles
                WHERE embedding IS NOT NULL
                  AND pred_scored_at IS NULL
            """)
            count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        log.warning("DB check failed: %s", e)
        return 0


def count_unsummarized_clusters() -> int:
    """Count event clusters passing quality gates that lack summaries."""
    try:
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM cluster_labels cl
                WHERE cl.is_event_cluster = TRUE
                  AND cl.cluster_run_id = (SELECT MAX(id) FROM cluster_runs)
                  AND cl.outlet_count   >= 3
                  AND cl.article_count  BETWEEN 4 AND 60
                  AND (cl.date_to - cl.date_from) <= 7
                  AND NOT EXISTS (
                      SELECT 1 FROM cluster_summaries cs
                      WHERE cs.scope = 'event'
                        AND cs.cluster_run_id = cl.cluster_run_id
                        AND cs.cluster_id     = cl.cluster_id
                  )
            """)
            count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        log.warning("DB check failed: %s", e)
        return 0


# ── Execution helpers ─────────────────────────────────────────────────────────

def run_script(name: str, dry_run: bool = False) -> bool:
    """Run a Python script by its key name. Returns True on success."""
    if name in PLACEHOLDERS:
        log.info("  [SKIP] %s — placeholder, not yet implemented", name)
        return True

    rel_path = SCRIPTS.get(name)
    if rel_path is None:
        log.error("  [ERROR] Unknown script: %s", name)
        return False

    script_path = PROJECT_ROOT / rel_path
    if not script_path.exists():
        log.warning("  [SKIP] %s — file not found: %s", name, script_path)
        return False

    if dry_run:
        log.info("  [DRY-RUN] would run: python %s", script_path)
        return True

    log.info("  [RUN] %s", name)
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(script_path.parent),
            capture_output=False,
            timeout=7200,  # 2h max per script
            env={**os.environ, "DATABASE_URL": DB_URL, "OLLAMA_HOST": OLLAMA_HOST},
        )
        if result.returncode != 0:
            log.error("  [FAIL] %s exited with code %d", name, result.returncode)
            return False
        log.info("  [OK] %s", name)
        return True
    except subprocess.TimeoutExpired:
        log.error("  [TIMEOUT] %s exceeded 2h limit", name)
        return False
    except Exception as e:
        log.error("  [ERROR] %s: %s", name, e)
        return False


def docker_compose(*args, dry_run: bool = False) -> bool:
    """Run a docker compose command from the project root."""
    cmd = ["docker", "compose"] + list(args)
    if dry_run:
        log.info("  [DRY-RUN] %s", " ".join(cmd))
        return True
    log.info("  [DOCKER] %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, cwd=str(COMPOSE_ROOT), capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log.error("  docker compose failed: %s", result.stderr.strip())
            return False
        return True
    except Exception as e:
        log.error("  docker compose error: %s", e)
        return False



# ── Pipeline stages ───────────────────────────────────────────────────────────

def run_fast_cycle(dry_run: bool = False):
    """Stage 1: NLP scoring + transformer inference on new articles."""
    unscored = count_unscored_articles()
    log.info("Fast cycle: %d unscored articles", unscored)

    if unscored == 0:
        log.info("Nothing to score, skipping fast cycle.")
        return

    run_script("nlp_pipeline", dry_run)
    run_script("infer_transformer", dry_run)


def run_cluster_cycle(dry_run: bool = False):
    """Stage 2–4: Clustering + LLM summaries + post-clustering."""
    log.info("=== CLUSTER CYCLE START ===")

    log.info("--- Stage 2: Clustering ---")
    run_script("topical_cluster", dry_run)
    run_script("cluster_events", dry_run)
    run_script("cluster_labels", dry_run)
    run_script("cluster_centroids", dry_run)

    unsummarized = count_unsummarized_clusters()
    log.info("Unsummarized event clusters: %d", unsummarized)

    if unsummarized > 0:
        log.info("--- Stage 3: LLM Summaries (GPU swap) ---")
        docker_compose("stop", *GPU_SERVICES, dry_run=dry_run)
        time.sleep(10)

        summary_ok = run_script("event_summaries", dry_run)

        log.info("Waiting for Ollama to release VRAM...")
        if not dry_run:
            time.sleep(60)

        docker_compose("start", *GPU_SERVICES, dry_run=dry_run)

        if not summary_ok:
            log.warning("Summaries failed — GPU services restarted, continuing.")
    else:
        log.info("No unsummarized clusters, skipping GPU swap.")

    log.info("--- Stage 4: Post-clustering ---")
    run_script("coverage_metrics", dry_run)
    run_script("event_diffusion", dry_run)

    log.info("=== CLUSTER CYCLE DONE ===")


def run_graph_cycle(dry_run: bool = False):
    """Stage 5: Entity graph rebuild."""
    log.info("=== GRAPH REBUILD ===")
    run_script("graph_builder", dry_run)
    log.info("=== GRAPH REBUILD DONE ===")


def _write_pid():
    PID_FILE.write_text(str(os.getpid()))

def _remove_pid():
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PRISMA pipeline coordinator")
    parser.add_argument("--once", action="store_true", help="Run one pass then exit")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing")
    parser.add_argument("--cluster-now", action="store_true", help="Force a cluster cycle immediately")
    parser.add_argument("--graph-now", action="store_true", help="Force a graph rebuild immediately")
    args = parser.parse_args()

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logging.getLogger().addHandler(file_handler)

    _write_pid()
    atexit.register(_remove_pid)

    state = CycleState()

    if not args.cluster_now:
        state.last_cluster_date = datetime.now().date()
    if not args.graph_now:
        state.last_graph_date = datetime.now().date()

    log.info("PRISMA coordinator started. dry_run=%s, once=%s", args.dry_run, args.once)
    log.info("Schedule: fast=every %dh, cluster=daily at %02d:00, graph=every %dd at %02d:00",
             FAST_CYCLE_HOURS, CLUSTER_RUN_HOUR, GRAPH_EVERY_N_DAYS, CLUSTER_RUN_HOUR)

    while True:
        try:
            now = datetime.now()
            log.info("── Tick at %s ──", now.strftime("%Y-%m-%d %H:%M"))

            if state.fast_due():
                run_fast_cycle(args.dry_run)
                state.last_fast_cycle = datetime.now()

            if state.cluster_due():
                run_cluster_cycle(args.dry_run)
                state.last_cluster_date = datetime.now().date()

            if state.graph_due():
                run_graph_cycle(args.dry_run)
                state.last_graph_date = datetime.now().date()

        except Exception as e:
            log.error("Coordinator error: %s", e, exc_info=True)

        if args.once:
            log.info("--once flag set, exiting.")
            break

        log.info("Sleeping %d seconds until next tick.", POLL_INTERVAL_SECS)
        time.sleep(POLL_INTERVAL_SECS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Coordinator stopped by user.")
        sys.exit(0)
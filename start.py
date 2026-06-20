import os
import sys
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COORDINATOR_SCRIPT = ROOT / "Prisma" / "coordinator" / "coordinator.py"
PID_FILE = ROOT / "coordinator.pid"
COORD_LOG = ROOT / "coordinator.log"


def print_step(msg: str):
    print(f"\n{'─' * 60}")
    print(f"  {msg}")
    print(f"{'─' * 60}")


def check_prerequisites():
    """Verify Docker and docker compose are available."""
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=15)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[ERROR] Docker is not running. Start Docker Desktop first.")
        sys.exit(1)

    try:
        subprocess.run(["docker", "compose", "version"], capture_output=True, check=True, timeout=10)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[ERROR] docker compose not available.")
        sys.exit(1)


def is_coordinator_running() -> bool:
    if not PID_FILE.exists():
        return False
    pid = int(PID_FILE.read_text().strip())
    # Check if process is alive
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/fi", f"PID eq {pid}"],
            capture_output=True, text=True
        )
        return str(pid) in result.stdout
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def main():
    no_coord = "--no-coord" in sys.argv

    print_step("PRISMA Platform — Starting")

    print("\n[1/4] Checking prerequisites...")
    check_prerequisites()
    print("  Docker is running.")

    print("\n[2/4] Starting Docker Compose services...")
    result = subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=str(ROOT),
        timeout=900,
    )
    if result.returncode != 0:
        print("[ERROR] docker compose up failed.")
        sys.exit(1)
    print("  All containers started.")

    # 3. Wait for database health
    print("\n[3/4] Waiting for database...")
    for i in range(30):
        health = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", "prisma_postgres"],
            capture_output=True, text=True, timeout=10,
        )
        if "healthy" in health.stdout:
            print("  Database is healthy.")
            break
        time.sleep(2)
    else:
        print("[WARNING] Database health check timed out. Continuing anyway.")

    # 4. Coordinator
    if no_coord:
        print("\n[4/4] Coordinator skipped (--no-coord flag).")
    elif is_coordinator_running():
        print("\n[4/4] Coordinator is already running.")
    else:
        print("\n[4/4] Starting pipeline coordinator...")
        if sys.platform == "win32":
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                [sys.executable, str(COORDINATOR_SCRIPT)],
                cwd=str(COORDINATOR_SCRIPT.parent),
                stdout=open(COORD_LOG, "a"),
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            )
        else:
            subprocess.Popen(
                [sys.executable, str(COORDINATOR_SCRIPT)],
                cwd=str(COORDINATOR_SCRIPT.parent),
                stdout=open(COORD_LOG, "a"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        time.sleep(2)
        if PID_FILE.exists():
            pid = PID_FILE.read_text().strip()
            print(f"  Coordinator running (PID {pid}). Logs: coordinator.log")
        else:
            print("  [WARNING] Coordinator may not have started. Check coordinator.log")

    print_step("PRISMA is Up and Running")
    print(f"""
  Frontend:    http://localhost:4200
  API:         http://localhost:5170
  Database:    localhost:5433
  Coordinator: {"running" if not no_coord else "skipped"} (logs in coordinator.log)

  To stop:     python stop.py
""")


if __name__ == "__main__":
    main()
import os
import sys
import subprocess
import signal
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / "coordinator.pid"


def print_step(msg: str):
    print(f"\n{'─' * 60}")
    print(f"  {msg}")
    print(f"{'─' * 60}")


def stop_coordinator():
    """Stop the coordinator process using its PID file."""
    if not PID_FILE.exists():
        print("  Coordinator is not running (no PID file).")
        return

    pid = int(PID_FILE.read_text().strip())
    print(f"  Stopping coordinator (PID {pid})...")

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/f", "/pid", str(pid)],
                           capture_output=True, timeout=15)
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
            try:
                os.kill(pid, 0)  # check if still alive
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        print("  Coordinator stopped.")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  Coordinator already stopped (PID {pid} not found).")

    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def stop_docker():
    """Stop all Docker Compose services."""
    print("  Stopping Docker Compose services...")
    result = subprocess.run(
        ["docker", "compose", "stop"],
        cwd=str(ROOT),
        timeout=120,
    )
    if result.returncode == 0:
        print("  All containers stopped.")
    else:
        print("  [WARNING] docker compose stop returned non-zero. Check manually.")


def main():
    print_step("PRISMA Platform — Stopping")

    print("\n[1/2] Coordinator...")
    stop_coordinator()

    print("\n[2/2] Docker Compose services...")
    stop_docker()

    print_step("PRISMA is Stopped")
    print("""
  All services have been stopped. Containers are preserved (not removed).
  To restart:  python start.py
""")


if __name__ == "__main__":
    main()
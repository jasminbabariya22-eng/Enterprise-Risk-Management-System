"""
ERM Standalone Platform Launcher.
Runs all ERM services (Web Portal + Core API + AI Copilot) completely self-contained from ERM.
"""
import os
import sys
import subprocess
import time
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ERM_ROOT = Path(__file__).resolve().parent

# 1. Load ERM Unified Environment
ERM_ENV = ERM_ROOT / ".env"
if ERM_ENV.exists():
    load_dotenv(ERM_ENV, override=True)

# 2. Detect Local Virtual Environment inside ERM
candidates = [
    ERM_ROOT / "myenv" / "Scripts" / "python.exe",
    ERM_ROOT / ".venv" / "Scripts" / "python.exe",
]

VENV_PYTHON = None
for c in candidates:
    if c.exists():
        # Check if uvicorn or fastapi is installed in this venv
        try:
            res = subprocess.run([str(c), "-c", "import fastapi, flask, psycopg2"], capture_output=True)
            if res.returncode == 0:
                VENV_PYTHON = c
                break
        except Exception:
            pass

if not VENV_PYTHON:
    VENV_PYTHON = Path(sys.executable)

# 3. Configure Execution Environment with PYTHONPATH
env = os.environ.copy()
env["PYTHONPATH"] = str(ERM_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

web_app_dir = ERM_ROOT / "ERM_WEB_APP" if (ERM_ROOT / "ERM_WEB_APP").exists() else ERM_ROOT / "ERM_APP"
api_dir = ERM_ROOT / "ERM_API" if (ERM_ROOT / "ERM_API").exists() else ERM_ROOT / "ESM"

SERVICES = [
    {
        "name": "ERM Web Portal (Flask + AI Copilot)",
        "cmd": [str(VENV_PYTHON), "run.py"],
        "cwd": str(web_app_dir),
        "url": "http://localhost:8088"
    },
    {
        "name": "ERM Core API (FastAPI)",
        "cmd": [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"],
        "cwd": str(api_dir),
        "url": "http://localhost:8001/docs"
    }
]


def main():
    print("=" * 60)
    print("🛡️  ERM STANDALONE PLATFORM LAUNCHER")
    print("=" * 60)
    print(f"[*] ERM Root Directory : {ERM_ROOT}")
    print(f"[*] Python Interpreter : {VENV_PYTHON}")
    print(f"[*] Unified .env File  : {ERM_ENV}")
    print("[*] Status             : 100% Self-Contained Project")
    print("=" * 60)

    processes = []
    for s in SERVICES:
        print(f"\n[+] Launching '{s['name']}' on {s['url']}...")
        p = subprocess.Popen(s["cmd"], cwd=s["cwd"], env=env)
        processes.append((s["name"], p))
        time.sleep(1.5)

    print("\n" + "=" * 60)
    print("✨ All ERM Services are running!")
    print("👉 Open ERM Web Portal in Browser : http://localhost:8088")
    print("👉 ERM Core API Documentation     : http://localhost:8001/docs")
    print("=" * 60)
    print("[*] Press CTRL+C to terminate all services cleanly.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Gracefully stopping all ERM services...")
        for name, p in processes:
            p.terminate()
        print("[*] All services stopped.")


if __name__ == "__main__":
    main()

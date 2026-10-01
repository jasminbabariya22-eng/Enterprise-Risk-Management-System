"""
Standalone CLI Execution Script for ERM Copilot Guardrails & Evaluation Harness.
Usage: python ERM_Copilot/harness/run_eval.py
"""
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
ERM_ROOT = Path(__file__).resolve().parents[2]
if str(ERM_ROOT) not in sys.path:
    sys.path.insert(0, str(ERM_ROOT))

from ERM_Copilot.harness.runner import EvaluationHarness

if __name__ == "__main__":
    summary = EvaluationHarness.run_all()
    if summary["pass_rate_pct"] < 90:
        sys.exit(1)
    sys.exit(0)

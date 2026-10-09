"""
Regression Tracking and Baseline Delta Engine.
Compares evaluation metrics across versions and flags any degradation in routing, RBAC, or grounding.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional


class RegressionTracker:
    """Stores and evaluates version-over-version score baselines."""

    @staticmethod
    def compare_baselines(
        old_baseline: Dict[str, Any],
        new_results: Dict[str, Any],
        tolerance_percentage: float = 2.0
    ) -> Dict[str, Any]:
        """
        Compare old baseline with current test run.
        Flags REGRESSION DETECTED if any metric drops by more than tolerance_percentage.
        """
        regressions = []
        old_overall = float(str(old_baseline.get("overall_accuracy", "100.0")).replace("%", ""))
        new_overall = float(str(new_results.get("overall_accuracy", "100.0")).replace("%", ""))

        if new_overall < (old_overall - tolerance_percentage):
            regressions.append({
                "metric": "overall_accuracy",
                "old_value": f"{old_overall}%",
                "new_value": f"{new_overall}%",
                "drop": f"{old_overall - new_overall:.1f}%"
            })

        # Compare per-intent drops
        old_intents = old_baseline.get("accuracy_by_intent", {})
        new_intents = new_results.get("accuracy_by_intent", {})

        for intent, old_str in old_intents.items():
            if intent in new_intents:
                old_val = float(str(old_str).replace("%", ""))
                new_val = float(str(new_intents[intent]).replace("%", ""))
                if new_val < (old_val - tolerance_percentage):
                    regressions.append({
                        "metric": f"intent:{intent}",
                        "old_value": f"{old_val}%",
                        "new_value": f"{new_val}%",
                        "drop": f"{old_val - new_val:.1f}%"
                    })

        status = "REGRESSION_DETECTED" if regressions else "NO_REGRESSION"
        return {
            "status": status,
            "has_regression": bool(regressions),
            "regressions": regressions,
            "baseline_overall": f"{old_overall}%",
            "current_overall": f"{new_overall}%"
        }

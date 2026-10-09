"""
Evaluation Scoring Engine.
Computes percentage accuracy scores across Intent, Routing, Tool, RBAC, Grounding, and Hallucination Resistance.
"""
from typing import List, Dict, Any


class EvaluationScorecard:
    """Aggregates and formats evaluation results into an executive scorecard."""

    def __init__(self):
        self.total_tests: int = 0
        self.passed_tests: int = 0
        self.failed_tests: int = 0
        self.by_role: Dict[str, Dict[str, int]] = {}
        self.by_intent: Dict[str, Dict[str, int]] = {}
        self.by_failure_category: Dict[str, int] = {}
        self.metric_counts: Dict[str, int] = {
            "intent_accuracy": 0,
            "agent_accuracy": 0,
            "tool_accuracy": 0,
            "rbac_enforcement": 0,
            "grounding_accuracy": 0,
            "prompt_injection_resistance": 0,
            "hallucination_resistance": 0,
        }

    def record_result(
        self,
        test_id: str,
        role: str,
        intent: str,
        passed: bool,
        failure_category: str = None,
        metrics: Dict[str, bool] = None
    ) -> None:
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
        else:
            self.failed_tests += 1
            if failure_category:
                self.by_failure_category[failure_category] = self.by_failure_category.get(failure_category, 0) + 1

        # Role stats
        if role not in self.by_role:
            self.by_role[role] = {"passed": 0, "total": 0}
        self.by_role[role]["total"] += 1
        if passed:
            self.by_role[role]["passed"] += 1

        # Intent stats
        if intent not in self.by_intent:
            self.by_intent[intent] = {"passed": 0, "total": 0}
        self.by_intent[intent]["total"] += 1
        if passed:
            self.by_intent[intent]["passed"] += 1

        # Metric stats
        if metrics:
            for k, v in metrics.items():
                if v and k in self.metric_counts:
                    self.metric_counts[k] += 1

    def generate_summary_report(self) -> Dict[str, Any]:
        """Generate formatted summary dictionary."""
        overall_pass_rate = (self.passed_tests / max(self.total_tests, 1)) * 100.0

        role_rates = {}
        for r, data in self.by_role.items():
            role_rates[r] = f"{(data['passed'] / max(data['total'], 1)) * 100.0:.1f}%"

        intent_rates = {}
        for i, data in self.by_intent.items():
            intent_rates[i] = f"{(data['passed'] / max(data['total'], 1)) * 100.0:.1f}%"

        return {
            "total_questions": self.total_tests,
            "passed": self.passed_tests,
            "failed": self.failed_tests,
            "overall_accuracy": f"{overall_pass_rate:.1f}%",
            "accuracy_by_role": role_rates,
            "accuracy_by_intent": intent_rates,
            "failure_breakdown": self.by_failure_category,
        }

"""
Deterministic Natural Language Question Generator.
Generates reproducible test questions parameterized by role, intent, task, entities, and variation style.
"""
import random
from typing import List, Dict, Any, Optional
from tests.evaluation.taxonomy import ERMRole, ERMIntent, VariationCategory


class QuestionGenerator:
    """Reusable, seeded test question generator for ERM Copilot evaluation."""

    TEMPLATES: Dict[str, Dict[str, List[str]]] = {
        ERMIntent.GET_MY_RISKS.value: {
            VariationCategory.DIRECT.value: [
                "Show my open risks.",
                "List my assigned risks.",
                "Get my active risks.",
            ],
            VariationCategory.FORMAL.value: [
                "Please provide all open risk items assigned to my ownership.",
                "Kindly list all pending risks registered under my profile.",
            ],
            VariationCategory.INFORMAL.value: [
                "What am I dealing with right now?",
                "What's on my plate for risk management?",
            ],
            VariationCategory.SHORT.value: [
                "my risks",
                "open risks",
                "active risks",
            ],
            VariationCategory.TYPOGRAPHICAL.value: [
                "show my opne risks",
                "list my acitve risks",
                "shwo my risk reg",
            ],
            VariationCategory.ABBREVIATION.value: [
                "show active risk reg",
                "list my RO risks",
            ],
        },
        ERMIntent.GET_PENDING_APPROVALS.value: {
            VariationCategory.DIRECT.value: [
                "Show pending approvals.",
                "List risks waiting for my signoff.",
            ],
            VariationCategory.FORMAL.value: [
                "Please present the governance approval queue requiring my authorization.",
            ],
            VariationCategory.SHORT.value: [
                "pending approvals",
                "approval queue",
            ],
            VariationCategory.ABBREVIATION.value: [
                "show FH queue",
                "show RM queue",
            ],
        },
        ERMIntent.APPROVE_RISK.value: {
            VariationCategory.DIRECT.value: [
                "approve {risk_id} with remark {remark}",
                "sign off on {risk_id} remark: {remark}",
            ],
            VariationCategory.FORMAL.value: [
                "I hereby approve risk {risk_id} with the following comment: {remark}",
            ],
            VariationCategory.SHORT.value: [
                "approve {risk_id}",
            ],
        },
        ERMIntent.CREATE_RISK.value: {
            VariationCategory.DIRECT.value: [
                "create a new risk for {risk_name}",
                "save new risk about {risk_name}",
            ],
            VariationCategory.FORMAL.value: [
                "I would like to initiate the registration of a new risk: {risk_name}",
            ],
        }
    }

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_questions(
        self,
        intent: str,
        role: str = ERMRole.RISK_OWNER.value,
        entities: Optional[Dict[str, Any]] = None,
        count_per_category: int = 2
    ) -> List[Dict[str, Any]]:
        """Generate formatted test cases across available categories for an intent."""
        ents = entities or {
            "risk_id": "RSK-GAS-087",
            "risk_name": "Compressor Vibration",
            "remark": "Approved for proceeding"
        }
        category_map = self.TEMPLATES.get(intent, {})
        generated_cases = []

        for cat, templates in category_map.items():
            sampled = self.rng.sample(templates, min(len(templates), count_per_category))
            for idx, tmpl in enumerate(sampled):
                formatted_q = tmpl.format(**ents)
                generated_cases.append({
                    "test_id": f"GEN-{intent[:6]}-{cat[:4]}-{idx+1}",
                    "role": role,
                    "intent": intent,
                    "variation_category": cat,
                    "question": formatted_q,
                    "entities": ents,
                })

        return generated_cases

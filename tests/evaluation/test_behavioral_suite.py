"""
Pytest Suite for ERM Copilot AI Behavioral Evaluation.
Executes Golden Dataset, Question Generator, Multi-Turn Dialogues, RBAC Security, Hallucination, and Regression tests.
"""
import pytest
from tests.evaluation.taxonomy import ERMRole, ERMIntent
from tests.evaluation.dataset import GOLDEN_QUESTION_DATASET
from tests.evaluation.generator import QuestionGenerator
from tests.evaluation.multi_turn import MULTI_TURN_CONVERSATIONS
from tests.evaluation.security_dataset import SECURITY_EVALUATION_DATASET
from tests.evaluation.hallucination_dataset import HALLUCINATION_EVALUATION_DATASET
from tests.evaluation.runner import EvaluationRunner
from tests.evaluation.evaluator import BehavioralEvaluator
from tests.evaluation.regression import RegressionTracker
from tests.evaluation.matrix import lookup_matrix
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.agents.orchestrator.agent import ERMCopilotAgent
from ERM_Copilot.ai_harness.guardrails import HarnessGuardrails
from ERM_Copilot.ai_harness.exceptions import GuardrailViolationError


@pytest.fixture
def eval_runner():
    return EvaluationRunner()


# -----------------------------------------------------------------
# 1. Golden Natural Language Question Dataset Tests
# -----------------------------------------------------------------
@pytest.mark.evaluation
@pytest.mark.parametrize("test_case", GOLDEN_QUESTION_DATASET, ids=[tc["test_id"] for tc in GOLDEN_QUESTION_DATASET])
def test_golden_question_evaluation(eval_runner, test_case):
    result = eval_runner.run_test_case(test_case)
    assert result["passed"] is True, f"Failed test {test_case['test_id']}: {result.get('error')}"


# -----------------------------------------------------------------
# 2. Reusable Question Generator Parameterized Tests
# -----------------------------------------------------------------
@pytest.mark.evaluation
def test_question_generator_reproducibility():
    gen1 = QuestionGenerator(seed=123)
    gen2 = QuestionGenerator(seed=123)
    q1 = gen1.generate_questions(intent=ERMIntent.GET_MY_RISKS.value)
    q2 = gen2.generate_questions(intent=ERMIntent.GET_MY_RISKS.value)
    assert q1 == q2
    assert len(q1) > 0


@pytest.mark.evaluation
def test_generated_questions_execution(eval_runner):
    generator = QuestionGenerator(seed=42)
    generated_cases = generator.generate_questions(intent=ERMIntent.GET_MY_RISKS.value, count_per_category=1)
    
    for case in generated_cases:
        # Attach expected facts for evaluation
        case["expected"] = {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "key_facts": ["Gas Processing Facilities"]
        }
        res = eval_runner.run_test_case(case)
        assert res["passed"] is True, f"Generated case {case['test_id']} failed: {res.get('error')}"


# -----------------------------------------------------------------
# 3. Multi-Turn Dialogue & Context Preservation Tests
# -----------------------------------------------------------------
@pytest.mark.evaluation
def test_multi_turn_dialogue_context():
    agent = ERMCopilotAgent()
    scenario = MULTI_TURN_CONVERSATIONS[0] # Deep-dive scenario
    user_id = scenario["user_id"]
    role = scenario["role"]
    dept_id = scenario["dept_id"]

    from ERM_Copilot.agents.treatment import treatment_management_agent
    from ERM_Copilot.agents.risk_creation import risk_creation_agent
    from ERM_Copilot.agents.approval import approval_agent

    uid_str = str(user_id)
    treatment_management_agent.clear_session(uid_str)
    risk_creation_agent.clear_session(uid_str)
    approval_agent.clear_session(uid_str)

    for turn in scenario["turns"]:
        req = AgentRequest(
            message=turn["input"],
            user_id=str(user_id),
            user_role=role,
            metadata={"role": role, "user_id": str(user_id), "dept_id": dept_id, "dept_name": "Gas Processing Facilities"}
        )
        resp = agent.process(req)
        resp_text = resp.message if hasattr(resp, "message") else str(resp)

        # Check turn facts
        for fact in turn["expected_facts"]:
            assert fact.lower() in resp_text.lower(), f"Turn {turn['turn']} response missed fact '{fact}': {resp_text}"


# -----------------------------------------------------------------
# 4. Security & Prompt Injection Defense Tests
# -----------------------------------------------------------------
@pytest.mark.evaluation
@pytest.mark.parametrize("sec_case", SECURITY_EVALUATION_DATASET, ids=[sc["test_id"] for sc in SECURITY_EVALUATION_DATASET])
def test_security_dataset_enforcement(sec_case):
    agent = ERMCopilotAgent()
    uid = str(sec_case.get("user_id", 101))
    req = AgentRequest(
        message=sec_case["question"],
        user_id=uid,
        user_role=sec_case["role"],
        metadata={"role": sec_case["role"], "user_id": uid}
    )
    
    # Process through orchestrator / guardrails
    resp = agent.process(req)
    resp_text = resp.message if hasattr(resp, "message") else str(resp)

    # Evaluate security boundaries
    evaluator = BehavioralEvaluator()
    assert evaluator.evaluate_security_probe(
        {"response_text": resp_text},
        sec_case["must_not_contain"]
    ) is True


# -----------------------------------------------------------------
# 5. Hallucination Prevention Probing Tests
# -----------------------------------------------------------------
@pytest.mark.evaluation
@pytest.mark.parametrize("hal_case", HALLUCINATION_EVALUATION_DATASET, ids=[hc["test_id"] for hc in HALLUCINATION_EVALUATION_DATASET])
def test_hallucination_prevention_probes(hal_case):
    agent = ERMCopilotAgent()
    req = AgentRequest(
        message=hal_case["question"],
        user_id="101",
        user_role=hal_case["role"],
        metadata={"role": hal_case["role"], "user_id": "101"}
    )
    resp = agent.process(req)
    resp_text = resp.message if hasattr(resp, "message") else str(resp)

    evaluator = BehavioralEvaluator()
    assert evaluator.evaluate_hallucination_probe(
        {"response_text": resp_text},
        probe_entity=hal_case["probe_entity"],
        must_not_invent=hal_case["must_not_invent"]
    ) is True


# -----------------------------------------------------------------
# 6. Regression Tracker & Baseline Verification
# -----------------------------------------------------------------
@pytest.mark.evaluation
def test_regression_tracker_no_regression():
    old_baseline = {
        "overall_accuracy": "98.0%",
        "accuracy_by_intent": {
            "GET_MY_RISKS": "100.0%",
            "APPROVE_RISK": "96.0%"
        }
    }
    current_results = {
        "overall_accuracy": "97.5%",
        "accuracy_by_intent": {
            "GET_MY_RISKS": "100.0%",
            "APPROVE_RISK": "96.0%"
        }
    }
    diff = RegressionTracker.compare_baselines(old_baseline, current_results, tolerance_percentage=2.0)
    assert diff["has_regression"] is False
    assert diff["status"] == "NO_REGRESSION"


@pytest.mark.evaluation
def test_regression_tracker_detects_drop():
    old_baseline = {
        "overall_accuracy": "98.0%",
        "accuracy_by_intent": {
            "GET_MY_RISKS": "100.0%",
            "APPROVE_RISK": "96.0%"
        }
    }
    degraded_results = {
        "overall_accuracy": "91.0%",
        "accuracy_by_intent": {
            "GET_MY_RISKS": "90.0%",
            "APPROVE_RISK": "88.0%"
        }
    }
    diff = RegressionTracker.compare_baselines(old_baseline, degraded_results, tolerance_percentage=2.0)
    assert diff["has_regression"] is True
    assert diff["status"] == "REGRESSION_DETECTED"
    assert len(diff["regressions"]) >= 1

# Phase 1A — Repository Discovery and Baseline Report

**Project:** MASS ERM Copilot — Agentic State Management & PostgreSQL Checkpointing  
**Audit & Discovery Date:** 2026-10-09  
**Target Repository:** `Enterprise-Risk-Management-System` (MASS ERM Copilot)  
**Environment:** Windows (win32), Python 3.14.6, pytest 9.1.1, PostgreSQL (Schema `ers`), LangGraph  

---

## 1. Existing Architecture & Request Flow

The current MASS ERM Copilot architecture processes conversational requests along the following path:

```
[Authenticated User / Frontend UI]
             │
             ▼
[FastAPI Gateway / Chat Endpoint]
  (JWT Identity & Claims Extraction → User ID, Role, Department)
             │
             ▼
[ERM AI Harness (`ERMAIHarness.run`)]
  ├─ 1. HarnessContext Verification (Authentication, Immutability)
  ├─ 2. Input Guardrails (`HarnessGuardrails.validate_input` - prompt injection, SQLi)
  ├─ 3. Action Cancellation Detection
  ├─ 4. Observability Tracer (`observability_tracer.start_span`)
             │
             ▼
[Master Orchestrator (`ERMCopilotAgent.process`)]
  ├─ Query Transformation (`QueryTransformer.transform` - acronym expansion)
  ├─ Session Key Resolution (`{user_id}::{session_id}`)
  ├─ Subagent Delegation Checks:
  │    ├─ TreatmentManagementAgent (Action plans & progress)
  │    ├─ RiskCreationAgent (14-step risk formulation wizard)
  │    └─ ApprovalWorkflowAgent (LangGraph approval workflow)
  ├─ Tier-1 High-Speed Response Cache (`erm_response_cache`)
  └─ Direct Intent Routing & Formatting (`response_formatter`)
             │
             ▼
[Governed Tool Registry (`tool_registry.py`)]
  ├─ RBAC Policy Check (`is_role_authorized_for_tool`)
  ├─ Argument Validation & Pydantic Schemas
  ├─ Human-in-the-Loop Confirmation Gate (`ConfirmationManager`)
  └─ Handlers execute against `erm_db` (PostgreSQL Database Service)
             │
             ▼
[PostgreSQL Database (`ers` schema)]
  Tables: `risk_register`, `risk_description`, `risk_treatment`, `mst_department`, `mst_users`, etc.
             │
             ▼
[Output Guardrails (`HarnessGuardrails.sanitize_output`)]
  Masks bearer tokens, credentials, connection strings
             │
             ▼
[User Response (`AgentResponse` with trace metadata)]
```

---

## 2. Existing Agents, Tools, and Workflow Graphs

### 2.1 Agents
1. **Master Orchestrator (`ERMCopilotAgent`):**
   - *Source:* `ERM_Copilot/agents/orchestrator/agent.py`
   - *Role:* Routes queries, performs regex and intent classification, checks active subagent sessions, and formats markdown responses with interactive UI buttons.
2. **Risk Creation Agent (`RiskCreationAgent`):**
   - *Source:* `ERM_Copilot/agents/risk_creation/agent.py`
   - *State Model:* 14-step conversational state machine (`INITIATION` → `CO_OWNER` → `DESCRIPTION` → `INHERENT_ASSESSMENT` → `MITIGATION` → `CURRENT_ASSESSMENT` → `ACTION_PLAN` → `ACTION_OWNER` → `TARGET_DATE` → `STATUS` → `VALIDATE` → `PREVIEW` → `CONFIRM` → `PERSIST`).
3. **Treatment Management Agent (`TreatmentManagementAgent`):**
   - *Source:* `ERM_Copilot/agents/treatment/agent.py`
   - *State Model:* Multi-turn action planning wizard, progress updates (`0-100%`), and action owner reassignments.
4. **Approval Workflow Agent (`ApprovalWorkflowAgent` / `ApprovalWorkflowGraph`):**
   - *Source:* `ERM_Copilot/agents/approval/graph.py`
   - *Graph Engine:* LangGraph `StateGraph(ApprovalState)` coordinating 4-stage governance approval (`START` → `extract` → `validate` → `continue_turn` → `execute` → `END`).

### 2.2 Governed Tool Registry
*Source:* `ERM_Copilot/ai_harness/tool_registry.py`  
Contains 11 centrally declared, governed tools:
- **Read-Only / Search:** `search_risks`, `get_pending_approvals`, `get_risk_details`, `get_risk_audit_trail`, `get_dropdown_options`, `calculate_risk_assessment`.
- **State-Changing / Governed Approval:** `approve_or_reject_risk`, `save_risk`, `add_risk_treatment`, `update_treatment_progress`, `resubmit_risk`.

---

## 3. Current State-Management Implementation (The Gap)

| Component | Current State Store | Mechanism | Limitations & Vulnerabilities |
| :--- | :--- | :--- | :--- |
| **`ERMCopilotAgent`** | Stateless | None | Cannot resume or remember multi-step plans across messages without delegation. |
| **`RiskCreationAgent`** | `self.sessions: Dict[str, RiskCreationSession]` | Python in-memory `dict` | **Ephemeral:** Lost immediately on process restart or across multiple server workers. No persistent checkpointing. |
| **`TreatmentManagementAgent`** | `self.sessions: Dict[str, TreatmentSession]` | Python in-memory `dict` | **Ephemeral:** Cannot survive crashes. State is unbounded in memory. |
| **`ApprovalWorkflowAgent`** | `self._sessions: Dict[str, ApprovalState]` | Python in-memory `dict` + LangGraph in-memory nodes | **Unpersisted:** If an approval requires a second turn for remark entry, a restart wipes the session. |

---

## 4. Existing Security & Confirmation Boundaries

1. **Identity & Context:** `HarnessContext` (`ERM_Copilot/ai_harness/context.py`) captures immutable `user_id`, `user_role`, `dept_id`, `dept_name`, `email`, and `request_id`.
2. **RBAC Policy Enforcement:** `is_role_authorized_for_tool` in `policies.py` checks normalized roles against canonical allowed lists before tool execution.
3. **Action Fingerprinting & Confirmation Tokens:**
   - `ConfirmationManager` (`ERM_Copilot/ai_harness/confirmation.py`) creates deterministic SHA-256 HMAC fingerprints of `(tool_name, sorted_arguments)`.
   - Generates single-use tokens expiring in 300 seconds (5 minutes).
   - Replay prevention: consumed tokens are marked and rejected on reuse.
4. **Department Scoping:** Frontline roles (`Risk Owner`, `Functional Head`) are strictly scoped by `dept_id` / `dept_name`. Enterprise roles (`Risk Manager`, `Risk Head`, `Super Admin`) have global visibility.

---

## 5. Current Persistence and Database Transaction Behavior

1. **Database Service:** `ERMDatabaseService` (`ERM_Copilot/services/db_service.py`) connects via `psycopg2` to PostgreSQL on port `5433` (fallback `5432`), schema `ers`.
2. **Read vs. Write Isolation:** Read operations use `conn.set_session(readonly=True)`. Write operations use autocommit or explicit parameterized transactions.
3. **Audit History Tables:** Writes to `risk_register` and `risk_treatment` write to historical tables (`risk_register_hist`, `risk_treatment_hist`).
4. **Checkpoint Tables:** **Currently nonexistent.** There is no table dedicated to agent workflow checkpoints or LangGraph state persistence.

---

## 6. Relevant Package Versions and Compatibility Constraints

- **Python:** `3.14.6`
- **Pytest:** `9.1.1`
- **LangGraph:** Installed (`langgraph.graph.StateGraph` and `langgraph.checkpoint.base.BaseCheckpointSaver` are available).
- **Database Drivers:** `psycopg2` is installed and verified. `SQLAlchemy` is available in `ERM_API`.
- **Operating Constraints:** Windows filesystem, thread-safe connection pooling, no uncommitted blocking connections.

---

## 7. Baseline Test Execution Results

Prior to modifications, baseline execution confirmed:
- `python -m pytest tests/evaluation/ -v`: **33 passed** (including Phase 3A gap tests)
- `python -m pytest tests/ -v`: **91 passed**
- `python -m pytest -v`: **218 passed** across the full workspace

---

## 8. Missing Capabilities & Proposed Minimal Upgrades

To achieve production-grade agentic state management without rebuilding existing components:

1. **Shared Workflow State Contract (`ERM_Copilot/workflow/contracts.py`):**
   - Implement `AgentWorkflowState`, `WorkflowStatus`, `WorkflowType`, and deterministic transition validation.
2. **PostgreSQL Checkpoint Backend (`ERM_Copilot/workflow/checkpointer.py`):**
   - Create `ers.agent_workflow_checkpoints` table with optimistic locking (`state_version`), ownership enforcement (`owner_user_id`), expiration, and session key indexing.
   - Provide seamless compatibility with SQLite in-memory test fixtures.
3. **Bounded Autonomous Planner (`ERM_Copilot/workflow/planner.py`):**
   - Implement bounded multi-step reasoning (`CALL_READ_TOOL`, `DELEGATE_TO_AGENT`, `ASK_USER`, `WAIT_FOR_CONFIRMATION`, `WAIT_FOR_APPROVAL`, `RESUME_WORKFLOW`, `COMPLETE`, `FAIL_SAFELY`) with strict max-step limits (15 steps) and circular handoff detection.
4. **Agent Integration & Resume Governance:**
   - Integrate `ERMCopilotAgent`, `RiskCreationAgent`, `TreatmentManagementAgent`, and `ApprovalWorkflowAgent` with the persistent checkpointer.
   - Require full re-authentication, role re-validation, department checking, and fresh database entity verification on every resume.
5. **Idempotency & Crash Recovery:**
   - Attach idempotency tokens to state-changing operations to prevent duplicate database writes on interrupted or retried workflows.

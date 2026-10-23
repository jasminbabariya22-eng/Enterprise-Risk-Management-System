# 🛡️ Governed AI Harness & Tool Registry Documentation (`ERMAIHarness`)

---

## 📌 1. Overview & Identity

- **Core Module:** [`ERM_Copilot/ai_harness/`](file:///d:/ERM/ERM_Copilot/ai_harness/)
- **Primary Classes:**
  - [`ERMAIHarness`](file:///d:/ERM/ERM_Copilot/ai_harness/harness.py#L25): Top-level gateway entry point managing context, traces, and execution loops.
  - [`ToolRegistry`](file:///d:/ERM/ERM_Copilot/ai_harness/tool_registry.py#L30): Central directory registering all allowed tools, schemas, allowed roles, and confirmation constraints.
  - [`ExecutionCoordinator`](file:///d:/ERM/ERM_Copilot/ai_harness/execution.py#L30): Governed dispatcher executing tool handlers under strict RBAC, validation, and HMAC confirmation token checks.
  - [`ConfirmationManager`](file:///d:/ERM/ERM_Copilot/ai_harness/confirmation.py#L20): Generates and verifies cryptographically signed HMAC-SHA256 confirmation tokens.
- **Why It Matters:**
  - **Zero Direct Tool Execution:** Specialized agents cannot invoke database mutations or sensitive tools directly; all requests must pass through the Harness.
  - **Fail-Closed Security:** Rejects unauthenticated requests, mismatched roles, parameter tampering, and cross-department mutations before hitting the database.
  - **Cryptographic Anti-Tamper:** Two-phase mutations require an HMAC-SHA256 token binding the actor, role, action, target, and arguments with a 15-minute TTL.

---

## 🏛️ 2. Governed Tool Execution Pipeline

```mermaid
flowchart TD
    Req["Agent Request\n(tool_name, arguments, context)"] --> RegCheck{"Tool Registered in ToolRegistry?"}
    RegCheck -->|No| Block1["Error: Tool Not Registered (403)"]
    
    RegCheck -->|Yes| RBAC{"Caller Role in tool.allowed_roles?"}
    RBAC -->|No| Block2["Error: Role Unauthorized for Tool (403)"]
    
    RBAC -->|Yes| ParamVal{"Validate Parameters against Schema"}
    ParamVal -->|Invalid| Block3["Error: Schema Validation Failure (400)"]
    
    ParamVal -->|Valid| ConfCheck{"Is tool.requires_confirmation?"}
    
    %% Branch A: Read-Only Tool
    ConfCheck -->|No (Read-Only)| ExecHandler["Execute Tool Handler directly\n(with auto-retry on transient errors)"]
    
    %% Branch B: State-Changing Mutation
    ConfCheck -->|Yes (State-Changing)| TokenProvided{"Valid Confirmation Token Provided?"}
    TokenProvided -->|No| GenerateToken["Generate HMAC-SHA256 Token\nReturn Confirmation Preview Card"]
    TokenProvided -->|Yes| VerifyToken{"Verify HMAC Signature,\nActor, Action, Target, Arguments & Expiry"}
    
    VerifyToken -->|Signature Failed / Expired| Block4["Error: Token Invalid / Tampered / Expired"]
    VerifyToken -->|Valid| AtomicExec["Atomic State: PENDING ➔ EXECUTING\nExecute Handler in DB Transaction\nCommit & Transition to EXECUTED"]
    
    AtomicExec --> AuditLog["Append Execution Record to Audit History"]
    ExecHandler --> AuditLog
    AuditLog --> Response["Return Governed Tool Result"]
```

---

## 🛠️ 3. Complete Tool Registry Catalogue

### 3.1 Read-Only Informational Tools (`ToolCategory.READ_ONLY`)

| Tool Name | Allowed Roles | Description | Handler Function |
| :--- | :--- | :--- | :--- |
| **`search_risk_register`** | All 7 Roles | Multi-criteria search across risk register | [`erm_db.search_risks`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L320) |
| **`get_risk_details`** | All 7 Roles | Retrieves comprehensive record for a risk code | [`erm_db.get_risk_by_code`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L320) |
| **`get_risk_matrix`** | All 7 Roles | Computes 5×5 distribution matrix | [`erm_db.get_risk_matrix_distribution`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L600) |
| **`get_pending_approvals`** | Functional Head, Risk Manager, Risk Head, Admin | Lists pending sign-offs in caller's queue | [`erm_db.get_pending_approvals`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L750) |
| **`get_risk_audit_trail`** | All 7 Roles | Reconstructs complete governance lifecycle history | [`erm_db.get_risk_audit_trail`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L850) |
| **`get_department_summary`**| Management, Risk Head, Admin | Comprehensive breakdown by department | [`erm_db.get_department_risk_summary`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L1100) |
| **`get_overdue_actions`** | All 7 Roles | Lists treatment milestones past target date | [`erm_db.get_overdue_actions`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L1020) |
| **`calculate_risk_score`** | All 7 Roles | Validates $L \times I$ calculation and severity | [`erm_db.calculate_risk_score`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L550) |
| **`get_user_daily_briefing`**| All 7 Roles | Generates proactive morning task summary | [`erm_db.get_user_daily_briefing`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L120) |
| **`get_dropdown_options`** | All 7 Roles | Fetches departments, categories, owners | [`erm_db.get_dropdown_options`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L200) |
| **`list_risk_treatments`** | All 7 Roles | Retrieves active mitigation action plans | [`erm_db.get_risk_treatments`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L900) |
| **`get_treatment_details`**| All 7 Roles | Retrieves specific action plan record | [`erm_db.get_treatment_by_id`](file:///d:/ERM/ERM_Copilot/services/db_service.py#L920) |

---

### 3.2 State-Changing Governed Mutation Tools (`ToolCategory.STATE_CHANGING`)

All state-changing tools strictly enforce **Two-Phase Confirmation** (`requires_confirmation = True`) and produce cryptographic HMAC signatures:

| Tool Name | Allowed Roles | Confirmation Required? | Primary Inputs | Target DB Tables |
| :--- | :--- | :---: | :--- | :--- |
| **`create_risk`** | Risk Owner, Admin | ✅ Yes | `risk_name`, `dept_id`, `category`, `description`, `likelihood`, `impact`, `mitigation`, `action_owner_id`, `target_date` | `ers.risk_register`, `ers.risk_description`, `ers.risk_treatment` |
| **`approve_or_reject_risk`**| Functional Head, Risk Manager, Risk Head, Admin | ✅ Yes | `risk_id`, `approver_id`, `action` (`approve`/`reject`), `remark` (mandatory for reject) | `ers.risk_register`, `ers.risk_register_hist` |
| **`add_risk_treatment`** | Risk Owner, Action Owner, Admin | ✅ Yes | `risk_id`, `action_plan`, `action_owner_id`, `target_date`, `progress` | `ers.risk_treatment`, `ers.risk_register_hist` |
| **`update_treatment_progress`**| Action Owner, Risk Owner, Admin | ✅ Yes | `treatment_id`, `progress` (0-100), `status`, `remark` | `ers.risk_treatment`, `ers.risk_treatment_hist` |
| **`reassign_treatment_owner`** | Risk Owner, Functional Head, Admin | ✅ Yes | `treatment_id`, `new_owner_id`, `remark` | `ers.risk_treatment`, `ers.risk_treatment_hist` |
| **`resubmit_risk`** | Risk Owner, Admin | ✅ Yes | `risk_id`, `user_id`, `reason` | `ers.risk_register`, `ers.risk_register_hist` |

---

## 🔒 4. Cryptographic Confirmation Specification

### HMAC-SHA256 Token Formula
```python
signature_payload = f"{actor_id}:{actor_role}:{action}:{target_id}:{canonical_json(arguments)}:{expires_at}"
token = hmac.new(SECRET_KEY.encode(), signature_payload.encode(), hashlib.sha256).hexdigest()
```

### Verification Checks:
1. **Secret Integrity:** Signed using `CONFIRMATION_HMAC_SECRET` (falling back to `SECRET_KEY`).
2. **Actor & Role Binding:** Ensures the executing session matches the proposing session.
3. **Payload Anti-Tamper:** Any altered field (e.g. changing target date or progress percentage) causes a signature mismatch and immediately aborts execution.
4. **Expiry Enforcement:** Verified against UTC timestamp; expired tokens are rejected after 15 minutes.
5. **Atomic Single-Use State:** Status is updated to `EXECUTING` in a locked row before handler execution, preventing race conditions, double-clicks, and replay attacks across multiple worker threads.

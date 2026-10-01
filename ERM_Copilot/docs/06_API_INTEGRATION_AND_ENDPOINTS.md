# 🔌 API Integration & Endpoints Guide

## 1. Web Portal & Copilot Chat Endpoint

The ERM Web Portal communicates with the Copilot through a dedicated REST endpoint:

### Endpoint: `POST /api/erm/chat`

- **Protocol:** HTTP/1.1 REST
- **Content-Type:** `application/json`

#### Request Payload
```json
{
  "message": "Give department-wise risk profile summary",
  "user_id": "2",
  "user_role": "Risk Head",
  "dept_name": "All",
  "dept_id": null
}
```

#### Response Payload (`AgentResponse`)
```json
{
  "request_id": "a93bf81e-bc91-4c6e-8d2b-98f5a6b0c2e3",
  "agent_id": "erm_copilot_agent",
  "status": "success",
  "success": true,
  "response": "### 📊 Department Risk Profile Summary (Enterprise-Wide)\n\n| Department | Total Active Risks | Pending FH Review | Pending Exec Review | Fully Approved |\n| :--- | :---: | :---: | :---: | :---: |\n| **Refining Operations** | 10 | 7 ⚠️ | 1 🟣 | 2 ✅ |\n| **Health, Safety & Environment** | 1 | 0 ⚠️ | 1 🟣 | 0 ✅ |\n| **Gas Processing Facilities** | 1 | 0 ⚠️ | 1 🟣 | 0 ✅ |\n| **Information Technology & SCADA** | 1 | 0 ⚠️ | 0 🟣 | 1 ✅ |\n| **Maintenance & Engineering** | 1 | 1 ⚠️ | 0 🟣 | 0 ✅ |\n| **Enterprise Fleet Total** | **14** | **8** | **3** | **3** |",
  "metadata": {
    "intent": "DEPARTMENT_SUMMARY",
    "timestamp": "2026-09-30T17:21:54Z"
  }
}
```

---

## 2. Interactive Action Token Syntax

The frontend parser converts custom tokens in `response` into interactive UI components:

| Markdown Token | UI Rendering | Action on Click |
| :--- | :--- | :--- |
| `[btn:Label\|Command]` | Standard Blue Pill Button | Sends `Command` as a user chat message |
| `[btn-confirm:Label\|Command]` | Green Success Action Button | Requests confirmation then executes `Command` |
| `[btn-cancel:Label\|Command]` | Red Warning / Reject Button | Requests confirmation then executes `Command` |

---

## 3. Python Contract Classes (`models/contracts.py`)

```python
class AgentRequest(BaseModel):
    message: str
    user_id: Optional[str] = "5"
    user_role: Optional[str] = "Risk Owner"
    session_id: Optional[str] = None
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    request_id: str
    agent_id: str
    status: str = "success"
    success: bool = True
    response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

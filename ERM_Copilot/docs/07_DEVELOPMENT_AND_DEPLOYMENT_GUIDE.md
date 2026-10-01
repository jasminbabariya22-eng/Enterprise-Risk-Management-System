# 🚀 Development, Configuration & Deployment Guide

## 1. Prerequisites

- **Python Version:** 3.10 to 3.14
- **PostgreSQL Server:** v14+ running on port `5433` with database `MassERS`
- **FastAPI / ESM Core API:** Running on port `8001`
- **ERM Web Portal:** Running on port `8088`

---

## 2. Environment Variables Configuration

Create or verify `.env` in `d:\Chatboat\ERM\ESM\.env` or `d:\Chatboat\ERM\.env`:

```env
# --- LLM Gateway API Keys ---
GROQ_API_KEY="gsk_..."
PORTKEY_API_KEY="BjYk..."
GEMINI_API_KEY="AQ.Ab..."
MESH_API_KEY="rsk_..."

# --- PostgreSQL Connection (MassERS) ---
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_DB_ERM=MassERS
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Alethe@123
DB_SCHEMA=ers

# --- ESM FastAPI Backend ---
ESM_API_BASE_URL=http://127.0.0.1:8001
```

---

## 3. Quick Start & Execution

### Option A: Running Full ERM Platform with Services
From `d:\Chatboat\ERM`:
```powershell
python run_all_services.py
```
This starts:
- **ERM Web Portal:** `http://localhost:8088`
- **ESM Core API & Swagger Docs:** `http://localhost:8001/docs`

### Option B: Testing ERM Copilot Standalone
```powershell
python -c "
from ERM_Copilot import erm_copilot_agent, AgentRequest

req = AgentRequest(
    message='Give department-wise risk profile summary',
    user_role='Risk Head',
    user_id='2'
)
res = erm_copilot_agent.process(req)
print(res.response)
"
```

---

## 4. Troubleshooting & FAQ

### Q1: Why did the agent return empty tables or `relation "ers.risk_register" does not exist`?
- **Root Cause:** A parent directory `.env` was specifying `POSTGRES_DB=Mass` (the MASS QA bot database), which caused psycopg2 to connect to `Mass` instead of `MassERS`.
- **Resolution:** Verify in `config/settings.py` that `POSTGRES_DB` defaults to `MassERS` and environment variables from `ESM/.env` take precedence.

### Q2: What if Portkey or Groq encounters a rate limit?
- The `SmartLLMGatewayClient` automatically falls back to Groq (Tier 2) and Google Gemini (Tier 3), or outputs deterministic rule-based cards with 0% downtime.

### Q3: How do I test the 5-step conversational wizard?
- Open the Copilot in the web portal or pass the message:
  `"Save a new risk for crude distillation column corrosion"`
  and follow the interactive prompts for scoring and assignees.

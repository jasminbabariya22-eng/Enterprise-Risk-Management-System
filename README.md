# 🛡️ Enterprise Risk Management (ERM) Platform

<div align="center">

![Python Version](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-MassERS-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![LLM Gateway](https://img.shields.io/badge/AI_Copilot-Groq_|_Gemini_|_Portkey-8A2BE2?style=for-the-badge&logo=openai&logoColor=white)

<p align="center">
  <b>A mission-critical, enterprise-grade risk governance and intelligence suite tailored for plant operations, refineries, petrochemical units, and corporate governance.</b>
</p>

[🚀 Quick Start](#-quick-start--installation) •
[🏛️ System Architecture](#-system-architecture) •
[👥 Governance Roles](#-7-supported-governance-roles) •
[🤖 AI Copilot](#-ai-risk-copilot--gateway) •
[📚 Documentation](#-deep-dive-technical-documentation)

---

</div>

## 📌 Overview

The **Enterprise Risk Management (ERM) Platform** is an end-to-end, self-contained risk intelligence and compliance system. It bridges frontline industrial operations with executive decision-making through automated 4-tier approval workflows, 5×5 dynamic risk matrix calculations, real-time audit trails, and an embedded **AI Risk Copilot**.

---

## 🏛️ System Architecture

```mermaid
flowchart TB
    subgraph UI_Layer ["🌐 Frontend Web Portal (Port 8088)"]
        UI_Web["ERM Web Portal\n(Flask + Bootstrap 5 + AdminLTE)"]
        UI_Widget["Floating AI Copilot Drawer Modal"]
        UI_Heatmap["Interactive 5×5 Risk Heatmap"]
    end

    subgraph Core_API ["⚡ Core Business API (Port 8001)"]
        FastAPI_Core["FastAPI Backend Services\n(ESM Core Engine)"]
        Swagger_Docs["Swagger UI / ReDoc\n(/docs, /redoc)"]
    end

    subgraph Copilot_Engine ["🤖 AI Intelligence Engine (ERM_Copilot)"]
        Agent_Router["ERMCopilotAgent\n(Intent Router & State Machine)"]
        Risk_Wizard["5-Step Conversational Wizard"]
        Audit_Engine["Audit Trail Reconstruction"]
    end

    subgraph Gateway_Layer ["🔀 Multi-Provider LLM Gateway"]
        LLM_Router["Smart Failover Gateway"]
        Groq_LLM["Groq LLaMA 3.3 (70B Versatile)"]
        Gemini_LLM["Google Gemini 2.5 Flash"]
        Portkey_LLM["Portkey / Mesh Gateway"]
    end

    subgraph Data_Layer ["🗄️ Persistence Layer (Port 5433)"]
        PG_DB[("PostgreSQL: MassERS\n(Schema: ers)")]
    end

    UI_Web -->|REST API| FastAPI_Core
    UI_Widget -->|POST /api/erm/chat| Agent_Router
    Agent_Router --> Risk_Wizard
    Agent_Router --> Audit_Engine
    Agent_Router --> LLM_Router
    LLM_Router --> Groq_LLM
    LLM_Router -.->|Fallback| Gemini_LLM
    LLM_Router -.->|Fallback| Portkey_LLM
    FastAPI_Core --> PG_DB
    Agent_Router -->|Direct Connection| PG_DB
```

---

## 📂 Project Structure

```text
d:\ERM\
├── 🌐 ERM_WEB_APP/               # Frontend Web Portal (Flask + Bootstrap 5 + AdminLTE)
│   ├── app/                     # Controllers, views, templates, static assets, widget partials
│   ├── run.py                   # Web portal server entrypoint (Port 8088)
│   └── requirements.txt         # Frontend dependencies
│
├── 🤖 ERM_Copilot/               # Dedicated AI Risk Intelligence Engine
│   ├── agents/                  # ERMCopilotAgent, Conversational Wizard, State Machine
│   ├── config/                  # Copilot settings & environment loaders
│   ├── docs/                    # Full 7-part architectural & technical documentation
│   ├── gateway/                 # Multi-provider LLM failover gateway (Groq, Gemini, Portkey)
│   ├── models/                  # Request/Response contracts & Pydantic schemas
│   └── services/                # Direct PostgreSQL service & ESM API client
│
├── ⚡ ERM_API/                   # Core Business API Backend (FastAPI + SQLAlchemy)
│   ├── app/                     # FastAPI routers, models, schemas, core DB logic
│   ├── Dockerfile               # Backend container configuration
│   └── requirements.txt         # Backend dependencies
│
├── 📦 myenv/                     # Unified local Python 3.11 virtual environment
├── 📄 .env                       # Unified master environment configuration
├── 📄 .env.example               # Template configuration for fresh deployments
├── 📄 requirements.txt           # Master consolidated requirements for entire ERM suite
└── 🚀 start_erm.py               # One-command platform service launcher
```

---

## 👥 7 Supported Governance Roles

The platform enforces strict role-based access control (RBAC) across 4 sequential approval stages:

| Role ID | Role Name | Governance Scope | Key Capabilities |
| :---: | :--- | :--- | :--- |
| `1` | **Risk Owner (RO)** | Department / Unit | 5-step wizard risk creation, Likelihood × Impact scoring, Action Owner assignment |
| `2` | **Functional Head (FH)** | Department / Unit | Stage 2 technical evaluation, 1-click approvals, return with revision notes |
| `3` | **Risk Manager (RM)** | Cross-Department | Stage 3 mitigation adequacy audits, 4-tier matrix validation |
| `4` | **Risk Head (CRO)** | Enterprise-Wide | Stage 4 final executive approvals, 5×5 interactive heatmap monitoring |
| `5` | **Auditor** | Enterprise-Wide | Immutable audit trail reconstruction, timestamp & approver verification |
| `6` | **Management / C-Suite** | Enterprise-Wide | Executive risk profile summaries, plant hazard exposure metrics |
| `7` | **ERM Admin** | Enterprise-Wide | System health, user-department governance, workflow queues |

---

## 🤖 AI Risk Copilot & Gateway

The **ERM Copilot** provides real-time intelligent assistance directly inside the Web Portal:

- 🪄 **5-Step Conversational Risk Wizard:** Automatically guides users through Risk Title, Event Description, Impact/Likelihood categorization, Mitigation actions, and Action Owner assignment.
- 🔄 **Smart LLM Failover Gateway:** Automatically routes requests through **Groq (LLaMA 3.3 70B)**, falling back to **Google Gemini** or **Portkey** with zero downtime.
- 🔍 **Audit Trail Reconstruction:** Instant natural language query reconstruction of approval histories and compliance records.
- 📊 **Risk Matrix & Heatmap Calculations:** Real-time formula validation for $Score = Likelihood \times Impact$.

---

## 🚀 Quick Start & Installation

### 1️⃣ Prerequisites
- **Python:** `3.11.x`
- **PostgreSQL:** Version 14+ (`MassERS` database running on port `5433`)

### 2️⃣ Configure Environment
Copy the example environment template and configure your credentials:
```powershell
cp .env.example .env
```

Ensure your database connection string and LLM API keys are populated in `.env`:
```ini
DATABASE_URL=postgresql://postgres:YourPassword@localhost:5433/MassERS
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
```

### 3️⃣ Create Virtual Environment & Install Dependencies
```powershell
# Create Python 3.11 virtual environment
py -3.11 -m venv myenv

# Activate virtual environment
.\myenv\Scripts\Activate.ps1

# Install all consolidated requirements
pip install -r requirements.txt
```

### 4️⃣ Launch All Platform Services
Run the unified platform launcher:
```powershell
python start_erm.py
```

---

## 🌐 Service Endpoints

Once launched, all services are accessible locally:

| Service | URL | Description |
| :--- | :--- | :--- |
| **ERM Web Portal** | [http://localhost:8088](http://localhost:8088) | Full Web UI + Embedded AI Copilot Drawer |
| **ERM Core API Docs** | [http://localhost:8001/docs](http://localhost:8001/docs) | Interactive Swagger UI API documentation |
| **API ReDoc** | [http://localhost:8001/redoc](http://localhost:8001/redoc) | Alternative OpenAPI documentation |

---

## 📚 Deep-Dive Technical Documentation

For in-depth architectural and developer guides, explore the dedicated [`ERM_Copilot/docs/`](./ERM_Copilot/docs/) suite:

- 📘 [01. Architecture Overview](./ERM_Copilot/docs/01_ARCHITECTURE_OVERVIEW.md) — System architecture, decoupling, and high-level design.
- 🗄️ [02. Database & Schema Specifications](./ERM_Copilot/docs/02_DATABASE_AND_SCHEMA.md) — Table schemas, relations, and data dictionary.
- ⚡ [03. LLM Gateway & Smart Routing](./ERM_Copilot/docs/03_LLM_GATEWAY_ROUTING.md) — Multi-provider failover mechanics and token optimization.
- 🪄 [04. Conversational Risk Wizard Guide](./ERM_Copilot/docs/04_CONVERSATIONAL_WIZARD_GUIDE.md) — 5-step state machine workflow for risk registration.
- 🛡️ [05. Governance & Approval Workflow](./ERM_Copilot/docs/05_GOVERNANCE_AND_APPROVAL_WORKFLOW.md) — 4-stage governance pipeline and delegation rules.
- 🔌 [06. API Integration & Endpoints](./ERM_Copilot/docs/06_API_INTEGRATION_AND_ENDPOINTS.md) — Complete REST endpoint reference and request/response contracts.
- 🚢 [07. Development & Deployment Guide](./ERM_Copilot/docs/07_DEVELOPMENT_AND_DEPLOYMENT_GUIDE.md) — Production setup, Docker configurations, and maintenance.

---

<div align="center">
  <sub>Enterprise Risk Management (ERM) Platform • Industrial Risk & Compliance Suite</sub>
</div>

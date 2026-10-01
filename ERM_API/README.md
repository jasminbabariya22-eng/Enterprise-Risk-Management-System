# ERM Repository Guide

This document explains the codebase at a practical level: what it is, how it is structured, and how to run it locally.

## 1) What this project is

**ESM** is a FastAPI backend for enterprise risk management workflows. It includes:
- authentication/login,
- user + master-data management (department, role, user type),
- risk register lifecycle endpoints,
- risk description/treatment/action-follow-up flows,
- approval/status workflows,
- risk dashboard analytics endpoints.

The app is assembled in `app/main.py` by registering API routers and middleware.

## 2) Tech stack

- **Framework:** FastAPI
- **Server:** Uvicorn
- **ORM:** SQLAlchemy
- **Database driver:** psycopg2-binary (PostgreSQL)
- **Migrations:** Alembic
- **Auth utilities:** python-jose, passlib
- **Validation/settings:** pydantic + pydantic-settings

See pinned dependencies in `requirements.txt`.

## 3) Project structure

```text
app/
  api/            # Route handlers (REST endpoints)
  core/           # App config, db session, logger, security, exceptions
  models/         # SQLAlchemy models
  schemas/        # Pydantic request/response schemas
  services/       # Business/domain services
  main.py         # FastAPI app bootstrap and router wiring
logs/             # Runtime logs
MassERS_Current_Project/  # Database scripts and schema artifacts
```

## 4) App bootstrap and request lifecycle

`app/main.py`:
- creates `FastAPI()` app,
- registers all feature routers,
- configures exception handlers,
- adds HTTP middleware for request/response logging.

Middleware behavior:
- logs request method + URL + body,
- masks password text when present,
- logs status code, processing time, and response body,
- rebuilds `Response` from consumed body iterator.

## 5) Environment and configuration

Configuration is loaded from `.env` via `BaseSettings` in `app/core/config.py`.

Required keys:
- `DATABASE_URL`
- `SECRET_KEY`
- `ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`

DB setup is in `app/core/database.py`:
- `create_engine(settings.DATABASE_URL, echo=True)`
- `SessionLocal` for request-scoped DB sessions
- `get_db()` dependency for API routes

## 6) API modules (high-level)

> Prefixes/tags are defined inside each route file.

- `app/api/auth.py` → login and token issuance.
- `app/api/user.py` → user CRUD/listing.
- `app/api/department.py` → department master CRUD.
- `app/api/role.py` → role master CRUD.
- `app/api/user_type.py` → user-type master CRUD.
- `app/api/risk_api.py` → consolidated risk save/query APIs.
- `app/api/risk_register.py` → risk register CRUD/read flows.
- `app/api/risk_description.py` → risk description CRUD/read/history-related flows.
- `app/api/risk_treatment.py` → treatment CRUD/read/history APIs.
- `app/api/risk_action_followup.py` → follow-up APIs (including download/reference lookups).
- `app/api/approval.py` → approval action endpoints.
- `app/api/Status.py` → status lookup APIs.
- `app/api/risk_dashboard_api.py` → summary/charts/heatmap dashboard endpoints.

## 7) Local development quick start

1. Create/activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set `.env` with valid database and auth values.
4. Start the app:

```bash
uvicorn app.main:app --reload
python -m app.workers.email_worker
```

5. Open generated docs:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## 8) Notes and observations

- Logging is verbose and includes bodies; review this behavior for production privacy/compliance.
- Current login logic checks stored password equality directly; if moving to production hardening, ensure hashed password verification via passlib.
- The repository contains generated `__pycache__` artifacts under `app/`; these are usually excluded in source control via `.gitignore`.

---

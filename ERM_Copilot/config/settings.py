"""
Configuration and settings module for ERM Copilot.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Search and load .env: prioritize ERM root .env for complete self-contained isolation
_erm_dir = Path(__file__).resolve().parents[2]
_esm_dir = _erm_dir / "ESM"
_root_dir = _erm_dir.parent

if (_erm_dir / ".env").exists():
    load_dotenv(_erm_dir / ".env", override=True)
elif (_esm_dir / ".env").exists():
    load_dotenv(_esm_dir / ".env", override=True)
elif (_root_dir / ".env").exists():
    load_dotenv(_root_dir / ".env")


class Settings:
    # --- LLM PROVIDERS ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
    MESH_API_KEY = os.getenv("MESH_API_KEY", os.getenv("PORTKEY_API_KEY", ""))
    MESH_API_BASE_URL = os.getenv("MESH_API_BASE_URL", os.getenv("PORTKEY_GATEWAY_URL", "https://api.portkey.ai/v1"))

    # --- POSTGRESQL DATABASE (MassERS) ---
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
    POSTGRES_DB = os.getenv("POSTGRES_DB_ERM", "MassERS")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "Alethe@123")
    DB_SCHEMA = "ers"

    # --- ESM CORE API ---
    ESM_API_BASE_URL = os.getenv("ESM_API_BASE_URL", "http://127.0.0.1:8001")


settings = Settings()

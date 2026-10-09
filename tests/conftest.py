import os
import sys
from pathlib import Path

# Add root, ERM_API, and ERM_Copilot to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
ERM_API_DIR = ROOT_DIR / "ERM_API"
if str(ERM_API_DIR) not in sys.path:
    sys.path.insert(0, str(ERM_API_DIR))
ERM_COPILOT_DIR = ROOT_DIR / "ERM_Copilot"
if str(ERM_COPILOT_DIR) not in sys.path:
    sys.path.insert(0, str(ERM_COPILOT_DIR))

import pytest
from typing import Dict, Any, Generator
from unittest.mock import MagicMock, patch

from tests.fixtures.users import TEST_USERS
from tests.fixtures.risks import TEST_RISKS
from tests.fixtures.auth import get_harness_context_for_role
from tests.fixtures.database import TestDatabase
from ERM_Copilot.ai_harness.context import HarnessContext



@pytest.fixture
def test_db() -> TestDatabase:
    """Disposable isolated test database instance."""
    return TestDatabase()


@pytest.fixture
def in_memory_db(test_db: TestDatabase) -> TestDatabase:
    """Alias for test_db."""
    return test_db


@pytest.fixture
def ro_context() -> HarnessContext:
    """Risk Owner HarnessContext."""
    return get_harness_context_for_role("risk_owner")


@pytest.fixture
def fh_context() -> HarnessContext:
    """Functional Head HarnessContext."""
    return get_harness_context_for_role("functional_head")


@pytest.fixture
def rm_context() -> HarnessContext:
    """Risk Manager HarnessContext."""
    return get_harness_context_for_role("risk_manager")


@pytest.fixture
def rh_context() -> HarnessContext:
    """Risk Head HarnessContext."""
    return get_harness_context_for_role("risk_head")


@pytest.fixture
def aud_context() -> HarnessContext:
    """Auditor HarnessContext."""
    return get_harness_context_for_role("auditor")


@pytest.fixture
def admin_context() -> HarnessContext:
    """Super Admin HarnessContext."""
    return get_harness_context_for_role("super_admin")


@pytest.fixture
def mock_llm_response():
    """Mock for Portkey / LLM Gateway generating deterministic JSON or markdown."""
    with patch("ERM_Copilot.gateway.client.portkey_client.generate") as mock_gen:
        mock_gen.return_value = "Deterministic mock AI response."
        yield mock_gen

"""
Unit Tests for Query Transformer, Parsers, and Formatters.
"""
import pytest
from ERM_Copilot.transform.query_transformer import QueryTransformer
from ERM_Copilot.agents.risk_creation.tools import parse_target_date, parse_progress


@pytest.mark.unit
def test_query_transformer_acronym_expansion():
    # Expand FH -> Functional Head
    expanded_msg, meta = QueryTransformer.transform("Show pending FH approvals", "Functional Head", "Gas Processing Facilities")
    assert "functional head" in expanded_msg.lower() or "fh" in meta.get("detected_acronyms", [])

    # Expand RM -> Risk Manager
    expanded_rm, _ = QueryTransformer.transform("pending RM review", "Risk Manager", "Gas Processing Facilities")
    assert "risk manager" in expanded_rm.lower() or "rm" in expanded_rm.lower()


@pytest.mark.unit
def test_parse_target_date_variations():
    assert parse_target_date("2026-11-30") == "2026-11-30"
    assert parse_target_date("30-11-2026") == "2026-11-30"
    assert parse_target_date("30/11/2026") == "2026-11-30"
    rel_date = parse_target_date("+45 days")
    assert rel_date is not None
    assert len(rel_date) == 10


@pytest.mark.unit
def test_parse_progress_percentages():
    assert parse_progress("60%") == 60
    assert parse_progress("100 percent") == 100
    assert parse_progress("invalid") is None

"""
Unit Tests for Risk Dashboard Service aggregations, date normalization, and KPI formulas.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from ERM_API.app.services.risk_dashboard_service import (
    normalize_date_range,
    get_dashboard_summary_service,
    department_wise_risk_count,
    user_wise_risk_count,
    status_wise_Risk_Count,
    top_10_risk,
    risk_percentage_chart
)


def test_normalize_date_range_defaults():
    start_dt, end_dt = normalize_date_range()
    assert isinstance(start_dt, datetime)
    assert isinstance(end_dt, datetime)
    assert start_dt.hour == 0 and start_dt.minute == 0 and start_dt.second == 0
    assert end_dt.hour == 23 and end_dt.minute == 59 and end_dt.second == 59
    assert start_dt < end_dt


def test_normalize_date_range_iso_strings():
    start_dt, end_dt = normalize_date_range("2026-04-01", "2027-03-31")
    assert start_dt.year == 2026 and start_dt.month == 4 and start_dt.day == 1
    assert start_dt.hour == 0 and start_dt.minute == 0 and start_dt.second == 0
    assert end_dt.year == 2027 and end_dt.month == 3 and end_dt.day == 31
    assert end_dt.hour == 23 and end_dt.minute == 59 and end_dt.second == 59


def test_risk_percentage_chart_empty_dataset():
    db = MagicMock()
    # Mock query returning empty results
    db.query.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = []

    res = risk_percentage_chart(db, "2026-01-01", "2026-12-31")
    assert isinstance(res, list)
    assert len(res) == 4
    for item in res:
        assert item["percentage"] == 0.0
        assert item["count"] == 0


def test_dashboard_summary_service_calculations():
    db = MagicMock()
    
    # Mock rows returned by status aggregation
    row1 = MagicMock(status_name="Draft", total=10)
    row2 = MagicMock(status_name="Submitted to Function Head", total=10)
    row3 = MagicMock(status_name="Function Head Approved", total=15)
    row4 = MagicMock(status_name="Risk Manager Approved", total=10)
    row5 = MagicMock(status_name="Risk Head Approved (Final)", total=5)
    row6 = MagicMock(status_name="Completed", total=8)
    row7 = MagicMock(status_name="Rejected / Returned", total=2)

    db.query.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = [
        row1, row2, row3, row4, row5, row6, row7
    ]

    summary = get_dashboard_summary_service(db, "2026-04-01", "2027-03-31")
    assert summary["total"] == 60
    assert summary["open_risks"] == 20   # 10 Draft + 10 Submitted
    assert summary["in_progress"] == 15  # 15 Function Head Approved
    assert summary["completed"] == 8    # 8 Completed
    assert summary["approved"] == 15    # 10 RM + 5 RH (FH approved counted in in_progress)
    assert summary["rejected"] == 2    # 2 Rejected


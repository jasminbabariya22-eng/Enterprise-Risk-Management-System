from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# --------------------------------------------------------------------------
# Canonical records
# --------------------------------------------------------------------------

@dataclass
class RiskTreatmentRecord:
    action_plan: str
    action_owner: str = ""
    due_date: Optional[pd.Timestamp] = None
    action_status: str = ""
    fh: str = ""
    rm: str = ""
    rh: str = ""
    source_row: int = -1


@dataclass
class RiskDescriptionRecord:
    description: str
    inherent_code: Optional[str] = None          # raw code, e.g. "3D"
    mitigation: str = ""
    current_code: Optional[str] = None
    owner: str = ""                                # risk owner listed on this specific row
    treatments: list[RiskTreatmentRecord] = field(default_factory=list)
    source_row: int = -1


@dataclass
class RiskRegisterRecord:
    dept_code: str                            # sheet name / dept short code
    group_key: str                            # "S.No" value or "Risk ID" value, as string
    category: str                             # Category / Risk Name
    owner: str                                # owner on the FIRST row of the group -> used as register owner
    co_owner: str                                # owner on the SECOND row of the group -> used as description owner
    existing_risk_id: Optional[str] = None    # only set for "export" format (Risk ID already assigned)
    descriptions: list[RiskDescriptionRecord] = field(default_factory=list)
    source_sheet: str = ""


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if pd.isna(value) if not isinstance(value, (list, dict)) else False:
        return ""
    return str(value).strip()


def _blank(value) -> bool:
    return _clean(value) == ""


def _parse_date(value):
    if _blank(value):
        return None
    try:
        return pd.to_datetime(value)
    except Exception:
        return None


RISK_CODE_RE = re.compile(r"^([1-5])\s*[-]?\s*([A-Ea-e])$")


def normalize_risk_code(value) -> Optional[str]:

    text = _clean(value)
    if not text:
        return None
    m = RISK_CODE_RE.match(text.replace(" ", ""))
    if not m:
        return None
    return f"{m.group(1)}{m.group(2).upper()}"


# --------------------------------------------------------------------------
# format detection
# --------------------------------------------------------------------------

TEMPLATE_HEADER_HINTS = {"s. no", "s.no", "category"}
EXPORT_HEADER_HINTS = {"risk id", "risk name"}
UNIFIED_HEADER_HINTS = {"department"}


def detect_sheet_format(raw_df: pd.DataFrame) -> str:
    """
    raw_df must be read with header=None.
    Returns 'unified', 'template', or 'export'.
    """
    first_row = [
        _clean(v).lower() for v in raw_df.iloc[0].tolist()
    ]
    header_set = set(first_row)

    if header_set & UNIFIED_HEADER_HINTS:
        return "unified"
    if header_set & EXPORT_HEADER_HINTS:
        return "export"
    if header_set & TEMPLATE_HEADER_HINTS:
        return "template"

    raise ValueError(
        f"Could not detect sheet format from header row: {first_row}"
    )


# --------------------------------------------------------------------------
# generic hierarchical grouper
# --------------------------------------------------------------------------

def _group_rows(
    rows: list[dict],
    sheet_name: str,
    default_dept_code: str,
) -> list[RiskRegisterRecord]:

    registers: list[RiskRegisterRecord] = []
    current_register: Optional[RiskRegisterRecord] = None
    current_description: Optional[RiskDescriptionRecord] = None

    for i, row in enumerate(rows):
        starts_register = not _blank(row["group_key"])
        has_description_fields = any([
            not _blank(row["description"]),
            normalize_risk_code(row["inherent"]) is not None,
            not _blank(row["mitigation"]),
            normalize_risk_code(row["current"]) is not None,
        ])
        has_action_plan = not _blank(row["action_plan"])

        if starts_register:
            row_dept = _clean(row.get("dept_code")) or default_dept_code
            current_register = RiskRegisterRecord(
                dept_code=row_dept,
                group_key=_clean(row["group_key"]),
                category=_clean(row["category"]),
                owner=_clean(row["owner"]),
                co_owner=_clean(row["co_owner"]),
                existing_risk_id=_clean(row["group_key"]) if dept_code_looks_like_id(row["group_key"]) else None,
                source_sheet=sheet_name,
            )
            registers.append(current_register)
            current_description = None

        if current_register is None:

            if has_description_fields or has_action_plan:
               
                current_register = RiskRegisterRecord(
                    dept_code=_clean(row.get("dept_code")) or default_dept_code,
                    group_key=f"__orphan_row_{i}",
                    category=_clean(row["category"]),
                    owner=_clean(row["owner"]),
                    co_owner=_clean(row["co_owner"]),
                    source_sheet=sheet_name,
                )
                registers.append(current_register)
            else:
                continue

        if has_description_fields:
            current_description = RiskDescriptionRecord(
                description=_clean(row["description"]),
                inherent_code=normalize_risk_code(row["inherent"]),
                mitigation=_clean(row["mitigation"]),
                current_code=normalize_risk_code(row["current"]),
                owner=_clean(row["owner"]) or current_register.owner,
                source_row=i,
            )
            current_register.descriptions.append(current_description)

        if has_action_plan:
            if current_description is None:

                current_description = RiskDescriptionRecord(
                    description="",
                    owner=current_register.owner,
                    source_row=i,
                )
                current_register.descriptions.append(current_description)

            current_description.treatments.append(
                RiskTreatmentRecord(
                    action_plan=_clean(row["action_plan"]),
                    action_owner=_clean(row["action_owner"]),
                    due_date=_parse_date(row["due_date"]),
                    action_status=_clean(row["action_status"]),
                    fh=_clean(row.get("fh")),
                    rm=_clean(row.get("rm")),
                    rh=_clean(row.get("rh")),
                    source_row=i,
                )
            )

    return registers


def dept_code_looks_like_id(value) -> bool:
    """True for values like 'HR-0013' (export format's Risk ID)."""
    text = _clean(value)
    return bool(re.match(r"^[A-Za-z ]+-\d+$", text))


# --------------------------------------------------------------------------
# format-specific column mapping
# --------------------------------------------------------------------------

TEMPLATE_COLUMNS = [
    "S.No", "Category", "Risk Description", "Inherent Risk",
    "Current Mitigation", "Current Risk", "Risk Owner", "Risk Co Owner",
    "Action Plan", "Due Date", "Action Owner",
    "Q1", "Q2", "Q3", "Q4", "Backup",
]

EXPORT_COLUMNS = [
    "Risk ID", "Risk Name", "Risk Description", "Inherent Risk",
    "Current Mitigation", "Current Risk", "Risk Owner", "Risk Co Owner",
    "Action Plan", "Action Owner", "Due Date", "Action Status",
]


UNIFIED_COLUMNS = [
    "Department", "S.No", "Risk Category", "Risk Owner", "Risk Co Owner",
    "Inherent Risk", "Current Mitigation", "Current Risk", 
    "Action Owner", "Action Plan", "Due Date", "FH", "RM", "RH"
]


def parse_template_sheet(raw_df: pd.DataFrame, dept_code: str, sheet_name: str) -> list[RiskRegisterRecord]:

    df = raw_df.copy()
    n_cols = min(len(TEMPLATE_COLUMNS), df.shape[1])
    df = df.iloc[:, :n_cols]
    df.columns = TEMPLATE_COLUMNS[:n_cols]
    df = df.iloc[3:].reset_index(drop=True)

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "group_key": r.get("S.No"),
            "dept_code": None,                         # not present in this format -> use default
            "category": r.get("Category"),
            "owner": r.get("Risk Owner"),
            "co_owner": r.get("Risk Co Owner"),
            "description": r.get("Risk Description"),
            "inherent": r.get("Inherent Risk"),
            "mitigation": r.get("Current Mitigation"),
            "current": r.get("Current Risk"),
            "action_plan": r.get("Action Plan"),
            "action_owner": r.get("Action Owner"),
            "due_date": r.get("Due Date"),
            "fh": r.get("FH"),
            "rm": r.get("RM"),
            "rh": r.get("RH"),
            "action_status": None,
        })

    return _group_rows(rows, sheet_name=sheet_name, default_dept_code=dept_code)


def parse_export_sheet(raw_df: pd.DataFrame, dept_code: str, sheet_name: str) -> list[RiskRegisterRecord]:

    df = raw_df.copy()
    n_cols = min(len(EXPORT_COLUMNS), df.shape[1])
    df = df.iloc[:, :n_cols]
    df.columns = EXPORT_COLUMNS[:n_cols]
    df = df.iloc[1:].reset_index(drop=True)

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "group_key": r.get("Risk ID"),
            "dept_code": None,                          # dept comes from the sheet name for this format
            "category": r.get("Risk Name"),
            "owner": r.get("Risk Owner"),
            "co_owner": r.get("Risk Co Owner"),
            "description": r.get("Risk Description"),
            "inherent": r.get("Inherent Risk"),
            "mitigation": r.get("Current Mitigation"),
            "current": r.get("Current Risk"),
            "action_plan": r.get("Action Plan"),
            "action_owner": r.get("Action Owner"),
            "due_date": r.get("Due Date"),
            "fh": _clean(r.get("FH")),
            "rm": _clean(r.get("RM")),
            "rh": _clean(r.get("RH")),
            "action_status": r.get("Action Status"),
        })

    return _group_rows(rows, sheet_name=sheet_name, default_dept_code=dept_code)


def parse_unified_sheet(raw_df: pd.DataFrame, sheet_name: str) -> list[RiskRegisterRecord]:

    df = raw_df.copy()
    n_cols = min(len(UNIFIED_COLUMNS), df.shape[1])
    df = df.iloc[:, :n_cols]
    df.columns = UNIFIED_COLUMNS[:n_cols]
    df = df.iloc[2:].reset_index(drop=True)

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "group_key": r.get("S.No"),
            "dept_code": r.get("Department"),
            "category": r.get("Risk Category"),
            "owner": r.get("Risk Owner"),
            "co_owner": r.get("Risk Co Owner"),
            "description": r.get("Risk Category"),
            "inherent": r.get("Inherent Risk"),
            "mitigation": r.get("Current Mitigation"),
            "current": r.get("Current Risk"),
            "action_plan": r.get("Action Plan"),
            "action_owner": r.get("Action Owner"),
            "due_date": r.get("Due Date"),
            "fh": _clean(r.get("FH")),
            "rm": _clean(r.get("RM")),
            "rh": _clean(r.get("RH")),
            "action_status": None,
        })

    
    return _group_rows(rows, sheet_name=sheet_name, default_dept_code="")


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------

def load_excel(path: str, default_dept_code: Optional[str] = None) -> list[RiskRegisterRecord]:

    #xl = pd.ExcelFile(path)
    all_registers: list[RiskRegisterRecord] = []

    with pd.ExcelFile(path) as xl:
        for sheet_name in xl.sheet_names:
            raw_df = xl.parse(sheet_name, header=None)
            if raw_df.empty:
                continue

            try:
                fmt = detect_sheet_format(raw_df)
            except ValueError:
                # Not a risk sheet (e.g. an instructions/cover sheet) -> skip.
                continue

            dept_code = (default_dept_code or sheet_name).strip()

            if fmt == "unified":
                registers = parse_unified_sheet(raw_df, sheet_name=sheet_name)
                
            elif fmt == "template":
                registers = parse_template_sheet(raw_df, dept_code=dept_code, sheet_name=sheet_name)
                
            else:
                registers = parse_export_sheet(raw_df, dept_code=sheet_name.strip(), sheet_name=sheet_name)

            all_registers.extend(registers)

    return all_registers


# --------------------------------------------------------------------------
# convenience: flatten back to a table, for eyeballing / debugging
# --------------------------------------------------------------------------

def to_flat_dataframe(registers: list[RiskRegisterRecord]) -> pd.DataFrame:
    rows = []
    for reg in registers:
        if not reg.descriptions:
            rows.append({
                "sheet": reg.source_sheet, "dept": reg.dept_code,
                "group_key": reg.group_key, "existing_risk_id": reg.existing_risk_id,
                "category": reg.category, "register_owner": reg.owner,
                "description": "", "inherent": "", "mitigation": "", "current": "",
                "description_owner": "", "action_plan": "", "action_owner": "",
                "due_date": "", "action_status": "",
            })
            continue
        for desc in reg.descriptions:
            if not desc.treatments:
                rows.append({
                    "sheet": reg.source_sheet, "dept": reg.dept_code,
                    "group_key": reg.group_key, "existing_risk_id": reg.existing_risk_id,
                    "category": reg.category, "register_owner": reg.owner,
                    "description": desc.description, "inherent": desc.inherent_code,
                    "mitigation": desc.mitigation, "current": desc.current_code,
                    "description_owner": desc.owner,
                    "action_plan": "", "action_owner": "", "due_date": "", "action_status": "",
                })
                continue
            for t in desc.treatments:
                rows.append({
                    "sheet": reg.source_sheet, "dept": reg.dept_code,
                    "group_key": reg.group_key, "existing_risk_id": reg.existing_risk_id,
                    "category": reg.category, "register_owner": reg.owner,
                    "description": desc.description, "inherent": desc.inherent_code,
                    "mitigation": desc.mitigation, "current": desc.current_code,
                    "description_owner": desc.owner,
                    "action_plan": t.action_plan, "action_owner": t.action_owner,
                    "due_date": t.due_date, "action_status": t.action_status,
                })
    return pd.DataFrame(rows)
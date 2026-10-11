from pydantic import BaseModel
from typing import Optional, List


# Schemas for Risk Dashboard operations, including response models for various dashboard views and summaries
class RiskDashboardSummaryResponse(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total: int = 0
    open_risks: Optional[int] = 0
    in_progress: int = 0
    completed: Optional[int] = 0
    approved: int = 0
    rejected: int = 0
    # Granular status counters
    New: Optional[int] = 0
    Open: Optional[int] = 0
    Close: Optional[int] = 0
    Pending: Optional[int] = 0
    Complete: Optional[int] = 0
    Approved: Optional[int] = 0
    Rejected: Optional[int] = 0


class DepartmentWiseRiskResponse(BaseModel):
    department: str
    total: int


class EmployeeWiseRiskResponse(BaseModel):
    employee_name: str
    total: int


class StatusWisePieResponse(BaseModel):
    status: str
    total: int


class DeptartmentwiseprogressResponse(BaseModel):
    department: str
    progress: float


class DepartmentWiseStatusStackedResponse(BaseModel):
    department: str
    New: int = 0
    Open: Optional[int] = 0
    In_Progress: int = 0
    Pending: int = 0
    Approved: int = 0
    Rejected: int = 0
    Complete: Optional[int] = 0
    Close: Optional[int] = 0


class TopRiskResponse(BaseModel):
    risk_register_id: int
    risk_id: str
    risk_name: str
    department: Optional[str] = None
    risk_owner: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[str] = None
    risk_description_id: Optional[int] = None
    likelihood: int = 1
    impact: int = 1
    risk_score: int = 1
    severity_level: Optional[str] = "Low"
    color: Optional[str] = "#10B981"


class RiskPercentageResponse(BaseModel):
    category: str
    count: Optional[int] = 0
    percentage: float


class RiskHeatmapResponse(BaseModel):
    likelihood: int
    impact: int
    count: int
    color: str
    code: str


class RiskHeatmapcountResponse(BaseModel):
    count: int
    inherent_code: str
    current_code: str
    Department: Optional[str] = None
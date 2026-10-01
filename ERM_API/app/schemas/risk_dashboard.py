from pydantic import BaseModel


# Schemas for Risk Dashboard operations, including response models for various dashboard views and summaries
class RiskDashboardSummaryResponse(BaseModel):
    year: int
    total: int
    New: int
    open: int  
    in_progress: int
    Close: int
    Pending: int
    complet: int  
    approved: int   
    rejected: int   
    
    
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
    department: int
    progress: float
    
class DepartmentWiseStatusStackedResponse(BaseModel):
    department: str

    New: int
    In_Progress: int
    pending : int
    Approved: int
    Rejected: int
    
class TopRiskResponse(BaseModel):
    risk_register_id: int
    risk_id: str
    risk_name: str
    risk_description_id: int
    likelihood: int
    impact: int
    risk_score: int
    

class RiskPercentageResponse(BaseModel):
    category: str
    percentage: float
    
    
class RiskHeatmapResponse(BaseModel):
    likelihood: int
    impact: int
    count: int
    color: str
    code: str
    
class RiskHeatmapcountResponse(BaseModel):
    count: int
    Department: str
    inherent_code: str
    current_code: str
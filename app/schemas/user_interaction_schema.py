from pydantic import BaseModel, Field
from typing import Optional, Dict
from app.schemas.common_schema import AlertFrequency

class CompanyReviewCreate(BaseModel):
    company_id: str = Field(...)
    is_anonymous: bool = Field(default=True)
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class SavedJobCreate(BaseModel):
    job_id: str = Field(...)

class JobAlertCreate(BaseModel):
    search_criteria: Dict = Field(..., description="Các filter ứng viên đã chọn")
    frequency: AlertFrequency = Field(default=AlertFrequency.WEEKLY)
    is_active: bool = Field(default=True)

class JobAlertUpdate(BaseModel):
    search_criteria: Optional[Dict] = None
    frequency: Optional[AlertFrequency] = None
    is_active: Optional[bool] = None
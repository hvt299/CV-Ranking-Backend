from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime
from app.schemas.common_schema import utc_now, AlertFrequency

class CompanyReviewDB(BaseModel):
    id: str
    company_id: str = Field(...)
    reviewer_user_id: str = Field(...)
    is_anonymous: bool = Field(default=True)
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

class SavedJobDB(BaseModel):
    id: str
    user_id: str = Field(...)
    job_id: str = Field(...)
    created_at: datetime = Field(default_factory=utc_now)

class JobAlertDB(BaseModel):
    id: str
    user_id: str = Field(...)
    search_criteria: Dict = Field(..., description="VD: {'keyword': 'React', 'location': 'HCM', 'salary_min': 1000}")
    frequency: AlertFrequency = Field(default=AlertFrequency.WEEKLY)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
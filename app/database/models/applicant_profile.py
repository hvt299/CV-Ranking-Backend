from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date
from app.schemas.common_schema import utc_now
from app.schemas.shared_schema import LocationDetail

class ApplicantProfileDB(BaseModel):
    id: str
    user_id: str = Field(..., description="Unique Index tham chiếu sang bảng Users")
    
    headline: Optional[str] = Field(default=None, description="VD: Backend Developer 3 năm kinh nghiệm")
    desired_job_titles: List[str] = Field(default_factory=list)
    
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    currency: str = Field(default="VND")
    
    current_location: Optional[LocationDetail] = None
    preferred_locations: List[LocationDetail] = Field(default_factory=list)
    willing_to_relocate: bool = Field(default=False)
    availability_date: Optional[date] = None
    
    github: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: List[str] = Field(default_factory=list)
    
    primary_cv_document_id: Optional[str] = Field(default=None, description="CV nộp nhanh mặc định")
    
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
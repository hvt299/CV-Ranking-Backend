from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date
from app.schemas.shared_schema import LocationDetail

class ExternalCVLink(BaseModel):
    provider: str = Field(..., description="Ví dụ: 'google_drive', 'onedrive', 'notion'")
    url: str = Field(...)
    is_primary: bool = Field(default=False)

class ApplicantProfileUpdate(BaseModel):
    headline: Optional[str] = None
    desired_job_titles: Optional[List[str]] = None
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    currency: Optional[str] = None
    current_location: Optional[LocationDetail] = None
    preferred_locations: Optional[List[LocationDetail]] = None
    willing_to_relocate: Optional[bool] = None
    availability_date: Optional[date] = None
    
    linkedin: Optional[str] = None
    portfolio: Optional[List[str]] = None
    
    industry_specific_data: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Lưu trữ linh hoạt. VD: {'behance': '...', 'leetcode': '...', 'driver_license_class': 'B2'}"
    )
    
    primary_cv_document_id: Optional[str] = None
    external_cv_links: Optional[List[ExternalCVLink]] = None
    is_searchable: Optional[bool] = Field(default=True, description="Cho phép HR chủ động tìm thấy hồ sơ")
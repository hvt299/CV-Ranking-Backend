from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
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

    linkedin: Optional[str] = None
    portfolio: List[str] = Field(default_factory=list)
    
    industry_specific_data: Dict[str, Any] = Field(default_factory=dict)
    
    primary_cv_document_id: Optional[str] = Field(default=None, description="CV nộp nhanh mặc định")
    external_cv_links: List[dict] = Field(default_factory=list)
    is_searchable: bool = Field(default=True)
    
    current_plan_id: Optional[str] = Field(default=None, description="ID tham chiếu tới collection subscription_plans")
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    credits_remaining: int = Field(default=0, description="Trừ lùi mỗi lần dùng AI")
    
    hr_view_count: int = Field(default=0, description="Số lượt HR bấm vào xem profile chi tiết")
    search_appearance_count: int = Field(default=0, description="Số lượt xuất hiện trên trang kết quả tìm kiếm của HR")
    
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
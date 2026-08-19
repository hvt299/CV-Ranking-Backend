from pydantic import Field
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import utc_now, CompanyStatus
from app.schemas.company_schema import CompanyCreate, DepartmentCreate

class CompanyDB(CompanyCreate):
    id: str
    owner_user_id: str = Field(..., description="user_id của HR_OWNER đã tạo công ty này")
    
    status: CompanyStatus = Field(default=CompanyStatus.PENDING_VERIFICATION)
    rejection_reason: Optional[str] = None
    
    kyc_submitted_at: Optional[datetime] = None
    kyc_approved_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    verified_by_admin_id: Optional[str] = None
    
    view_count: int = Field(default=0)
    profile_view_count: int = Field(default=0)
    follower_count: int = Field(default=0)
    
    avg_rating: float = Field(default=0.0)
    review_count: int = Field(default=0)
    
    current_plan_id: Optional[str] = Field(default=None, description="ID tham chiếu tới collection subscription_plans")
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    credits_remaining: int = Field(default=0, description="Trừ lùi mỗi lần dùng AI")

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None

class DepartmentDB(DepartmentCreate):
    id: str
    created_at: datetime = Field(default_factory=utc_now)
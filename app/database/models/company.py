from pydantic import Field
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import utc_now, CompanyStatus
from app.schemas.company_schema import CompanyCreate, DepartmentCreate

class CompanyDB(CompanyCreate):
    id: str
    owner_user_id: str = Field(
        ...,
        description="user_id của HR_OWNER đã tạo công ty này"
    )
    status: CompanyStatus = Field(default=CompanyStatus.PENDING_VERIFICATION)
    rejection_reason: Optional[str] = None
    verified_at: Optional[datetime] = None
    verified_by_admin_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None

class DepartmentDB(DepartmentCreate):
    id: str
    created_at: datetime = Field(default_factory=utc_now)
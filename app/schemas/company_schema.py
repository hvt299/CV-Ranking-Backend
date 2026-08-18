from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Optional, List
from datetime import datetime
import re
from app.schemas.shared_schema import LocationDetail, KYCDocument
from app.schemas.common_schema import CompanyStatus

class CompanyCreate(BaseModel):
    name: str = Field(..., example="TechCorp VN")
    tax_code: str = Field(..., description="Mã số thuế doanh nghiệp — bắt buộc để xác minh")
    industries: List[str] = Field(default=["other"], description="Danh sách mã ngành (VD: ['it', 'finance']). Phần tử đầu tiên là Primary Industry.")
    size: Optional[str] = Field(default=None, example="50-100 nhân sự")

    @field_validator("industries")
    def validate_industries(cls, v):
        if not v or len(v) == 0:
            return ["other"]
        if len(v) > 3:
            raise ValueError("Chỉ được chọn tối đa 3 ngành nghề cho một công ty.")
        return v
    website: Optional[str] = None
    
    location: Optional[LocationDetail] = None 
    
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    description: Optional[str] = Field(default=None, description="Giới thiệu công ty (trang public)")
    
    legal_representative_name: Optional[str] = None
    kyc_documents: List[KYCDocument] = Field(default_factory=list, description="Danh sách giấy tờ pháp lý")

    @field_validator("tax_code")
    def validate_tax_code_format(cls, v):
        if not re.match(r"^\d{10}(-\d{3})?$", v):
            raise ValueError("Mã số thuế không đúng định dạng (10 số, có thể kèm mã chi nhánh 3 số).")
        return v

class CompanyVerifyAction(BaseModel):
    approve: bool
    rejection_reason: Optional[str] = Field(default=None, description="Bắt buộc nếu approve=False")

    @field_validator("rejection_reason")
    def require_reason_if_rejected(cls, v, info):
        if info.data.get("approve") is False and not v:
            raise ValueError("Cần nêu lý do khi từ chối duyệt công ty.")
        return v

class DepartmentCreate(BaseModel):
    company_id: str
    name: str = Field(..., example="Phòng Backend")
    description: Optional[str] = None
    head_user_id: Optional[str] = Field(default=None, description="Trưởng phòng")

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    head_user_id: Optional[str] = None

class DepartmentResponse(DepartmentCreate):
    id: str
    created_at: datetime
    updated_at: datetime

class CompanyResponse(CompanyCreate):
    id: str
    status: CompanyStatus
    
    kyc_submitted_at: Optional[datetime] = None
    kyc_approved_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    
    view_count: int = Field(default=0)
    profile_view_count: int = Field(default=0, description="Số lượt ứng viên chủ động xem trang thông tin công ty")
    follower_count: int = Field(default=0, description="Tổng số lượt lưu công ty từ bảng SavedCompany")
    
    avg_rating: float = Field(default=0.0)
    review_count: int = Field(default=0)
    created_at: datetime
    updated_at: Optional[datetime] = None

class InviteMemberPayload(BaseModel):
    email: EmailStr
    department_id: Optional[str] = Field(default=None, description="ID của phòng ban (tuỳ chọn)")
    department_roles: List[str] = Field(default=["viewer"], description="Quyền hạn: 'interviewer', 'recruiter', 'viewer'")

class AssignMemberPayload(BaseModel):
    department_id: Optional[str] = Field(default=None, description="ID phòng ban (Truyền None nếu muốn gỡ nhân sự khỏi phòng)")
    department_roles: List[str] = Field(default=["viewer"], description="Quyền hạn: 'interviewer', 'recruiter', 'viewer'")
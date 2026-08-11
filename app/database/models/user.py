from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import utc_now, UserRole

class UserDB(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    hashed_password: str
    
    avatar_url: Optional[str] = None
    original_avatar_url: Optional[str] = None
    
    role: UserRole = Field(default=UserRole.APPLICANT)
    company_id: Optional[str] = None
    department_id: Optional[str] = None
    
    job_title_internal: Optional[str] = None
    extension_phone: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None

    is_verified: bool = Field(default=False)
    email_verified_at: Optional[datetime] = None

    is_active: bool = Field(default=True, description="Khóa/Mở tài khoản")
    banned_reason: Optional[str] = None
    banned_at: Optional[datetime] = None
    banned_by_admin_id: Optional[str] = None
    last_login_at: Optional[datetime] = None
    
    deleted_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
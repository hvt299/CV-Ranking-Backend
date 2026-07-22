from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import utc_now, UserRole
from app.schemas.user_schema import ProfileDetails

class UserDB(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    hashed_password: str
    avatar: str
    original_avatar: str
    role: UserRole = Field(default=UserRole.APPLICANT)
    company_id: Optional[str] = None
    department_id: Optional[str] = Field(
        default=None,
        description="Chỉ có ý nghĩa khi role = hr_member"
    )
    profile: Optional[ProfileDetails] = None
    is_verified: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional
import re
from app.schemas.common_schema import UserRole

class ProfileDetails(BaseModel):
    phone: Optional[str] = None
    address: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    bio: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=6, example="Trần Nam")
    password: str
    role: UserRole = Field(default=UserRole.APPLICANT)
    company_id: Optional[str] = None
    department_id: Optional[str] = Field(
        default=None,
        description="Chỉ có ý nghĩa khi role = hr_member"
    )

    @field_validator("password")
    def validate_password(cls, v):
        pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#+\-_=])[A-Za-z\d@$!%*?&#+\-_=]{8,}$"
        if not re.match(pattern, v):
            raise ValueError(
                "Mật khẩu phải từ 8 ký tự, gồm ít nhất 1 chữ hoa, 1 chữ thường, "
                "1 số và 1 ký tự đặc biệt."
            )
        return v

    @field_validator("role")
    def validate_role(cls, v):
        if v == UserRole.ADMIN:
            raise ValueError("Không được phép khởi tạo tài khoản Admin qua API này.")
        return v

    @field_validator("company_id")
    def validate_company_required_for_hr_member(cls, v, info):
        role = info.data.get("role")
        if role == UserRole.HR_MEMBER and not v:
            raise ValueError("company_id là bắt buộc với role hr_member (được mời vào công ty có sẵn).")
        return v
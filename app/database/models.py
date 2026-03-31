from pydantic import BaseModel, Field, EmailStr, field_validator
import re
from typing import List, Optional
from datetime import datetime, timezone

class SkillDetail(BaseModel):
    name: str = Field(..., description="Tên kỹ năng (VD: React, NodeJS)")
    weight: float = Field(default=0.5, ge=0.1, le=1.0, description="Trọng số kỹ năng (Từ 0.1 đến 1.0)")
    min_years: int = Field(default=0, description="Số năm kinh nghiệm tối thiểu cho kỹ năng này")

class EducationRequirement(BaseModel):
    min_level: str = Field(default="Không yêu cầu", description="Cấp bậc học vấn tối thiểu")
    preferred_majors: List[str] = Field(default=[], description="Các chuyên ngành ưu tiên")

class SalaryRange(BaseModel):
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    currency: str = Field(default="VND")

class LocationDetail(BaseModel):
    city: str = Field(..., description="Thành phố / Tỉnh (VD: TP.HCM)")
    district: Optional[str] = None
    country: str = Field(default="Vietnam")

class JobCreateEnterprise(BaseModel):
    title: str = Field(..., example="Senior Frontend Developer")
    company_name: str = Field(..., example="TechCorp VN")
    job_level: str = Field(default="Middle/Senior")
    employment_type: str = Field(default="Full-time")
    work_mode: str = Field(default="Office")
    headcount: Optional[int] = Field(default=1)
    deadline: Optional[datetime] = None

    required_skills: List[SkillDetail] = Field(..., description="Danh sách kỹ năng BẮT BUỘC")
    preferred_skills: List[SkillDetail] = Field(default=[], description="Danh sách kỹ năng ƯU TIÊN (điểm cộng)")
    min_yoe: int = Field(default=0, description="Tổng số năm kinh nghiệm tối thiểu")
    education: Optional[EducationRequirement] = None

    salary: Optional[SalaryRange] = None
    working_hours: Optional[str] = Field(default="08:00 - 17:30, Thứ 2 - Thứ 6")
    location: Optional[LocationDetail] = None

    description: str = Field(..., description="Mô tả công việc chi tiết")
    requirements: str = Field(..., description="Yêu cầu công việc chi tiết")
    benefits: Optional[str] = Field(default="", description="Quyền lợi ứng viên")
    other_info: Optional[str] = Field(default="", description="Thông tin/Ghi chú khác")

class JobResponse(JobCreateEnterprise):
    id: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None

class CVCandidateCreate(BaseModel):
    filename: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    github: Optional[str] = None
    skills: List[str] = []
    skill_count: int = 0
    years_of_experience: float = Field(default=0.0, description="Số năm kinh nghiệm bóc tách được")
    education_level: str = Field(default="Không đề cập", description="Trình độ học vấn cao nhất")
    raw_text: str = Field(exclude=True)
    status: str = Field(default="new", example="new, reviewed, interviewing, rejected, hired")
    notes: List[str] = Field(default_factory=list, description="Danh sách các ghi chú của HR")

class CVCandidateDB(CVCandidateCreate):
    id: str
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))

class CVUpdate(BaseModel):
    status: Optional[str] = Field(None, example="interviewing")
    note: Optional[str] = Field(None, example="Ứng viên giao tiếp tiếng Anh khá tốt")

class HRUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=6, example="Trần Nam")
    password: str

    @field_validator('password')
    def validate_password(cls, v):
        pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
        if not re.match(pattern, v):
            raise ValueError("Mật khẩu phải từ 8 ký tự, gồm ít nhất 1 chữ hoa, 1 chữ thường, 1 số và 1 ký tự đặc biệt.")
        return v

class HRUserLogin(BaseModel):
    email: EmailStr
    password: str

class HRUserDB(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    hashed_password: str
    avatar: str
    original_avatar: str
    is_verified: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Token(BaseModel):
    access_token: str
    token_type: str
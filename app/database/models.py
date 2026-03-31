from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime, timezone

class JobDescriptionCreate(BaseModel):
    title: str = Field(..., example="Thực tập sinh React Native")
    description: Optional[str] = Field(None, example="Phát triển ứng dụng mobile...")
    required_skills: List[str] = Field(..., example=["React Native", "TypeScript", "Firebase"])
    required_experience: float = Field(default=0.0, description="Số năm kinh nghiệm yêu cầu")

class JobDescriptionDB(JobDescriptionCreate):
    id: str
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))

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
    password: str = Field(..., min_length=6)

class HRUserLogin(BaseModel):
    email: EmailStr
    password: str

class HRUserDB(BaseModel):
    id: str
    email: EmailStr
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))

class Token(BaseModel):
    access_token: str
    token_type: str
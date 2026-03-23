from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

class JobDescriptionCreate(BaseModel):
    title: str = Field(..., example="Thực tập sinh React Native")
    description: Optional[str] = Field(None, example="Phát triển ứng dụng mobile...")
    required_skills: List[str] = Field(..., example=["React Native", "TypeScript", "Firebase"])

class JobDescriptionDB(JobDescriptionCreate):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class CVCandidateCreate(BaseModel):
    filename: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    github: Optional[str] = None
    skills: List[str] = []
    skill_count: int = 0
    raw_text: str = Field(exclude=True)

class CVCandidateDB(CVCandidateCreate):
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
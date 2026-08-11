from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict
from enum import Enum
from app.schemas.shared_schema import LocationDetail

class ParsingStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class SkillMatch(BaseModel):
    skill_id: Optional[str] = None
    name: str

class CandidateInfo(BaseModel):
    full_name: Optional[str] = Field(default=None, description="Bóc tách từ CV để nhân sự dễ xem")
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    current_location: Optional[LocationDetail] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: List[str] = Field(default=[])
    education_level: str = Field(default="Không đề cập")
    years_of_experience: float = Field(default=0.0)
    skill_experience: Dict[str, float] = Field(default_factory=dict)
    job_hops: int = Field(default=1)
    gap_months: int = Field(default=0)
    fraud_analysis: Optional[Dict] = None

class CVDocumentCreate(BaseModel):
    display_name: str = Field(..., example="CV_Backend_2026")
    filename: str
    file_url: str = Field(..., description="URL file gốc trên Cloudinary")
    candidate_info: CandidateInfo
    extracted_skills: List[SkillMatch] = Field(default=[])
    raw_text: str = Field(exclude=True)

class CVSnapshot(BaseModel):
    cv_document_id: str = Field(...)
    display_name: str
    filename: str
    file_url: str
    candidate_info: CandidateInfo
    extracted_skills: List[SkillMatch] = Field(default=[])
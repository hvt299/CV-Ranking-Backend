from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from enum import Enum
from app.schemas.shared_schema import LocationDetail

class JobLevel(str, Enum):
    INTERN = "Intern"
    FRESHER = "Fresher"
    JUNIOR = "Junior"
    MIDDLE = "Middle"
    SENIOR = "Senior"
    MANAGER = "Manager"
    DIRECTOR = "Director"

class EmploymentType(str, Enum):
    FULL_TIME = "Full-time"
    PART_TIME = "Part-time"
    CONTRACT = "Contract"
    FREELANCE = "Freelance"
    INTERNSHIP = "Internship"

class WorkMode(str, Enum):
    OFFICE = "Office"
    HYBRID = "Hybrid"
    REMOTE = "Remote"

class SkillDetail(BaseModel):
    skill_id: Optional[str] = Field(default=None, description="Tham chiếu tới collection skills")
    name: str = Field(..., description="Tên kỹ năng (Fallback hiển thị)")
    weight: float = Field(default=0.5, ge=0.1, le=1.0)
    min_years: float = Field(default=0.0)

class EducationRequirement(BaseModel):
    min_level: str = Field(default="Không yêu cầu")
    preferred_majors: List[str] = Field(default=[])

class SalaryRange(BaseModel):
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    currency: str = Field(default="VND")

class ScoreWeights(BaseModel):
    skills_weight: float = Field(default=0.4, ge=0.1, le=0.7)
    nlp_weight: float = Field(default=0.3, ge=0.1, le=0.7)
    experience_weight: float = Field(default=0.2, ge=0.05, le=0.5)
    education_weight: float = Field(default=0.1, ge=0.0, le=0.4)

    @field_validator("education_weight")
    def validate_weights_sum_to_one(cls, v, info):
        total = info.data.get("skills_weight", 0) + info.data.get("nlp_weight", 0) + info.data.get("experience_weight", 0) + v
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Tổng 4 trọng số phải bằng 1.0 (hiện tại: {total}).")
        return v

class JobCreateEnterprise(BaseModel):
    title: str = Field(..., example="Senior Frontend Developer")
    company_id: str
    is_hot: bool = Field(default=False)
    industry: Optional[str] = None
    
    job_level: JobLevel = Field(default=JobLevel.MIDDLE)
    employment_type: EmploymentType = Field(default=EmploymentType.FULL_TIME)
    work_mode: WorkMode = Field(default=WorkMode.OFFICE)
    
    headcount: Optional[int] = Field(default=1)
    deadline: Optional[datetime] = None
    probation_period: Optional[str] = Field(default="2 tháng")
    gender_requirement: str = Field(default="Không yêu cầu")
    languages: List[str] = Field(default=[])
    
    required_skills: List[SkillDetail] = Field(...)
    preferred_skills: List[SkillDetail] = Field(default=[])
    
    min_yoe: float = Field(default=0.0)
    education: Optional[EducationRequirement] = None
    score_weights: Optional[ScoreWeights] = None
    required_certifications: List[str] = Field(default=[])
    salary: Optional[SalaryRange] = None
    working_hours: Optional[str] = Field(default="08:00 - 17:30, Thứ 2 - Thứ 6")
    location: Optional[LocationDetail] = None
    
    description: str = Field(...)
    requirements: str = Field(...)
    benefits: Optional[str] = Field(default="")
    other_info: Optional[str] = Field(default="")
    
    jd_file_url: Optional[str] = None
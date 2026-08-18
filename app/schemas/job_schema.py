from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from enum import Enum
from app.schemas.shared_schema import LocationDetail
from app.schemas.common_schema import JobStatus

class JobLevel(str, Enum):
    INTERN = "Intern"
    FRESHER = "Fresher"
    JUNIOR = "Junior"
    MIDDLE = "Middle"
    SENIOR = "Senior"
    LEAD = "LEAD"
    MANAGER = "Manager"
    DIRECTOR = "Director"
    EXECUTIVE = "Executive"

class EmploymentType(str, Enum):
    FULL_TIME = "Full-time"
    PART_TIME = "Part-time"
    CONTRACT = "Contract"
    FREELANCE = "Freelance"
    INTERNSHIP = "Internship"
    TEMPORARY = "Temporary"

class WorkMode(str, Enum):
    OFFICE = "Office"
    HYBRID = "Hybrid"
    REMOTE = "Remote"

class SkillDetail(BaseModel):
    skill_id: Optional[str] = Field(default=None, description="Tham chiếu tới collection skills")
    name: str = Field(..., description="Tên kỹ năng (Fallback hiển thị)")
    weight: float = Field(default=0.5, ge=0.1, le=1.0)
    min_years: float = Field(default=0.0)
    is_knockout: bool = Field(default=False, description="Tiêu chí tử thần. Thiếu sẽ bị loại trực tiếp")

class FilterRequirement(BaseModel):
    name: str = Field(..., description="Tên ngoại ngữ hoặc chứng chỉ")
    is_knockout: bool = Field(default=False, description="Tiêu chí tử thần. Thiếu sẽ bị loại trực tiếp")

class EducationRequirement(BaseModel):
    min_level: str = Field(default="Không yêu cầu")
    preferred_majors: List[str] = Field(default=[])

class SalaryRange(BaseModel):
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    currency: str = Field(default="VND")

class ScoreWeights(BaseModel):
    skills_weight: float = Field(..., ge=0.2, le=0.6, description="Trọng số Kỹ năng cốt lõi (20% - 60%)")
    nlp_weight: float = Field(..., ge=0.1, le=0.5, description="Trọng số Ngữ nghĩa AI (10% - 50%)")
    experience_weight: float = Field(..., ge=0.05, le=0.4, description="Trọng số Kinh nghiệm (5% - 40%)")
    education_weight: float = Field(..., ge=0.0, le=0.3, description="Trọng số Học vấn (0% - 30%)")

    @field_validator("education_weight")
    def validate_weights_sum_to_one(cls, v, info):
        s = info.data.get("skills_weight")
        n = info.data.get("nlp_weight")
        e = info.data.get("experience_weight")
        
        if s is None or n is None or e is None:
            return v
            
        total = s + n + e + v
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Tổng 4 trọng số phải bằng chính xác 1.0 (hiện tại: {total:.2f}).")
        return v

class JobCreateEnterprise(BaseModel):
    title: str = Field(..., example="Senior Frontend Developer")
    company_id: str
    is_hot: bool = Field(default=False)
    industry: str = Field(default="other", description="Mã ngành cụ thể của Job này (VD: 'it'). Nếu FE không gửi, backend sẽ tự gán Primary Industry của Company.")
    
    job_level: JobLevel = Field(default=JobLevel.MIDDLE)
    employment_type: EmploymentType = Field(default=EmploymentType.FULL_TIME)
    work_mode: WorkMode = Field(default=WorkMode.OFFICE)
    
    headcount: Optional[int] = Field(default=1)
    deadline: Optional[datetime] = None
    probation_period: Optional[str] = Field(default="2 tháng")
    gender_requirement: str = Field(default="Không yêu cầu")
    languages: List[FilterRequirement] = Field(default=[])
    
    required_skills: List[SkillDetail] = Field(...)
    preferred_skills: List[SkillDetail] = Field(default=[])
    
    min_yoe: float = Field(default=0.0)
    education: Optional[EducationRequirement] = None
    score_weights: Optional[ScoreWeights] = None
    required_certifications: List[FilterRequirement] = Field(default=[])
    salary: Optional[SalaryRange] = None
    working_hours: Optional[str] = Field(default="08:00 - 17:30, Thứ 2 - Thứ 6")
    location: Optional[LocationDetail] = None
    
    description: str = Field(...)
    requirements: str = Field(...)
    benefits: Optional[str] = Field(default="")
    other_info: Optional[str] = Field(default="")
    
    jd_file_url: Optional[str] = None

class JobResponse(JobCreateEnterprise):
    id: str
    company_name: Optional[str] = Field(default="Công ty Ẩn danh")
    status: JobStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    view_count: Optional[int] = Field(default=0)
    save_count: Optional[int] = Field(default=0, description="Số lượt ứng viên bookmark job này")
    num_applications: Optional[int] = Field(default=0)
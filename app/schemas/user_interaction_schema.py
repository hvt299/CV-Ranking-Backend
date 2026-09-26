from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class CompanyReviewCreate(BaseModel):
    company_id: str = Field(...)
    is_anonymous: bool = Field(default=True)
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class SavedJobCreate(BaseModel):
    job_id: str = Field(...)

class SavedCompanyCreate(BaseModel):
    company_id: str = Field(..., description="ID công ty mà ứng viên muốn theo dõi")

class TalentPoolCreate(BaseModel):
    applicant_user_id: str = Field(..., description="ID ứng viên được đưa vào Talent Pool")
    notes: Optional[str] = Field(None, description="Ghi chú nội bộ của HR")
    tags: List[str] = Field(default=[], description="Keywords để filter (vd: 'React', 'Senior')")

class RemoteFlexibilityEnum(str, Enum):
    REMOTE_ONLY = "remote_only"
    HYBRID = "hybrid"
    ONSITE_ONLY = "onsite_only"
    ANY = "any"

class MatchingPreferencesCreate(BaseModel):
    expected_salary_min: Optional[int] = Field(None, description="Mức lương tối thiểu mong muốn")
    expected_salary_max: Optional[int] = Field(None, description="Mức lương tối đa")
    currency: str = Field("VND", max_length=3)
    remote_flexibility: RemoteFlexibilityEnum = Field(default=RemoteFlexibilityEnum.ANY)
    preferred_industries: List[str] = Field(default=[])
    preferred_locations: List[str] = Field(default=[])
    strictly_avoided_keywords: List[str] = Field(default=[], description="Từ khóa cấm kỵ để AI loại trừ")

class MatchingPreferencesUpdate(BaseModel):
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    remote_flexibility: Optional[RemoteFlexibilityEnum] = None
    preferred_industries: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    strictly_avoided_keywords: Optional[List[str]] = None
    is_active: Optional[bool] = None
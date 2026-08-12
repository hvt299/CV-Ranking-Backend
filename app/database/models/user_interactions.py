from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.schemas.common_schema import utc_now
from app.schemas.user_interaction_schema import RemoteFlexibilityEnum

class CompanyReviewDB(BaseModel):
    id: str
    company_id: str = Field(...)
    reviewer_user_id: str = Field(...)
    is_anonymous: bool = Field(default=True)
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

class SavedJobDB(BaseModel):
    id: str
    user_id: str = Field(...)
    job_id: str = Field(...)
    created_at: datetime = Field(default_factory=utc_now)

class SavedCompanyDB(BaseModel):
    id: str
    company_id: str = Field(...)
    applicant_user_id: str = Field(...)
    created_at: datetime = Field(default_factory=utc_now)

class TalentPoolDB(BaseModel):
    id: str
    applicant_user_id: str = Field(...)
    hr_user_id: str = Field(..., description="HR đã lưu ứng viên này")
    company_id: str = Field(...)
    notes: Optional[str] = None
    tags: List[str] = Field(default=[])
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class MatchingPreferencesDB(BaseModel):
    id: str
    applicant_user_id: str = Field(...)
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    currency: str = Field("VND")
    remote_flexibility: RemoteFlexibilityEnum = Field(default=RemoteFlexibilityEnum.ANY)
    preferred_industries: List[str] = Field(default=[])
    preferred_locations: List[str] = Field(default=[])
    strictly_avoided_keywords: List[str] = Field(default=[])
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
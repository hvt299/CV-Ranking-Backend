from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date
from app.schemas.shared_schema import LocationDetail

class ApplicantProfileUpdate(BaseModel):
    headline: Optional[str] = None
    desired_job_titles: Optional[List[str]] = None
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    currency: Optional[str] = None
    current_location: Optional[LocationDetail] = None
    preferred_locations: Optional[List[LocationDetail]] = None
    willing_to_relocate: Optional[bool] = None
    availability_date: Optional[date] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: Optional[List[str]] = None
    primary_cv_document_id: Optional[str] = None
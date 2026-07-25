from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import utc_now, RecommendationEnum

class InterviewFeedbackDB(BaseModel):
    id: str
    application_id: str = Field(...)
    interviewer_user_id: str = Field(..., description="Người phỏng vấn")
    overall_rating: int = Field(..., ge=1, le=5)
    strengths: Optional[str] = None
    concerns: Optional[str] = None
    recommendation: RecommendationEnum = Field(...)
    created_at: datetime = Field(default_factory=utc_now)
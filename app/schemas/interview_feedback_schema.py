from pydantic import BaseModel, Field
from typing import Optional
from app.schemas.common_schema import RecommendationEnum

class InterviewFeedbackCreate(BaseModel):
    application_id: str = Field(...)
    overall_rating: int = Field(..., ge=1, le=5)
    strengths: Optional[str] = None
    concerns: Optional[str] = None
    recommendation: RecommendationEnum = Field(...)
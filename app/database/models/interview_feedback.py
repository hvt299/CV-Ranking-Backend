from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.schemas.common_schema import utc_now, RecommendationEnum
from app.schemas.interview_feedback_schema import InterviewStatus

class InterviewDB(BaseModel):
    id: str
    application_id: str = Field(...)
    company_id: str = Field(...)
    round_name: str = Field(...)
    scheduled_time: datetime = Field(...)
    duration_minutes: int = Field(60)
    meeting_url: Optional[str] = None
    interviewers: List[str] = Field(...)
    status: InterviewStatus = Field(default=InterviewStatus.SCHEDULED)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class InterviewFeedbackDB(BaseModel):
    id: str
    interview_id: str = Field(...)
    application_id: str = Field(..., description="Lưu dự phòng để truy vấn nhanh cho toàn bộ hồ sơ")
    interviewer_user_id: str = Field(...)
    overall_rating: int = Field(..., ge=1, le=5)
    strengths: Optional[str] = None
    concerns: Optional[str] = None
    recommendation: RecommendationEnum = Field(...)
    created_at: datetime = Field(default_factory=utc_now)
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
from app.schemas.common_schema import RecommendationEnum

class InterviewStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"

class InterviewCreate(BaseModel):
    application_id: str = Field(...)
    round_name: str = Field(..., description="VD: 'Technical Test', 'Culture Fit'")
    scheduled_time: datetime = Field(..., description="Thời gian phỏng vấn (UTC)")
    duration_minutes: int = Field(60)
    meeting_url: Optional[str] = Field(None, description="Link Google Meet/Zoom")
    interviewers: List[str] = Field(..., min_items=1, description="Danh sách ID của các HR tham gia phỏng vấn")

class InterviewFeedbackCreate(BaseModel):
    interview_id: str = Field(..., description="Feedback giờ đây gắn cứng vào từng vòng phỏng vấn (Interview), không phải Application")
    overall_rating: int = Field(..., ge=1, le=5)
    strengths: Optional[str] = None
    concerns: Optional[str] = None
    recommendation: RecommendationEnum = Field(...)
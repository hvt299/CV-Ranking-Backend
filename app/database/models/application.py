from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.schemas.common_schema import utc_now, ApplicationStatus, ApplicationSource
from app.schemas.cv_schema import CVSnapshot
from app.schemas.application_schema import AIScore, StatusChangeEntry, InterviewSchedule, OfferDetail, InterviewQuestion

class NoteEntry(BaseModel):
    author_id: str
    author_name: str
    content: str
    created_at: datetime = Field(default_factory=utc_now)

class ApplicationDB(BaseModel):
    id: str
    job_id: str
    cv_snapshot: CVSnapshot = Field(...)
    applicant_user_id: Optional[str] = None
    source: ApplicationSource
    company_id: str
    cover_letter: Optional[str] = None
    ai_score: Optional[AIScore] = None
    status: ApplicationStatus = Field(default=ApplicationStatus.NEW)
    
    status_history: List[StatusChangeEntry] = Field(default_factory=list)
    viewed_at: Optional[datetime] = None
    viewed_by_user_id: Optional[str] = None
    
    notes: List[NoteEntry] = Field(default_factory=list)
    
    interview_schedules: List[InterviewSchedule] = Field(default_factory=list)
    offer_detail: Optional[OfferDetail] = None
    rejection_reason: Optional[str] = Field(default=None, description="Bắt buộc nếu bị Reject")
    
    ai_interview_questions: Optional[List[InterviewQuestion]] = None
    
    applied_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from app.schemas.common_schema import utc_now, ApplicationStatus, ApplicationSource
from datetime import datetime

class SkillMatchDetail(BaseModel):
    skill: str
    matched: bool
    confidence: float = Field(
        default=0.0,
        description="Kết quả Skill-Context Verification: skill nằm trong câu có ngữ cảnh (cao) hay chỉ trong list phẳng (thấp)"
    )
    years_experience: Optional[float] = None

class ScoreBreakdown(BaseModel):
    skills_score: float = 0
    experience_score: float = 0
    education_score: float = 0
    nlp_score: float = 0
    penalty_score: float = 0
    fraud_analysis: Optional[Dict] = Field(
        default=None, 
        description="Lưu kết quả quét gian lận từ document_forensics (risk_score, penalty, evidence)"
    )

class AIScore(BaseModel):
    total_score: float
    score_breakdown: ScoreBreakdown
    skill_details: List[SkillMatchDetail] = Field(default=[])
    missing_required_skills: List[str] = Field(default=[])
    top_contributing_sentences: List[str] = Field(
        default=[],
        description="Các câu trong CV đóng góp điểm ngữ nghĩa cao nhất — phục vụ explainability"
    )

class ApplicationCreate(BaseModel):
    job_id: str
    cv_id: str = Field(
        ...,
        description="ID của CV gốc trong Document Center (CVRepository)"
    )
    applicant_user_id: Optional[str] = Field(
        default=None,
        description="None nếu HR chủ động sourcing, có giá trị nếu ứng viên tự nộp"
    )
    source: ApplicationSource
    company_id: str = Field(
        ...,
        description="ID của công ty quản lý job và application này"
    )
    cover_letter_id: Optional[str] = Field(
        default=None,
        description="ID của Thư giới thiệu (từ Thư viện Cover Letter)"
    )

class InterviewSchedule(BaseModel):
    interview_time: str = Field(
        ...,
        description="Thời gian phỏng vấn (VD: 14:00 - 20/10/2026)"
    )
    location: str = Field(
        ...,
        description="Địa điểm hoặc hình thức phỏng vấn (VD: Tầng 3, Tòa nhà X / Online)"
    )
    meeting_link: Optional[str] = Field(
        default=None,
        description="Link Google Meet / Zoom"
    )
    message: Optional[str] = Field(
        default=None,
        description="Lời nhắn thêm từ HR"
    )

class StatusChangeEntry(BaseModel):
    from_status: ApplicationStatus
    to_status: ApplicationStatus
    changed_by_user_id: str
    changed_at: datetime = Field(default_factory=utc_now)

class OfferDetail(BaseModel):
    offered_salary: int
    currency: str = Field(default="VND")
    start_date: datetime
    offer_file_url: Optional[str] = None

class InterviewQuestion(BaseModel):
    category: str = Field(..., description="VD: Technical, Soft Skill")
    question: str
    suggested_answer_points: List[str] = Field(default=[])

class ApplicationUpdate(BaseModel):
    status: Optional[ApplicationStatus] = None
    note_to_add: Optional[str] = None
    send_email: bool = Field(default=False)
    interview_schedule: Optional[InterviewSchedule] = None
    rejection_reason: Optional[str] = None
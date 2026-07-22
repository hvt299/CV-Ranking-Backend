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
    cv_document_id: str = Field(
        ...,
        description="ID của CVDocument trong Library được chọn để nộp")
    applicant_user_id: Optional[str] = Field(
        default=None,
        description="None nếu HR chủ động sourcing, có giá trị nếu ứng viên tự nộp"
    )
    source: ApplicationSource
    company_id: str = Field(
        ...,
        description="ID của công ty quản lý job và application này"
    )
    cover_letter: Optional[str] = Field(
        default=None,
        description="Thư giới thiệu của ứng viên gửi kèm khi nộp"
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

class ApplicationUpdate(BaseModel):
    status: Optional[ApplicationStatus] = None
    note_to_add: Optional[str] = Field(
        None,
        description="Thêm một dòng ghi chú mới vào mảng notes (author lấy từ token, không nhận từ client)"
    )
    send_email: bool = Field(
        default=False,
        description="Cờ xác nhận có gửi email cho ứng viên không"
    )
    interview_schedule: Optional[InterviewSchedule] = Field(
        default=None,
        description="Thông tin lịch phỏng vấn để gửi mail"
    )

class NoteEntry(BaseModel):
    author_id: str
    author_name: str = Field(..., description="Denormalize để FE không cần join thêm")
    content: str
    created_at: datetime = Field(default_factory=utc_now)
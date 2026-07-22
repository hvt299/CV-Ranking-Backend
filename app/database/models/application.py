from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.schemas.common_schema import utc_now, ApplicationStatus, ApplicationSource
from app.schemas.cv_schema import CVSnapshot
from app.schemas.application_schema import AIScore

class NoteEntry(BaseModel):
    author_id: str
    author_name: str = Field(
        ...,
        description="Denormalize để FE không cần join thêm"
    )
    content: str
    created_at: datetime = Field(default_factory=utc_now)

class ApplicationDB(BaseModel):
    id: str
    job_id: str
    cv_snapshot: CVSnapshot = Field(
        ...,
        description="Bản đóng băng CV tại thời điểm nộp — không đổi dù CVDocument gốc bị sửa/xóa sau"
    )
    applicant_user_id: Optional[str] = None
    source: ApplicationSource
    company_id: str
    cover_letter: Optional[str] = Field(
        default=None,
        description="Thư giới thiệu ứng viên đính kèm"
    )
    ai_score: Optional[AIScore] = None
    status: ApplicationStatus = Field(default=ApplicationStatus.NEW)
    is_viewed: bool = Field(
        default=False,
        description="HR đã xem hồ sơ hay chưa"
    )
    notes: List[NoteEntry] = Field(default_factory=list)
    applied_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
    ai_interview_questions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Lưu trữ câu hỏi phỏng vấn do AI sinh ra để tái sử dụng"
    )
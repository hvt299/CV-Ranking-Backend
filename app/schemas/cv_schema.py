from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict

class CandidateInfo(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: List[str] = Field(default=[])
    education_level: str = Field(
        default="Không đề cập",
        description="Trình độ học vấn cao nhất (VD: Đại học, Cao đẳng...)"
    )
    years_of_experience: float = Field(
        default=0.0,
        description="Tổng số năm kinh nghiệm bóc tách được từ CV"
    )
    skill_experience: Dict[str, float] = Field(default_factory=dict)
    job_hops: int = Field(default=1)
    gap_months: int = Field(default=0)
    fraud_analysis: Optional[Dict] = Field(
        default=None,
        description="Lưu kết quả quét gian lận từ Forensics"
    )

class CVDocumentCreate(BaseModel):
    display_name: str = Field(
        ...,
        example="CV_Backend_2026",
        description="Tên do ứng viên tự đặt để phân biệt các bản CV"
    )
    filename: str
    file_url: str = Field(
        ...,
        description="URL file gốc trên Cloudinary"
    )
    candidate_info: CandidateInfo
    extracted_skills: List[str] = Field(default=[])
    raw_text: str = Field(exclude=True)

class CVSnapshot(BaseModel):
    cv_document_id: str = Field(
        ...,
        description="Tham chiếu ngược để truy vết, KHÔNG dùng để lấy dữ liệu sống"
    )
    display_name: str
    filename: str
    file_url: str
    candidate_info: CandidateInfo
    extracted_skills: List[str] = Field(default=[])
from pydantic import BaseModel, Field, EmailStr, field_validator
import re
from enum import Enum
from typing import List, Optional, Dict
from datetime import datetime, timezone

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

# =====================================================================
# ENUMS — nguồn sự thật duy nhất cho mọi giá trị trạng thái/loại.
# FE chỉ cần map các mã này sang nhãn hiển thị theo ngôn ngữ (i18n),
# không còn phụ thuộc chuỗi tiếng Việt cứng trong DB.
# =====================================================================

class UserRole(str, Enum):
    ADMIN = "admin"
    HR_OWNER = "hr_owner"
    HR_MEMBER = "hr_member"
    APPLICANT = "applicant"

class JobStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAUSED = "paused"
    CLOSED = "closed"
    EXPIRED = "expired"

class ApplicationStatus(str, Enum):
    NEW = "new"
    REVIEWING = "reviewing"
    INTERVIEW = "interview"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"

class ApplicationSource(str, Enum):
    HR_SOURCED = "hr_sourced"
    APPLICANT_APPLY = "applicant_apply"

class NotificationType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

class NotificationReadStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"

class CompanyStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    REJECTED = "rejected"

class AuditAction(str, Enum):
    COMPANY_VERIFIED = "company_verified"
    COMPANY_REJECTED = "company_rejected"
    COMPANY_SUSPENDED = "company_suspended"
    APPLICATION_STATUS_CHANGED = "application_status_changed"
    APPLICATION_NOTE_ADDED = "application_note_added"
    JOB_WEIGHTS_CHANGED = "job_weights_changed"
    HR_MEMBER_INVITED = "hr_member_invited"
    HR_MEMBER_REMOVED = "hr_member_removed"
    USER_SUSPENDED = "user_suspended"

# =====================================================================
# COMPANIES — Cho phép 1 công ty có nhiều tài khoản HR.
# tax_code là bắt buộc và phải qua Admin duyệt (status) trước khi được
# phép đăng job — chống công ty ma / lừa đảo.
# =====================================================================

class CompanyCreate(BaseModel):
    name: str = Field(..., example="TechCorp VN")
    tax_code: str = Field(..., description="Mã số thuế doanh nghiệp — bắt buộc để xác minh")
    industry: Optional[str] = Field(
        default=None,
        description="Ngành nghề chính của công ty (VD: CNTT, Xây dựng, Y tế, Kế toán...)",
    )
    size: Optional[str] = Field(default=None, example="50-100 nhân sự")
    website: Optional[str] = None
    address: Optional[str] = None
    license_file_url: Optional[str] = Field(
        default=None, description="URL (Cloudinary) của giấy phép kinh doanh để Admin đối chiếu"
    )

    @field_validator("tax_code")
    def validate_tax_code_format(cls, v):
        if not re.match(r"^\d{10}(-\d{3})?$", v):
            raise ValueError("Mã số thuế không đúng định dạng (10 số, có thể kèm mã chi nhánh 3 số).")
        return v

class CompanyDB(CompanyCreate):
    id: str
    owner_user_id: str = Field(..., description="user_id của HR_OWNER đã tạo công ty này")
    status: CompanyStatus = Field(default=CompanyStatus.PENDING_VERIFICATION)
    rejection_reason: Optional[str] = None
    verified_at: Optional[datetime] = None
    verified_by_admin_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None

class CompanyVerifyAction(BaseModel):
    """Admin dùng để duyệt/từ chối công ty."""
    approve: bool
    rejection_reason: Optional[str] = Field(
        default=None, description="Bắt buộc nếu approve=False"
    )

    @field_validator("rejection_reason")
    def require_reason_if_rejected(cls, v, info):
        if info.data.get("approve") is False and not v:
            raise ValueError("Cần nêu lý do khi từ chối duyệt công ty.")
        return v

# =====================================================================
# DEPARTMENTS — scope quyền hạn cho HR_MEMBER trong nội bộ 1 công ty.
# =====================================================================

class DepartmentCreate(BaseModel):
    company_id: str
    name: str = Field(..., example="Phòng Backend")

class DepartmentDB(DepartmentCreate):
    id: str
    created_at: datetime = Field(default_factory=utc_now)

# =====================================================================
# USERS — dùng chung cho mọi role.
# =====================================================================

class ProfileDetails(BaseModel):
    phone: Optional[str] = None
    address: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    bio: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=6, example="Trần Nam")
    password: str
    role: UserRole = Field(default=UserRole.APPLICANT)
    company_id: Optional[str] = None
    department_id: Optional[str] = Field(
        default=None, description="Chỉ có ý nghĩa khi role = hr_member"
    )

    @field_validator("password")
    def validate_password(cls, v):
        pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#+\-_=])[A-Za-z\d@$!%*?&#+\-_=]{8,}$"
        if not re.match(pattern, v):
            raise ValueError(
                "Mật khẩu phải từ 8 ký tự, gồm ít nhất 1 chữ hoa, 1 chữ thường, "
                "1 số và 1 ký tự đặc biệt."
            )
        return v

    @field_validator("role")
    def validate_role(cls, v):
        if v == UserRole.ADMIN:
            raise ValueError("Không được phép khởi tạo tài khoản Admin qua API này.")
        return v

    @field_validator("company_id")
    def validate_company_required_for_hr_member(cls, v, info):
        role = info.data.get("role")
        if role == UserRole.HR_MEMBER and not v:
            raise ValueError("company_id là bắt buộc với role hr_member (được mời vào công ty có sẵn).")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserDB(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    hashed_password: str
    avatar: str
    original_avatar: str
    role: UserRole = Field(default=UserRole.APPLICANT)
    company_id: Optional[str] = None
    department_id: Optional[str] = Field(
        default=None, description="Chỉ có ý nghĩa khi role = hr_member"
    )
    profile: Optional[ProfileDetails] = None
    is_verified: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None

class Token(BaseModel):
    access_token: str
    token_type: str

# =====================================================================
# JOBS
# =====================================================================

class SkillDetail(BaseModel):
    name: str = Field(..., description="Tên kỹ năng/năng lực (VD: React, Kế toán thuế)")
    weight: float = Field(default=0.5, ge=0.1, le=1.0, description="Trọng số")
    min_years: float = Field(default=0.0, description="Số năm kinh nghiệm tối thiểu")

class EducationRequirement(BaseModel):
    min_level: str = Field(default="Không yêu cầu", description="Cấp bậc học vấn tối thiểu")
    preferred_majors: List[str] = Field(default=[], description="Các chuyên ngành ưu tiên")

class SalaryRange(BaseModel):
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    currency: str = Field(default="VND")

class LocationDetail(BaseModel):
    city: str = Field(..., description="Thành phố / Tỉnh (VD: TP.HCM)")
    address: Optional[str] = None
    country: str = Field(default="Việt Nam")

class ScoreWeights(BaseModel):
    skills_weight: float = Field(default=0.4, ge=0.1, le=0.7)
    nlp_weight: float = Field(default=0.3, ge=0.1, le=0.7)
    experience_weight: float = Field(default=0.2, ge=0.05, le=0.5)
    education_weight: float = Field(default=0.1, ge=0.0, le=0.4)

    @field_validator("education_weight")
    def validate_weights_sum_to_one(cls, v, info):
        total = (
            info.data.get("skills_weight", 0)
            + info.data.get("nlp_weight", 0)
            + info.data.get("experience_weight", 0)
            + v
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Tổng 4 trọng số phải bằng 1.0 (hiện tại: {total}).")
        return v

class JobCreateEnterprise(BaseModel):
    title: str = Field(..., example="Senior Frontend Developer")
    company_id: str

    is_hot: bool = Field(
        default=False,
        description="Đánh dấu Job nổi bật/gấp"
    )

    industry: Optional[str] = Field(
        default=None,
        description=(
            "Ngành nghề của vị trí (VD: CNTT, Xây dựng, Y tế...). "
            "Mặc định kế thừa từ industry của company nếu bỏ trống."
        ),
    )

    job_level: str = Field(
        default="Middle/Senior",
        description="Cấp bậc của vị trí tuyển dụng"
    )

    employment_type: str = Field(
        default="Full-time",
        description="Hình thức làm việc (Full-time, Part-time, Internship...)"
    )

    work_mode: str = Field(
        default="Office",
        description="Hình thức làm việc (Office, Hybrid, Remote)"
    )

    headcount: Optional[int] = Field(
        default=1,
        description="Số lượng cần tuyển"
    )

    deadline: Optional[datetime] = Field(
        default=None,
        description="Hạn nộp hồ sơ"
    )

    probation_period: Optional[str] = Field(
        default="2 tháng",
        description="Thời gian thử việc"
    )

    gender_requirement: Optional[str] = Field(
        default="Không yêu cầu",
        description="Yêu cầu giới tính"
    )

    languages: List[str] = Field(
        default=[],
        description="Yêu cầu ngoại ngữ (VD: Tiếng Anh, Tiếng Nhật)"
    )

    required_skills: List[SkillDetail] = Field(
        ...,
        description="Danh sách kỹ năng BẮT BUỘC"
    )

    preferred_skills: List[SkillDetail] = Field(
        default=[],
        description="Danh sách kỹ năng ƯU TIÊN"
    )

    min_yoe: float = Field(
        default=0.0,
        description="Tổng số năm kinh nghiệm tối thiểu"
    )

    education: Optional[EducationRequirement] = Field(
        default=None,
        description="Yêu cầu học vấn"
    )

    score_weights: Optional[ScoreWeights] = Field(
        default=None,
        description="Nếu None, hệ thống dùng trọng số mặc định 40/30/20/10"
    )

    required_certifications: List[str] = Field(
        default=[],
        description="Danh sách chứng chỉ bắt buộc (nếu có)"
    )

    salary: Optional[SalaryRange] = Field(
        default=None,
        description="Khoảng lương"
    )

    working_hours: Optional[str] = Field(
        default="08:00 - 17:30, Thứ 2 - Thứ 6",
        description="Thời gian làm việc"
    )

    location: Optional[LocationDetail] = Field(
        default=None,
        description="Địa điểm làm việc"
    )

    description: str = Field(
        ...,
        description="Mô tả công việc chi tiết"
    )

    requirements: str = Field(
        ...,
        description="Yêu cầu công việc chi tiết"
    )

    benefits: Optional[str] = Field(
        default="",
        description="Quyền lợi ứng viên"
    )

    other_info: Optional[str] = Field(
        default="",
        description="Thông tin/Ghi chú khác"
    )
    
class JobDB(JobCreateEnterprise):
    id: str
    status: JobStatus = Field(default=JobStatus.DRAFT)
    created_by_user_id: str
    jd_search_text: Optional[str] = None
    jd_vector_ref: Optional[List[float]] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None

class JobResponse(JobCreateEnterprise):
    id: str
    status: JobStatus
    created_by_user_id: str
    company_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

# =====================================================================
# CV LIBRARY — CVDocument thuộc về Applicant, độc lập với company/job.
# Ứng viên upload 1 lần, dùng lại cho nhiều lượt apply. Khi apply, hệ
# thống tạo CVSnapshot đóng băng dữ liệu tại thời điểm nộp, để việc sửa/
# xóa CVDocument gốc về sau không ảnh hưởng tới các Application đã tạo.
# =====================================================================

class CandidateInfo(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: List[str] = Field(default=[])
    education_level: str = Field(default="Không đề cập", description="Trình độ học vấn cao nhất (VD: Đại học, Cao đẳng...)")
    years_of_experience: float = Field(default=0.0, description="Tổng số năm kinh nghiệm bóc tách được từ CV")
    skill_experience: Dict[str, float] = Field(default_factory=dict)
    job_hops: int = Field(default=1)
    gap_months: int = Field(default=0)
    fraud_analysis: Optional[Dict] = Field(default=None, description="Lưu kết quả quét gian lận từ Forensics")

class CVDocumentCreate(BaseModel):
    display_name: str = Field(..., example="CV_Backend_2026", description="Tên do ứng viên tự đặt để phân biệt các bản CV")
    filename: str
    file_url: str = Field(..., description="URL file gốc trên Cloudinary")
    candidate_info: CandidateInfo
    extracted_skills: List[str] = Field(default=[])
    raw_text: str = Field(exclude=True)

class CVDocumentDB(CVDocumentCreate):
    id: str
    owner_user_id: str = Field(..., description="Luôn bắt buộc — CV Library thuộc về đúng 1 Applicant")
    cv_vector_ref: Optional[List[float]] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None

class CVSnapshot(BaseModel):
    cv_document_id: str = Field(..., description="Tham chiếu ngược để truy vết, KHÔNG dùng để lấy dữ liệu sống")
    display_name: str
    filename: str
    file_url: str
    candidate_info: CandidateInfo
    extracted_skills: List[str] = Field(default=[])

# =====================================================================
# APPLICATIONS — mọi luồng ứng tuyển (HR upload hộ hoặc ứng viên tự nộp)
# đều tạo ra đúng 1 bản ghi Application, gắn với 1 CVSnapshot đóng băng.
# =====================================================================

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
        default=[], description="Các câu trong CV đóng góp điểm ngữ nghĩa cao nhất — phục vụ explainability"
    )

class ApplicationCreate(BaseModel):
    job_id: str
    cv_document_id: str = Field(..., description="ID của CVDocument trong Library được chọn để nộp")
    applicant_user_id: Optional[str] = Field(
        default=None, description="None nếu HR chủ động sourcing, có giá trị nếu ứng viên tự nộp"
    )
    source: ApplicationSource
    company_id: str = Field(..., description="ID của công ty quản lý job và application này")
    cover_letter: Optional[str] = Field(default=None, description="Thư giới thiệu của ứng viên gửi kèm khi nộp")

class NoteEntry(BaseModel):
    author_id: str
    author_name: str = Field(..., description="Denormalize để FE không cần join thêm")
    content: str
    created_at: datetime = Field(default_factory=utc_now)

class ApplicationDB(BaseModel):
    id: str
    job_id: str
    cv_snapshot: CVSnapshot = Field(..., description="Bản đóng băng CV tại thời điểm nộp — không đổi dù CVDocument gốc bị sửa/xóa sau")
    applicant_user_id: Optional[str] = None
    source: ApplicationSource
    company_id: str
    cover_letter: Optional[str] = Field(default=None, description="Thư giới thiệu ứng viên đính kèm")
    ai_score: Optional[AIScore] = None
    status: ApplicationStatus = Field(default=ApplicationStatus.NEW)
    is_viewed: bool = Field(default=False, description="HR đã xem hồ sơ hay chưa")
    notes: List[NoteEntry] = Field(default_factory=list)
    applied_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None

class ApplicationUpdate(BaseModel):
    status: Optional[ApplicationStatus] = None
    note_to_add: Optional[str] = Field(None, description="Thêm một dòng ghi chú mới vào mảng notes (author lấy từ token, không nhận từ client)")

# =====================================================================
# AUDIT LOG — ghi vết mọi thao tác nhạy cảm để phục vụ đối soát/minh bạch.
# =====================================================================

class AuditLogCreate(BaseModel):
    actor_id: str
    actor_role: UserRole
    action: AuditAction
    target_type: str = Field(..., example="company | application | job | user")
    target_id: str
    note: Optional[str] = None

class AuditLogDB(AuditLogCreate):
    id: str
    created_at: datetime = Field(default_factory=utc_now)

# =====================================================================
# NOTIFICATIONS
# =====================================================================

class NotificationCreate(BaseModel):
    recipient_user_id: str
    application_id: str
    title: str
    message: str
    type: NotificationType = Field(default=NotificationType.INFO)
    job_title_snapshot: Optional[str] = None
    application_status_snapshot: Optional[ApplicationStatus] = None

class NotificationDB(NotificationCreate):
    id: str
    status: NotificationReadStatus = Field(default=NotificationReadStatus.UNREAD)
    created_at: datetime = Field(default_factory=utc_now)
    read_at: Optional[datetime] = None
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from app.schemas.common_schema import JobStatus

class SkillDetail(BaseModel):
    name: str = Field(
        ...,
        description="Tên kỹ năng/năng lực (VD: React, Kế toán thuế)"
    )
    weight: float = Field(default=0.5, ge=0.1, le=1.0, description="Trọng số")
    min_years: float = Field(
        default=0.0,
        description="Số năm kinh nghiệm tối thiểu"
    )

class EducationRequirement(BaseModel):
    min_level: str = Field(
        default="Không yêu cầu",
        description="Cấp bậc học vấn tối thiểu"
    )
    preferred_majors: List[str] = Field(
        default=[],
        description="Các chuyên ngành ưu tiên"
    )

class SalaryRange(BaseModel):
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    currency: str = Field(default="VND")

class LocationDetail(BaseModel):
    city: str = Field(
        ...,
        description="Thành phố / Tỉnh (VD: TP.HCM)"
    )
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

class JobResponse(JobCreateEnterprise):
    id: str
    status: JobStatus
    created_by_user_id: str
    company_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
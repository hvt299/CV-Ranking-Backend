from pydantic import BaseModel, Field, field_validator
from typing import Optional
import re

class CompanyCreate(BaseModel):
    name: str = Field(
        ...,
        example="TechCorp VN"
    )
    tax_code: str = Field(
        ...,
        description="Mã số thuế doanh nghiệp — bắt buộc để xác minh"
    )
    industry: Optional[str] = Field(
        default=None,
        description="Ngành nghề chính của công ty (VD: CNTT, Xây dựng, Y tế, Kế toán...)"
    )
    size: Optional[str] = Field(
        default=None,
        example="50-100 nhân sự"
    )
    website: Optional[str] = None
    address: Optional[str] = None
    license_file_url: Optional[str] = Field(
        default=None,
        description="URL (Cloudinary) của giấy phép kinh doanh để Admin đối chiếu"
    )

    @field_validator("tax_code")
    def validate_tax_code_format(cls, v):
        if not re.match(r"^\d{10}(-\d{3})?$", v):
            raise ValueError("Mã số thuế không đúng định dạng (10 số, có thể kèm mã chi nhánh 3 số).")
        return v

class CompanyVerifyAction(BaseModel):
    approve: bool
    rejection_reason: Optional[str] = Field(
        default=None,
        description="Bắt buộc nếu approve=False"
    )

    @field_validator("rejection_reason")
    def require_reason_if_rejected(cls, v, info):
        if info.data.get("approve") is False and not v:
            raise ValueError("Cần nêu lý do khi từ chối duyệt công ty.")
        return v

class DepartmentCreate(BaseModel):
    company_id: str
    name: str = Field(
        ...,
        example="Phòng Backend"
    )
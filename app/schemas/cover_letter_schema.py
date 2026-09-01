from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import utc_now

class CoverLetterDB(BaseModel):
    id: Optional[str] = None
    owner_user_id: Optional[str] = Field(default=None, description="ID Ứng viên (Nếu ứng viên tự tải)")
    company_id: Optional[str] = Field(default=None, description="ID Công ty (Nếu HR tải lên hộ ứng viên)")
    display_name: str = Field(..., description="Tên gợi nhớ (VD: Cover Letter - IT Backend)")
    filename: str
    file_url: str
    created_at: datetime = Field(default_factory=utc_now)
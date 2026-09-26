from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from app.schemas.common_schema import utc_now

class CertificationDB(BaseModel):
    id: str
    canonical_name: str = Field(..., description="Tên chuẩn hóa (VD: IELTS)")
    aliases: List[str] = Field(default_factory=list, description="Các biến thể (VD: IELTS Academic)")
    issuer: Optional[str] = Field(default=None, description="Tổ chức cấp (VD: British Council)")
    created_at: datetime = Field(default_factory=utc_now)

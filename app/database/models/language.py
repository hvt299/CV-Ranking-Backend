from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from app.schemas.common_schema import utc_now

class LanguageDB(BaseModel):
    id: str
    canonical_name: str = Field(..., description="Tên chuẩn hóa (VD: Tiếng Anh)")
    aliases: List[str] = Field(default_factory=list, description="Các biến thể (VD: English, EN, Tiếng Anh)")
    created_at: datetime = Field(default_factory=utc_now)

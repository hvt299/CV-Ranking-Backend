from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from app.schemas.common_schema import utc_now

class SkillDB(BaseModel):
    id: str
    canonical_name: str = Field(..., description="Tên chuẩn hóa (VD: Python)")
    industry: str = Field(..., description="Ngành nghề (Giúp phân biệt Salesforce ngành IT vs Sales)")
    aliases: List[str] = Field(default_factory=list, description="Các biến thể (VD: py, python3)")
    category: Optional[str] = Field(default=None, description="hard_skill | soft_skill | certification")
    created_at: datetime = Field(default_factory=utc_now)
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import AdminLevel

class AdministrativeUnitDB(BaseModel):
    id: str
    code: str = Field(..., description="Mã chuẩn GSO")
    name: str = Field(...)
    level: AdminLevel = Field(...)
    parent_code: Optional[str] = Field(default=None, description="Mã của tỉnh/huyện cấp trên")
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = Field(default=None, description="Null = Đang còn hiệu lực")
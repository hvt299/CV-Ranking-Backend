from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import utc_now

class RefreshTokenDB(BaseModel):
    id: str
    user_id: str = Field(...)
    token_hash: str = Field(..., description="Lưu hash, không lưu token thô")
    expires_at: datetime = Field(...)
    revoked_at: Optional[datetime] = Field(default=None, description="Thu hồi khi user đăng xuất hoặc đổi mật khẩu")
    created_at: datetime = Field(default_factory=utc_now)
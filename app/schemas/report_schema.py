from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from app.schemas.common_schema import ReportStatus, ReportTargetType
from datetime import datetime

class ReportCreate(BaseModel):
    target_type: ReportTargetType = Field(..., description="Loại đối tượng bị báo cáo")
    target_id: Optional[str] = Field(None, description="ID của đối tượng (nếu có)")
    reason: str = Field(..., description="Lý do báo cáo (VD: Lừa đảo, Spam)")
    description: str = Field(..., description="Chi tiết vụ việc")
    reporter_email: EmailStr = Field(..., description="Email người báo cáo để phản hồi")
    reporter_user_id: Optional[str] = Field(None, description="ID người báo cáo (nếu đã đăng nhập)")
    status: ReportStatus = Field(default=ReportStatus.PENDING)

class ReportResolve(BaseModel):
    admin_notes: str = Field(..., description="Ghi chú của Admin khi xử lý")
    action_taken: Optional[str] = Field(None, description="Hành động đã thực hiện (VD: Đã khóa tài khoản)")
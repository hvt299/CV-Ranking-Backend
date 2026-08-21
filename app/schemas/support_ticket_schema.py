from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from app.schemas.common_schema import TicketStatus, TicketCategory

class SupportTicketCreate(BaseModel):
    full_name: str = Field(..., description="Họ và tên người gửi")
    email: EmailStr = Field(..., description="Email liên hệ")
    category: TicketCategory = Field(..., description="Chủ đề hỗ trợ")
    subject: str = Field(..., description="Tiêu đề yêu cầu")
    description: str = Field(..., description="Nội dung chi tiết")
    user_id: Optional[str] = Field(None, description="ID người dùng (nếu đã đăng nhập)")

class SupportTicketResolve(BaseModel):
    status: TicketStatus = Field(..., description="Trạng thái mới")
    admin_notes: Optional[str] = Field(None, description="Ghi chú nội bộ của Admin")
    reply_message: Optional[str] = Field(None, description="Nội dung phản hồi (nếu có)")
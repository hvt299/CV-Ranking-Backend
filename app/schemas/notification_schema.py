from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from app.schemas.common_schema import NotificationType, NotificationActorType, NotificationActionType

class NotificationCreate(BaseModel):
    recipient_user_id: str = Field(..., description="ID người nhận")
    recipient_type: NotificationActorType = Field(...)
    
    sender_id: Optional[str] = Field(default=None, description="ID người gửi (None nếu là SYSTEM)")
    sender_type: NotificationActorType = Field(default=NotificationActorType.SYSTEM)
    
    action_type: NotificationActionType = Field(default=NotificationActionType.GENERAL_ALERT)
    
    title: str
    message: str
    type: NotificationType = Field(default=NotificationType.INFO)
    
    entity_ref: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Tham chiếu. VD: {'type': 'job', 'id': '123'}"
    )
    payload: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Dữ liệu linh hoạt cho UI. VD: {'job_title': 'Dev', 'status': 'interview'}"
    )
    action_url: Optional[str] = Field(
        default=None, 
        description="Deep-link điều hướng"
    )
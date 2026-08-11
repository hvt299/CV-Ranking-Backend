from pydantic import BaseModel, Field
from typing import Optional
from app.schemas.common_schema import NotificationType, ApplicationStatus

class NotificationCreate(BaseModel):
    recipient_user_id: str
    
    application_id: Optional[str] = None
    
    title: str
    message: str
    type: NotificationType = Field(default=NotificationType.INFO)
    
    job_title_snapshot: Optional[str] = None
    application_status_snapshot: Optional[ApplicationStatus] = None
    
    related_entity_type: Optional[str] = Field(
        default=None, 
        description="VD: 'company' | 'job' | 'application' | 'user'"
    )
    related_entity_id: Optional[str] = None
    action_url: Optional[str] = Field(
        default=None, 
        description="Deep-link để Frontend điều hướng trực tiếp khi click"
    )
from pydantic import BaseModel, Field
from typing import Optional
from app.schemas.common_schema import NotificationType, ApplicationStatus

class NotificationCreate(BaseModel):
    recipient_user_id: str
    application_id: str
    title: str
    message: str
    type: NotificationType = Field(default=NotificationType.INFO)
    job_title_snapshot: Optional[str] = None
    application_status_snapshot: Optional[ApplicationStatus] = None
from pydantic import Field
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import utc_now, NotificationReadStatus
from app.schemas.notification_schema import NotificationCreate

class NotificationDB(NotificationCreate):
    id: str
    status: NotificationReadStatus = Field(default=NotificationReadStatus.UNREAD)
    created_at: datetime = Field(default_factory=utc_now)
    read_at: Optional[datetime] = None
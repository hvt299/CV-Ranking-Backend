from pydantic import Field
from datetime import datetime
from app.schemas.common_schema import utc_now
from app.schemas.audit_schema import AuditLogCreate

class AuditLogDB(AuditLogCreate):
    id: str
    created_at: datetime = Field(default_factory=utc_now)
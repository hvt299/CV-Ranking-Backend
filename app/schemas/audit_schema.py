from pydantic import BaseModel, Field
from typing import Optional
from app.schemas.common_schema import AuditAction, UserRole

class AuditLogCreate(BaseModel):
    actor_id: str
    actor_role: UserRole
    action: AuditAction
    target_type: str = Field(
        ...,
        example="company | application | job | user"
    )
    target_id: str
    note: Optional[str] = None
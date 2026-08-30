from pydantic import BaseModel, Field
from typing import Optional, Dict
from enum import Enum
from app.schemas.common_schema import AuditAction, UserRole

class TargetEntityType(str, Enum):
    COMPANY = "company"
    APPLICATION = "application"
    JOB = "job"
    USER = "user"
    DEPARTMENT = "department"
    SUBSCRIPTION_PLAN = "subscription_plan"
    SYSTEM_SETTINGS = "system_settings"
    SKILL = "skill"
    ADMINISTRATIVE_UNIT = "administrative_unit"
    REPORT = "report"
    SUPPORT_TICKET = "support_ticket"
    BLOG_POST = "blog_post"

class AuditLogCreate(BaseModel):
    actor_id: str
    actor_role: UserRole
    action: AuditAction
    
    target_type: TargetEntityType
    target_id: str
    
    before_state: Optional[Dict] = Field(default=None, description="Trạng thái dữ liệu cũ")
    after_state: Optional[Dict] = Field(default=None, description="Trạng thái dữ liệu mới")
    
    note: Optional[str] = None
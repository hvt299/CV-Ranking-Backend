import logging
from datetime import datetime, timezone
from app.schemas.audit_schema import AuditLogCreate
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)

async def log_action(actor_id: str, actor_role: str, action: str, target_type: str, target_id: str, note: str = None, before_state: dict = None, after_state: dict = None):
    try:
        log_entry = AuditLogCreate(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_state=before_state,
            after_state=after_state,
            note=note
        ).model_dump()
        
        log_entry["created_at"] = datetime.now(timezone.utc)
        await AuditRepository.create(log_entry)
    except Exception as e:
        logger.error(f"Lỗi khi ghi Audit Log: {e}")
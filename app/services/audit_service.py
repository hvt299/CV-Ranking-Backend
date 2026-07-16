import logging
from datetime import datetime, timezone
from app.database.config import get_db, Collections
from app.database.models import AuditLogCreate

logger = logging.getLogger(__name__)

async def log_action(actor_id: str, actor_role: str, action: str, target_type: str, target_id: str, note: str = None):
    try:
        db = get_db()
        log_entry = AuditLogCreate(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            note=note
        ).model_dump()
        
        log_entry["created_at"] = datetime.now(timezone.utc)
        await db[Collections.AUDIT_LOGS].insert_one(log_entry)
    except Exception as e:
        logger.error(f"Lỗi khi ghi Audit Log: {e}")
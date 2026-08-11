import logging
from datetime import datetime, timezone
from app.schemas.audit_schema import AuditLogCreate
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)

def get_dict_diff(before: dict, after: dict):
    if not before and not after:
        return None, None
    if not before:
        return None, after
    if not after:
        return before, None

    diff_before = {}
    diff_after = {}
    
    all_keys = set(before.keys()).union(set(after.keys()))
    for key in all_keys:
        val_before = before.get(key)
        val_after = after.get(key)
        if val_before != val_after:
            diff_before[key] = val_before
            diff_after[key] = val_after

    return diff_before or None, diff_after or None

async def log_action(actor_id: str, actor_role: str, action: str, target_type: str, target_id: str, note: str = None, before_state: dict = None, after_state: dict = None):
    try:
        diff_before, diff_after = get_dict_diff(before_state or {}, after_state or {})

        log_entry = AuditLogCreate(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_state=diff_before,
            after_state=diff_after,
            note=note
        ).model_dump()
        
        log_entry["created_at"] = datetime.now(timezone.utc)
        await AuditRepository.create(log_entry)
    except Exception as e:
        logger.error(f"Lỗi khi ghi Audit Log: {e}")
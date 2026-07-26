from typing import List, Dict, Any
from app.database.config import get_db, Collections
from app.repositories.base_repository import BaseRepository

class AuditRepository(BaseRepository):
    collection_name = Collections.AUDIT_LOGS

    @classmethod
    async def find_all(cls, query: dict = {}, limit: int = 200, include_deleted: bool = False) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        # Audit log luôn cần sort mới nhất lên đầu
        cursor = db[cls.collection_name].find(query).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
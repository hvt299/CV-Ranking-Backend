from typing import Optional, List, Dict, Any
from app.database.config import get_db, Collections

class AuditRepository:
    @staticmethod
    async def find_one(query: dict) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.AUDIT_LOGS].find_one(query)
    
    @staticmethod
    async def create(log_data: dict) -> str:
        db = get_db()
        result = await db[Collections.AUDIT_LOGS].insert_one(log_data)
        return str(result.inserted_id)

    @staticmethod
    async def find_all(query: dict = {}, limit: int = 200) -> List[Dict[str, Any]]:
        db = get_db()
        cursor = db[Collections.AUDIT_LOGS].find(query).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
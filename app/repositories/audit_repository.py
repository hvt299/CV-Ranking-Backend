from typing import List, Dict, Any, Tuple
import pymongo
from app.database.config import get_db, Collections
from app.repositories.base_repository import BaseRepository

class AuditRepository(BaseRepository):
    collection_name = Collections.AUDIT_LOGS

    @classmethod
    async def get_paginated_logs(
        cls, query: dict, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        db = get_db()
        cursor = db[cls.collection_name].find(query).sort("created_at", pymongo.DESCENDING)
        
        total_items = await db[cls.collection_name].count_documents(query)
        
        skip_amount = (page - 1) * page_size
        cursor = cursor.skip(skip_amount).limit(page_size)
        
        logs = await cursor.to_list(length=page_size)
        return logs, total_items
from typing import List, Dict, Any
from app.database.config import get_db, Collections
from app.repositories.base_repository import BaseRepository

class CompanyRepository(BaseRepository):
    collection_name = Collections.COMPANIES

    @classmethod
    async def find_all_sorted(cls, query: dict = {}, limit: int = 500, include_deleted: bool = False) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        cursor = db[cls.collection_name].find(query).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db, Collections
from app.repositories.base_repository import BaseRepository

class CVRepository(BaseRepository):
    collection_name = Collections.CVS

    @classmethod
    async def get_by_email_and_company(cls, email: str, company_id: str) -> Optional[Dict[str, Any]]:
        query = {
            "company_id": company_id, 
            "candidate_info.email": email
        }
        return await cls.find_one(query)

    @classmethod
    async def delete(cls, cv_id: str, scope_filter: dict = None) -> int:
        query = {"_id": ObjectId(cv_id)}
        if scope_filter:
            query.update(scope_filter)
        # Tận dụng delete_many từ BaseRepository
        return await cls.delete_many(query)

    @classmethod
    async def find_all(cls, query: dict = {}, projection: dict = None, limit: int = 500, include_deleted: bool = False) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        # Giữ nguyên logic sort mới nhất lên đầu
        cursor = db[cls.collection_name].find(query, projection).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
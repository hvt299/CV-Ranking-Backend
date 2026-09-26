from typing import List, Dict, Any
from app.database.config import Collections, get_db
from app.repositories.base_repository import BaseRepository

class DepartmentRepository(BaseRepository):
    collection_name = Collections.DEPARTMENTS

    @classmethod
    async def get_by_company_id(cls, company_id: str) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete({"company_id": company_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("created_at", 1)
        return await cursor.to_list(length=None)

    @classmethod
    async def get_by_head_user_id(cls, head_user_id: str) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete({"head_user_id": head_user_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query)
        return await cursor.to_list(length=None)
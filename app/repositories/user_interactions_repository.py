from typing import List, Dict, Any
from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class CompanyReviewRepository(BaseRepository):
    collection_name = Collections.COMPANY_REVIEWS

    @classmethod
    async def get_by_company_id(cls, company_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        # Sắp xếp review mới nhất lên đầu
        db = cls._get_db_safe() # Giả định BaseRepository gọi được db
        query = cls._apply_soft_delete({"company_id": company_id}, include_deleted=False)
        from app.database.config import get_db
        db = get_db()
        cursor = db[cls.collection_name].find(query).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

class SavedJobRepository(BaseRepository):
    collection_name = Collections.SAVED_JOBS

    @classmethod
    async def get_by_user_id(cls, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        from app.database.config import get_db
        db = get_db()
        query = cls._apply_soft_delete({"user_id": user_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    @classmethod
    async def check_saved(cls, user_id: str, job_id: str) -> bool:
        record = await cls.find_one({"user_id": user_id, "job_id": job_id})
        return bool(record)

    @classmethod
    async def remove_saved_job(cls, user_id: str, job_id: str) -> int:
        return await cls.delete_many({"user_id": user_id, "job_id": job_id})

class JobAlertRepository(BaseRepository):
    collection_name = Collections.JOB_ALERTS

    @classmethod
    async def get_active_alerts_by_user(cls, user_id: str) -> List[Dict[str, Any]]:
        return await cls.find_many({"user_id": user_id, "is_active": True})
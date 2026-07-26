from app.database.config import Collections
from app.repositories.base_repository import BaseRepository
from typing import Optional, Dict, Any

class ApplicantProfileRepository(BaseRepository):
    collection_name = Collections.APPLICANT_PROFILES

    @classmethod
    async def get_by_user_id(cls, user_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        query = {"user_id": user_id}
        query = cls._apply_soft_delete(query, include_deleted)
        return await cls.find_one(query)
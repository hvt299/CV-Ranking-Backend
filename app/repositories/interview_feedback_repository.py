from typing import List, Dict, Any
from app.database.config import Collections, get_db
from app.repositories.base_repository import BaseRepository

class InterviewFeedbackRepository(BaseRepository):
    collection_name = Collections.INTERVIEW_FEEDBACKS

    @classmethod
    async def get_by_interview_id(cls, interview_id: str) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete({"interview_id": interview_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("created_at", -1)
        return await cursor.to_list(length=None)
        
    @classmethod
    async def get_all_by_application_id(cls, application_id: str) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete({"application_id": application_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("created_at", -1)
        return await cursor.to_list(length=None)
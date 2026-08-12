from typing import List, Dict, Any
from app.database.config import Collections, get_db
from app.repositories.base_repository import BaseRepository

class InterviewRepository(BaseRepository):
    collection_name = Collections.INTERVIEWS

    @classmethod
    async def get_by_application_id(cls, application_id: str) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete({"application_id": application_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("scheduled_time", 1)
        return await cursor.to_list(length=None)

    @classmethod
    async def get_upcoming_by_interviewer(cls, interviewer_id: str) -> List[Dict[str, Any]]:
        db = get_db()
        from datetime import datetime, timezone
        query = cls._apply_soft_delete({
            "interviewers": interviewer_id,
            "status": "scheduled",
            "scheduled_time": {"$gte": datetime.now(timezone.utc)}
        }, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("scheduled_time", 1)
        return await cursor.to_list(length=None)
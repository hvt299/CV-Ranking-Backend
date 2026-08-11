from typing import List, Dict, Any
from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class InterviewFeedbackRepository(BaseRepository):
    collection_name = Collections.INTERVIEW_FEEDBACKS

    @classmethod
    async def get_by_application_id(cls, application_id: str) -> List[Dict[str, Any]]:
        # Một ứng viên có thể được nhiều HR phỏng vấn, nên cần lấy danh sách
        from app.database.config import get_db
        db = get_db()
        query = cls._apply_soft_delete({"application_id": application_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("created_at", -1)
        return await cursor.to_list(length=None)
from typing import List, Dict, Any
from app.database.config import get_db, Collections
from app.repositories.base_repository import BaseRepository

class JobRepository(BaseRepository):
    collection_name = Collections.JOBS

    @classmethod
    async def aggregate_jobs(cls, pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        safe_pipeline = list(pipeline)

        if not safe_pipeline or "$match" not in safe_pipeline[0]:
            safe_pipeline.insert(0, {"$match": {"deleted_at": None}})
        elif "deleted_at" not in safe_pipeline[0]["$match"]:
            safe_pipeline[0]["$match"]["deleted_at"] = None

        return await db[cls.collection_name].aggregate(safe_pipeline).to_list(length=100)
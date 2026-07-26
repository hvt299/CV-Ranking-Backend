from typing import List, Dict, Any
from bson import ObjectId
from app.database.config import get_db, Collections
from app.repositories.base_repository import BaseRepository

class ApplicationRepository(BaseRepository):
    collection_name = Collections.APPLICATIONS

    @classmethod
    async def update_by_query(cls, query: dict, update_data: dict, include_deleted: bool = False) -> int:
        # Tận dụng update_custom của BaseRepository
        return await cls.update_custom(query, update_data, include_deleted)

    @classmethod
    async def delete(cls, app_id: str, scope_filter: dict = None) -> int:
        query = {"_id": ObjectId(app_id)}
        if scope_filter:
            query.update(scope_filter)
        # Tận dụng delete_many của BaseRepository
        return await cls.delete_many(query)

    @classmethod
    async def aggregate_applications(cls, pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        safe_pipeline = list(pipeline)
        
        # Nhúng cờ soft-delete vào pipeline
        if not safe_pipeline or "$match" not in safe_pipeline[0]:
            safe_pipeline.insert(0, {"$match": {"deleted_at": None}})
        elif "deleted_at" not in safe_pipeline[0]["$match"]:
            safe_pipeline[0]["$match"]["deleted_at"] = None
            
        return await db[cls.collection_name].aggregate(safe_pipeline).to_list(length=None)
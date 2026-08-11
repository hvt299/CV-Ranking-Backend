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

    @classmethod
    async def aggregate_companies(cls, pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        safe_pipeline = list(pipeline)

        if not safe_pipeline or "$match" not in safe_pipeline[0]:
            safe_pipeline.insert(0, {"$match": {"deleted_at": None}})
        elif "deleted_at" not in safe_pipeline[0]["$match"]:
            safe_pipeline[0]["$match"]["deleted_at"] = None

        return await db[cls.collection_name].aggregate(safe_pipeline).to_list(length=100)

    @classmethod
    async def aggregate_companies(cls, pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        safe_pipeline = list(pipeline)

        if not safe_pipeline or "$match" not in safe_pipeline[0]:
            safe_pipeline.insert(0, {"$match": {"deleted_at": None}})
        elif "deleted_at" not in safe_pipeline[0]["$match"]:
            safe_pipeline[0]["$match"]["deleted_at"] = None

        return await db[cls.collection_name].aggregate(safe_pipeline).to_list(length=100)

    @classmethod
    async def aggregate_companies(cls, pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        safe_pipeline = list(pipeline)

        if not safe_pipeline or "$match" not in safe_pipeline[0]:
            safe_pipeline.insert(0, {"$match": {"deleted_at": None}})
        elif "deleted_at" not in safe_pipeline[0]["$match"]:
            safe_pipeline[0]["$match"]["deleted_at"] = None

        return await db[cls.collection_name].aggregate(safe_pipeline).to_list(length=100)

    @classmethod
    async def aggregate_companies(cls, pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        safe_pipeline = list(pipeline)

        if not safe_pipeline or "$match" not in safe_pipeline[0]:
            safe_pipeline.insert(0, {"$match": {"deleted_at": None}})
        elif "deleted_at" not in safe_pipeline[0]["$match"]:
            safe_pipeline[0]["$match"]["deleted_at"] = None

        return await db[cls.collection_name].aggregate(safe_pipeline).to_list(length=100)
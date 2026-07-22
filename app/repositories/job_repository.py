from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db, Collections

class JobRepository:
    @staticmethod
    async def find_one(query: dict) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.JOBS].find_one(query)

    @staticmethod
    async def get_by_id(job_id: str, scope_filter: dict = None) -> Optional[Dict[str, Any]]:
        db = get_db()
        query = {"_id": ObjectId(job_id)}
        if scope_filter:
            query.update(scope_filter)
        return await db[Collections.JOBS].find_one(query)

    @staticmethod
    async def create(job_data: dict) -> str:
        db = get_db()
        result = await db[Collections.JOBS].insert_one(job_data)
        return str(result.inserted_id)

    @staticmethod
    async def update(job_id: str, update_data: dict, scope_filter: dict = None) -> int:
        db = get_db()
        query = {"_id": ObjectId(job_id)}
        if scope_filter:
            query.update(scope_filter)
        result = await db[Collections.JOBS].update_one(query, {"$set": update_data})
        return result.modified_count

    @staticmethod
    async def delete(job_id: str, scope_filter: dict = None) -> int:
        db = get_db()
        query = {"_id": ObjectId(job_id)}
        if scope_filter:
            query.update(scope_filter)
        result = await db[Collections.JOBS].delete_one(query)
        return result.deleted_count

    @staticmethod
    async def count_documents(query: dict) -> int:
        db = get_db()
        return await db[Collections.JOBS].count_documents(query)

    @staticmethod
    async def aggregate_jobs(pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.JOBS].aggregate(pipeline).to_list(length=100)
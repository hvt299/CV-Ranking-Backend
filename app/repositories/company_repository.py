from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
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
    async def delete(cls, doc_id: str, extra_query: Optional[dict] = None, hard_delete: bool = False) -> int:
        deleted_count = await super().delete(doc_id, extra_query, hard_delete)
        
        if deleted_count > 0:
            db = get_db()
            job_query = {"company_id": doc_id}
            app_query = {"company_id": doc_id}
            
            if hard_delete:
                await db[Collections.JOBS].delete_many(job_query)
                await db[Collections.APPLICATIONS].delete_many(app_query)
            else:
                now = datetime.now(timezone.utc)
                await db[Collections.JOBS].update_many(job_query, {"$set": {"deleted_at": now}})
                await db[Collections.APPLICATIONS].update_many(app_query, {"$set": {"deleted_at": now}})
                
        return deleted_count

    @classmethod
    async def deduct_ai_credits(cls, company_id: str, cost: int) -> bool:
        db = get_db()
        from bson import ObjectId
        
        result = await db[cls.collection_name].update_one(
            {"_id": ObjectId(company_id), "credits_remaining": {"$gte": cost}},
            {"$inc": {"credits_remaining": -cost}}
        )
        
        return result.modified_count > 0
from typing import List, Dict, Any
from bson import ObjectId
from datetime import datetime, timezone
from app.database.config import get_db, Collections
from app.repositories.base_repository import BaseRepository
from app.schemas.common_schema import ApplicationStatus

class ApplicationRepository(BaseRepository):
    collection_name = Collections.APPLICATIONS

    @classmethod
    async def update_by_query(cls, query: dict, update_data: dict, include_deleted: bool = False) -> int:
        return await cls.update_custom(query, update_data, include_deleted)

    @classmethod
    async def delete(cls, app_id: str, scope_filter: dict = None) -> int:
        query = {"_id": ObjectId(app_id)}
        if scope_filter:
            query.update(scope_filter)
        return await cls.delete_many(query)

    @classmethod
    async def aggregate_applications(cls, pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        safe_pipeline = list(pipeline)
        
        if not safe_pipeline or "$match" not in safe_pipeline[0]:
            safe_pipeline.insert(0, {"$match": {"deleted_at": None}})
        elif "deleted_at" not in safe_pipeline[0]["$match"]:
            safe_pipeline[0]["$match"]["deleted_at"] = None
            
        return await db[cls.collection_name].aggregate(safe_pipeline).to_list(length=None)

    @classmethod
    async def get_funnel_stats(cls, job_ids: List[str]) -> List[Dict[str, Any]]:
        pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        db = get_db()
        return await db[cls.collection_name].aggregate(pipeline).to_list(length=None)

    @classmethod
    async def get_ai_score_distribution(cls, job_ids: List[str]) -> List[Dict[str, Any]]:
        pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "deleted_at": None, "ai_score.total_score": {"$exists": True}}},
            {
                "$bucket": {
                    "groupBy": "$ai_score.total_score",
                    "boundaries": [0, 50, 80, 101],
                    "default": "Other",
                    "output": {"count": {"$sum": 1}}
                }
            }
        ]
        db = get_db()
        return await db[cls.collection_name].aggregate(pipeline).to_list(length=None)

    @classmethod
    async def get_todays_interviews(cls, job_ids: List[str]) -> List[Dict[str, Any]]:
        pipeline = [
            {"$match": {"job_id": {"$in": job_ids}, "status": ApplicationStatus.INTERVIEW.value, "deleted_at": None}},
            {"$sort": {"updated_at": -1}},
            {"$limit": 5},
            {
                "$project": {
                    "job_id": 1,
                    "candidate_name": {"$ifNull": ["$cv_snapshot.candidate_info.full_name", "$cv_snapshot.filename"]},
                    "status": 1
                }
            }
        ]
        db = get_db()
        return await db[cls.collection_name].aggregate(pipeline).to_list(length=5)
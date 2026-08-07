from typing import List, Dict, Any
from app.database.config import get_db, Collections
from app.repositories.base_repository import BaseRepository
from app.schemas.common_schema import JobStatus, ApplicationStatus

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

    @classmethod
    async def get_active_pipelines(cls, scope_filter: dict) -> List[Dict[str, Any]]:
        match_query = {"status": JobStatus.OPEN.value, "deleted_at": None}
        if scope_filter:
            match_query.update(scope_filter)

        pipeline = [
            {"$match": match_query},
            {
                "$lookup": {
                    "from": Collections.APPLICATIONS,
                    "let": {"job_id_str": {"$toString": "$_id"}},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$job_id", "$$job_id_str"]}, "deleted_at": None}},
                        {"$project": {"status": 1}}
                    ],
                    "as": "apps"
                }
            },
            {
                "$project": {
                    "_id": 0, 
                    "job_id": {"$toString": "$_id"},
                    "title": 1,
                    "target_hiring": {"$ifNull": ["$headcount", 0]},
                    "total_cvs": {"$size": "$apps"},
                    "new_cvs": {
                        "$size": {
                            "$filter": {
                                "input": "$apps",
                                "as": "app",
                                "cond": {"$eq": ["$$app.status", ApplicationStatus.NEW.value]}
                            }
                        }
                    },
                    "current_hired": {
                        "$size": {
                            "$filter": {
                                "input": "$apps",
                                "as": "app",
                                "cond": {"$eq": ["$$app.status", ApplicationStatus.HIRED.value]}
                            }
                        }
                    }
                }
            },
            {"$sort": {"created_at": -1}},
            {"$limit": 10}
        ]
        
        db = get_db()
        return await db[cls.collection_name].aggregate(pipeline).to_list(length=10)
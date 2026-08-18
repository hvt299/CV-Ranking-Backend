from app.database.config import Collections
from app.repositories.base_repository import BaseRepository
from typing import Optional, Dict, Any, List

class ApplicantProfileRepository(BaseRepository):
    collection_name = Collections.APPLICANT_PROFILES

    @classmethod
    async def get_by_user_id(cls, user_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        query = {"user_id": user_id}
        query = cls._apply_soft_delete(query, include_deleted)
        return await cls.find_one(query)

    @classmethod
    async def find_candidates_for_job(cls, job_data: dict, limit: int = 500) -> List[Dict[str, Any]]:
        match_query = {
            "deleted_at": None,
            "is_searchable": True,
            "primary_cv_document_id": {"$exists": True, "$ne": None}
        }

        job_salary = job_data.get("salary")
        if job_salary and job_salary.get("max_salary"):
            max_salary_hr_can_pay = job_salary.get("max_salary")
            match_query["$or"] = [
                {"expected_salary_min": {"$exists": False}},
                {"expected_salary_min": None},
                {"expected_salary_min": {"$lte": max_salary_hr_can_pay}}
            ]

        job_work_mode = job_data.get("work_mode")
        job_employment_type = job_data.get("employment_type")
        
        if job_work_mode != "Remote" and job_employment_type != "Freelance":
            job_location = job_data.get("location")
            if job_location and job_location.get("province_id"):
                job_province = job_location.get("province_id")
                
                match_query["$and"] = match_query.get("$and", []) + [{
                    "$or": [
                        {"current_location.province_id": job_province},
                        {"preferred_locations.province_id": job_province},
                        {"willing_to_relocate": True}
                    ]
                }]

        pipeline = [
            {"$match": match_query},
            {
                "$lookup": {
                    "from": Collections.CVS,
                    "let": {"primary_cv_id": {"$toObjectId": "$primary_cv_document_id"}},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$_id", "$$primary_cv_id"]}}},
                        {"$project": {"raw_text": 1, "cv_vector_ref": 1, "candidate_info": 1, "extracted_skills": 1, "display_name": 1, "file_url": 1}}
                    ],
                    "as": "cv_data"
                }
            },
            {"$unwind": {"path": "$cv_data", "preserveNullAndEmptyArrays": False}},
            {"$limit": limit}
        ]

        db = cls._get_db()
        cursor = db[cls.collection_name].aggregate(pipeline)
        return await cursor.to_list(length=limit)
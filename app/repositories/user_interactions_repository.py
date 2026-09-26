from typing import List, Dict, Any
from app.database.config import Collections, get_db
from app.repositories.base_repository import BaseRepository

class CompanyReviewRepository(BaseRepository):
    collection_name = Collections.COMPANY_REVIEWS

    @classmethod
    async def get_by_company_id(cls, company_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete({"company_id": company_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

class SavedJobRepository(BaseRepository):
    collection_name = Collections.SAVED_JOBS

    @classmethod
    async def get_by_user_id(cls, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete({"user_id": user_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    @classmethod
    async def check_saved(cls, user_id: str, job_id: str) -> bool:
        record = await cls.find_one({"user_id": user_id, "job_id": job_id})
        return bool(record)

class SavedCompanyRepository(BaseRepository):
    collection_name = Collections.SAVED_COMPANIES

    @classmethod
    async def get_by_applicant_id(cls, applicant_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete({"applicant_user_id": applicant_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    @classmethod
    async def check_saved(cls, applicant_id: str, company_id: str) -> bool:
        record = await cls.find_one({"applicant_user_id": applicant_id, "company_id": company_id})
        return bool(record)

class TalentPoolRepository(BaseRepository):
    collection_name = Collections.TALENT_POOLS

    @classmethod
    async def get_by_company_id(cls, company_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete({"company_id": company_id}, include_deleted=False)
        cursor = db[cls.collection_name].find(query).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        
        formatted_docs = []
        for doc in docs:
            formatted_doc = cls._format_doc(doc)
            applicant_id = formatted_doc.get("applicant_user_id")
            
            # Fetch cv or profile
            cv_doc = None
            profile_doc = None
            
            from bson import ObjectId
            from bson.errors import InvalidId
            try:
                cv_cursor = db[Collections.CVS].find({"_id": ObjectId(applicant_id)})
                cv_docs = await cv_cursor.to_list(length=1)
                if cv_docs:
                    cv_doc = cls._format_doc(cv_docs[0])
            except InvalidId:
                pass
                
            if not cv_doc:
                profile_cursor = db[Collections.APPLICANT_PROFILES].find({"user_id": applicant_id})
                profile_docs = await profile_cursor.to_list(length=1)
                if profile_docs:
                    profile_doc = cls._format_doc(profile_docs[0])
                    
                    user_cursor = db[Collections.USERS].find({"_id": ObjectId(applicant_id)})
                    user_docs = await user_cursor.to_list(length=1)
                    if user_docs:
                        user_data = cls._format_doc(user_docs[0])
                        profile_doc["full_name"] = user_data.get("full_name")
                        profile_doc["email"] = user_data.get("email")
                    
            formatted_doc["cv"] = cv_doc
            formatted_doc["profile"] = profile_doc
            formatted_docs.append(formatted_doc)
            
        return formatted_docs

class MatchingPreferencesRepository(BaseRepository):
    collection_name = Collections.MATCHING_PREFERENCES

    @classmethod
    async def get_by_applicant_id(cls, applicant_id: str) -> Dict[str, Any]:
        return await cls.find_one({"applicant_user_id": applicant_id, "is_active": True})
from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db, Collections

class CVRepository:
    @staticmethod
    async def find_one(query: dict) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.CVS].find_one(query)

    @staticmethod
    async def get_by_id(cv_id: str, scope_filter: dict = None) -> Optional[Dict[str, Any]]:
        db = get_db()
        query = {"_id": ObjectId(cv_id)}
        if scope_filter:
            query.update(scope_filter)
        return await db[Collections.CVS].find_one(query)

    @staticmethod
    async def get_by_email_and_company(email: str, company_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.CVS].find_one({
            "company_id": company_id, 
            "candidate_info.email": email
        })

    @staticmethod
    async def create(cv_data: dict) -> str:
        db = get_db()
        result = await db[Collections.CVS].insert_one(cv_data)
        return str(result.inserted_id)

    @staticmethod
    async def delete(cv_id: str, scope_filter: dict = None) -> int:
        db = get_db()
        query = {"_id": ObjectId(cv_id)}
        if scope_filter:
            query.update(scope_filter)
        result = await db[Collections.CVS].delete_one(query)
        return result.deleted_count

    @staticmethod
    async def find_all(query: dict = {}, projection: dict = None, limit: int = 500) -> List[Dict[str, Any]]:
        db = get_db()
        cursor = db[Collections.CVS].find(query, projection).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
        
    @staticmethod
    async def count_documents(query: dict) -> int:
        db = get_db()
        return await db[Collections.CVS].count_documents(query)
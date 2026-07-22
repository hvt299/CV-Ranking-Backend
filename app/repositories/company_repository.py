from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db, Collections

class CompanyRepository:
    @staticmethod
    async def find_one(query: dict) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.COMPANIES].find_one(query)

    @staticmethod
    async def get_by_id(company_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.COMPANIES].find_one({"_id": ObjectId(company_id)})

    @staticmethod
    async def create(company_data: dict) -> str:
        db = get_db()
        result = await db[Collections.COMPANIES].insert_one(company_data)
        return str(result.inserted_id)

    @staticmethod
    async def update(company_id: str, update_data: dict) -> int:
        db = get_db()
        result = await db[Collections.COMPANIES].update_one(
            {"_id": ObjectId(company_id)},
            {"$set": update_data}
        )
        return result.modified_count

    @staticmethod
    async def find_all(query: dict = {}, limit: int = 500) -> List[Dict[str, Any]]:
        db = get_db()
        cursor = db[Collections.COMPANIES].find(query).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
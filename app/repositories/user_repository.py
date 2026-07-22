from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db, Collections
from app.schemas.user_schema import UserCreate

class UserRepository:
    @staticmethod
    async def find_one(query: dict) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.USERS].find_one(query)

    @staticmethod
    async def get_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.USERS].find_one({"_id": ObjectId(user_id)})

    @staticmethod
    async def get_by_email(email: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.USERS].find_one({"email": email})

    @staticmethod
    async def get_by_reset_token(hashed_token: str, valid_after: Any) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.USERS].find_one({
            "reset_password_token": hashed_token,
            "reset_password_expires": {"$gt": valid_after}
        })

    @staticmethod
    async def create(user_data: dict) -> str:
        db = get_db()
        result = await db[Collections.USERS].insert_one(user_data)
        return str(result.inserted_id)

    @staticmethod
    async def update(user_id: str, update_data: dict) -> int:
        db = get_db()
        result = await db[Collections.USERS].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        return result.modified_count

    @staticmethod
    async def update_custom(query: dict, update_data: dict) -> int:
        db = get_db()
        result = await db[Collections.USERS].update_one(query, update_data)
        return result.modified_count

    @staticmethod
    async def find_all(query: dict = {}, projection: dict = None, limit: int = 500) -> List[Dict[str, Any]]:
        db = get_db()
        cursor = db[Collections.USERS].find(query, projection)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
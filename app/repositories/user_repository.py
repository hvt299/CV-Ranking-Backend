from typing import Optional, Dict, Any, List
from app.database.config import Collections, get_db
from app.repositories.base_repository import BaseRepository

class UserRepository(BaseRepository):
    collection_name = Collections.USERS

    @classmethod
    async def aggregate_users(cls, pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        cursor = db[cls.collection_name].aggregate(pipeline)
        return await cursor.to_list(length=None)

    @classmethod
    async def get_by_email(cls, email: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        query = {"email": email}
        return await cls.find_one(query, include_deleted)

    @classmethod
    async def get_by_reset_token(cls, hashed_token: str, valid_after: Any) -> Optional[Dict[str, Any]]:
        query = {
            "reset_password_token": hashed_token,
            "reset_password_expires": {"$gt": valid_after}
        }
        return await cls.find_one(query, include_deleted=False)
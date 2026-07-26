from typing import Optional, Dict, Any
from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class UserRepository(BaseRepository):
    collection_name = Collections.USERS

    @classmethod
    async def get_by_email(cls, email: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        query = {"email": email}
        # Tận dụng tối đa BaseRepository
        return await cls.find_one(query, include_deleted)

    @classmethod
    async def get_by_reset_token(cls, hashed_token: str, valid_after: Any) -> Optional[Dict[str, Any]]:
        query = {
            "reset_password_token": hashed_token,
            "reset_password_expires": {"$gt": valid_after}
        }
        return await cls.find_one(query, include_deleted=False)
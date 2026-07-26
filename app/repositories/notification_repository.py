from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db, Collections
from app.repositories.base_repository import BaseRepository

class NotificationRepository(BaseRepository):
    collection_name = Collections.NOTIFICATIONS

    @classmethod
    async def update(cls, notif_id: str, recipient_user_id: str, update_data: dict) -> int:
        query = {
            "_id": ObjectId(notif_id), 
            "recipient_user_id": recipient_user_id
        }
        return await cls.update_custom(query, {"$set": update_data})

    @classmethod
    async def delete(cls, notif_id: str, recipient_user_id: str) -> int:
        query = {
            "_id": ObjectId(notif_id),
            "recipient_user_id": recipient_user_id
        }
        return await cls.delete_many(query)

    @classmethod
    async def delete_custom(cls, query: dict) -> int:
        return await cls.delete_many(query)

    @classmethod
    async def find_all(cls, query: dict = {}, limit: int = 100, include_deleted: bool = False) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        # Notification luôn ưu tiên tin mới
        cursor = db[cls.collection_name].find(query).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db, Collections

class NotificationRepository:
    @staticmethod
    async def find_one(query: dict) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.NOTIFICATIONS].find_one(query)
    
    @staticmethod
    async def create(notif_data: dict) -> str:
        db = get_db()
        result = await db[Collections.NOTIFICATIONS].insert_one(notif_data)
        return str(result.inserted_id)

    @staticmethod
    async def update(notif_id: str, recipient_user_id: str, update_data: dict) -> int:
        db = get_db()
        result = await db[Collections.NOTIFICATIONS].update_one(
            {"_id": ObjectId(notif_id), "recipient_user_id": recipient_user_id},
            {"$set": update_data}
        )
        return result.modified_count

    @staticmethod
    async def update_custom(query: dict, update_data: dict) -> int:
        db = get_db()
        result = await db[Collections.NOTIFICATIONS].update_one(query, update_data)
        return result.modified_count

    @staticmethod
    async def update_many(query: dict, update_data: dict) -> int:
        db = get_db()
        result = await db[Collections.NOTIFICATIONS].update_many(query, {"$set": update_data})
        return result.modified_count

    @staticmethod
    async def delete(notif_id: str, recipient_user_id: str) -> int:
        db = get_db()
        result = await db[Collections.NOTIFICATIONS].delete_one({
            "_id": ObjectId(notif_id),
            "recipient_user_id": recipient_user_id
        })
        return result.deleted_count

    @staticmethod
    async def delete_custom(query: dict) -> int:
        db = get_db()
        result = await db[Collections.NOTIFICATIONS].delete_one(query)
        return result.deleted_count

    @staticmethod
    async def find_all(query: dict = {}, limit: int = 100) -> List[Dict[str, Any]]:
        db = get_db()
        cursor = db[Collections.NOTIFICATIONS].find(query).sort("created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
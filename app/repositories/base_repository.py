from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db

class BaseRepository:
    collection_name: str = None

    @classmethod
    def _apply_soft_delete(cls, query: dict, include_deleted: bool) -> dict:
        """Tự động nhúng cờ lọc dữ liệu rác (Xóa mềm)"""
        if not include_deleted and "deleted_at" not in query:
            query["deleted_at"] = None
        return query

    @classmethod
    async def find_one(cls, query: dict, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        return await db[cls.collection_name].find_one(query)

    @classmethod
    async def get_by_id(cls, doc_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        db = get_db()
        query = {"_id": ObjectId(doc_id)}
        query = cls._apply_soft_delete(query, include_deleted)
        return await db[cls.collection_name].find_one(query)

    @classmethod
    async def create(cls, data: dict) -> str:
        db = get_db()
        result = await db[cls.collection_name].insert_one(data)
        return str(result.inserted_id)

    @classmethod
    async def update(cls, doc_id: str, update_data: dict, include_deleted: bool = False) -> int:
        db = get_db()
        query = {"_id": ObjectId(doc_id)}
        query = cls._apply_soft_delete(query, include_deleted)
        result = await db[cls.collection_name].update_one(query, {"$set": update_data})
        return result.modified_count

    @classmethod
    async def update_custom(cls, query: dict, update_data: dict, include_deleted: bool = False) -> int:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        # update_data có thể chứa $set, $unset, $push...
        result = await db[cls.collection_name].update_one(query, update_data)
        return result.modified_count
        
    @classmethod
    async def update_many(cls, query: dict, update_data: dict, include_deleted: bool = False) -> int:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        result = await db[cls.collection_name].update_many(query, {"$set": update_data})
        return result.modified_count

    @classmethod
    async def find_many(cls, query: dict = {}, projection: dict = None, limit: int = 500, include_deleted: bool = False) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        cursor = db[cls.collection_name].find(query, projection)

        fetch_limit = limit if limit > 0 else None
        if fetch_limit:
            cursor = cursor.limit(fetch_limit)

        return await cursor.to_list(length=fetch_limit)

    @classmethod
    async def count_documents(cls, query: dict, include_deleted: bool = False) -> int:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        return await db[cls.collection_name].count_documents(query)

    @classmethod
    async def delete_many(cls, query: dict) -> int:
        db = get_db()
        result = await db[cls.collection_name].delete_many(query)
        return result.deleted_count
from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db
from datetime import datetime, timezone

class BaseRepository:
    collection_name: str = None

    @classmethod
    def _format_doc(cls, doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not doc:
            return None
        if "_id" in doc:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
        return doc

    @classmethod
    def sanitize_payload(cls, payload: dict) -> dict:
        if not isinstance(payload, dict): 
            return payload
        sanitized = {}
        for k, v in payload.items():
            if str(k).startswith('$'):
                continue
            sanitized[k] = cls.sanitize_payload(v) if isinstance(v, dict) else v
        return sanitized

    @classmethod
    def _apply_soft_delete(cls, query: dict, include_deleted: bool) -> dict:
        if not include_deleted and "deleted_at" not in query:
            query["deleted_at"] = None
        return query

    @classmethod
    async def find_one(cls, query: dict, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        doc = await db[cls.collection_name].find_one(query)
        return cls._format_doc(doc)

    @classmethod
    async def get_by_id(cls, doc_id: str, extra_query: Optional[dict] = None, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        if not ObjectId.is_valid(doc_id):
            return None
        db = get_db()
        query = {"_id": ObjectId(doc_id)}
        if extra_query:
            query.update(extra_query)
        query = cls._apply_soft_delete(query, include_deleted)
        doc = await db[cls.collection_name].find_one(query)
        return cls._format_doc(doc)

    @classmethod
    async def create(cls, data: dict) -> str:
        db = get_db()
        result = await db[cls.collection_name].insert_one(data)
        return str(result.inserted_id)

    @classmethod
    async def update(cls, doc_id: str, update_data: dict, extra_query: Optional[dict] = None, include_deleted: bool = False) -> int:
        if not ObjectId.is_valid(doc_id):
            return 0
        db = get_db()
        query = {"_id": ObjectId(doc_id)}
        if extra_query:
            query.update(extra_query)
        query = cls._apply_soft_delete(query, include_deleted)
        result = await db[cls.collection_name].update_one(query, {"$set": update_data})
        return result.modified_count

    @classmethod
    async def update_custom(cls, query: dict, update_data: dict, include_deleted: bool = False) -> int:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        result = await db[cls.collection_name].update_one(query, update_data)
        return result.modified_count
        
    @classmethod
    async def update_many(cls, query: dict, update_data: dict, include_deleted: bool = False) -> int:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        result = await db[cls.collection_name].update_many(query, {"$set": update_data})
        return result.modified_count

    @classmethod
    async def find_many(cls, query: dict = {}, projection: dict = None, sort: list = None, limit: int = 500, include_deleted: bool = False) -> List[Dict[str, Any]]:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        cursor = db[cls.collection_name].find(query, projection)

        if sort:
            cursor = cursor.sort(sort)

        fetch_limit = limit if limit > 0 else None
        if fetch_limit:
            cursor = cursor.limit(fetch_limit)

        docs = await cursor.to_list(length=fetch_limit)
        return [cls._format_doc(doc) for doc in docs]

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

    @classmethod
    async def delete(cls, doc_id: str, extra_query: Optional[dict] = None, hard_delete: bool = False) -> int:
        if not ObjectId.is_valid(doc_id):
            return 0
        db = get_db()
        query = {"_id": ObjectId(doc_id)}
        if extra_query:
            query.update(extra_query)

        if hard_delete:
            result = await db[cls.collection_name].delete_one(query)
            return result.deleted_count

        result = await db[cls.collection_name].update_one(
            query, {"$set": {"deleted_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count

    @classmethod
    async def distinct(cls, field: str, query: dict = {}, include_deleted: bool = False) -> list:
        db = get_db()
        query = cls._apply_soft_delete(query, include_deleted)
        return await db[cls.collection_name].distinct(field, query)
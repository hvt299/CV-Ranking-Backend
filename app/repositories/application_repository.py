from typing import Optional, List, Dict, Any
from bson import ObjectId
from app.database.config import get_db, Collections

class ApplicationRepository:
    @staticmethod
    async def find_one(query: dict) -> Optional[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.APPLICATIONS].find_one(query)

    @staticmethod
    async def get_by_id(app_id: str, scope_filter: dict = None) -> Optional[Dict[str, Any]]:
        db = get_db()
        query = {"_id": ObjectId(app_id)}
        if scope_filter:
            query.update(scope_filter)
        return await db[Collections.APPLICATIONS].find_one(query)

    @staticmethod
    async def check_exists(query: dict) -> bool:
        db = get_db()
        app = await db[Collections.APPLICATIONS].find_one(query)
        return app is not None

    @staticmethod
    async def create(app_data: dict) -> str:
        db = get_db()
        result = await db[Collections.APPLICATIONS].insert_one(app_data)
        return str(result.inserted_id)

    @staticmethod
    async def update_custom(app_id: str, update_query: dict, scope_filter: dict = None) -> int:
        db = get_db()
        query = {"_id": ObjectId(app_id)}
        if scope_filter:
            query.update(scope_filter)
        result = await db[Collections.APPLICATIONS].update_one(query, update_query)
        return result.modified_count

    @staticmethod
    async def update_by_query(query: dict, update_data: dict) -> int:
        db = get_db()
        result = await db[Collections.APPLICATIONS].update_one(query, update_data)
        return result.modified_count

    @staticmethod
    async def delete(app_id: str, scope_filter: dict = None) -> int:
        db = get_db()
        query = {"_id": ObjectId(app_id)}
        if scope_filter:
            query.update(scope_filter)
        result = await db[Collections.APPLICATIONS].delete_one(query)
        return result.deleted_count
        
    @staticmethod
    async def delete_many(query: dict) -> int:
        db = get_db()
        result = await db[Collections.APPLICATIONS].delete_many(query)
        return result.deleted_count

    @staticmethod
    async def aggregate_applications(pipeline: list) -> List[Dict[str, Any]]:
        db = get_db()
        return await db[Collections.APPLICATIONS].aggregate(pipeline).to_list(length=None)
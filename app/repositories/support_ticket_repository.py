from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class SupportTicketRepository(BaseRepository):
    collection_name = Collections.SUPPORT_TICKETS
    
    @classmethod
    async def aggregate_tickets(cls, pipeline: list) -> list:
        from app.database.config import get_db
        db = get_db()
        return await db[cls.collection_name].aggregate(pipeline).to_list(length=100)

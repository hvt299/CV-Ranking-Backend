from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class SupportTicketRepository(BaseRepository):
    collection_name = Collections.SUPPORT_TICKETS
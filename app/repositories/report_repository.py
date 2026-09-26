from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class ReportRepository(BaseRepository):
    collection_name = Collections.REPORTS
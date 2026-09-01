from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class CoverLetterRepository(BaseRepository):
    collection_name = Collections.COVER_LETTERS
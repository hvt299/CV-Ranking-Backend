from app.repositories.base_repository import BaseRepository
from app.database.config import Collections

class LanguageRepository(BaseRepository):
    collection_name = Collections.LANGUAGES

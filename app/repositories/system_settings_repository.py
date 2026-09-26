from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class SystemSettingsRepository(BaseRepository):
    collection_name = Collections.SYSTEM_SETTINGS
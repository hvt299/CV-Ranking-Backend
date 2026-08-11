from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class RefreshTokenRepository(BaseRepository):
    collection_name = Collections.REFRESH_TOKENS
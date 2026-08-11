from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class AdministrativeUnitRepository(BaseRepository):
    collection_name = Collections.ADMINISTRATIVE_UNITS
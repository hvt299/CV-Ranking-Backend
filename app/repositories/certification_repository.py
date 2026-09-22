from app.repositories.base_repository import BaseRepository
from app.database.config import Collections

class CertificationRepository(BaseRepository):
    collection_name = Collections.CERTIFICATIONS

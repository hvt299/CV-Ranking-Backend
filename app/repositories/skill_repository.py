from app.repositories.base_repository import BaseRepository
from app.database.config import Collections

class SkillRepository(BaseRepository):
    collection_name = Collections.SKILLS
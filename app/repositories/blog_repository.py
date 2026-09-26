from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class BlogRepository(BaseRepository):
    collection_name = Collections.BLOG_POSTS
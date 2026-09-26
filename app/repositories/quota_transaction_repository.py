from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class QuotaTransactionRepository(BaseRepository):
    collection_name = Collections.QUOTA_TRANSACTIONS
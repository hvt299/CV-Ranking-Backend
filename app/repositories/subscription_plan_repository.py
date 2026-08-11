from app.database.config import Collections
from app.repositories.base_repository import BaseRepository

class SubscriptionPlanRepository(BaseRepository):
    collection_name = Collections.SUBSCRIPTION_PLANS
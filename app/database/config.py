import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

class Database:
    client: AsyncIOMotorClient = None
    db = None

db_instance = Database()

class Collections:
    USERS = "users"
    COMPANIES = "companies"
    JOBS = "jobs"
    CVS = "cvs"
    APPLICATIONS = "applications"
    NOTIFICATIONS = "notifications"
    CV_VECTORS = "cv_vectors"
    JD_VECTORS = "jd_vectors"

MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "cv-ranking")

async def connect_to_mongo():
    try:
        db_instance.client = AsyncIOMotorClient(MONGO_URL)
        db_instance.db = db_instance.client.get_default_database(MONGO_DB_NAME)
        print("Đã kết nối thành công với MongoDB!")
    except Exception as e:
        print(f"Lỗi kết nối MongoDB: {e}")

async def close_mongo_connection():
    if db_instance.client is not None:
        db_instance.client.close()
        print("Đã ngắt kết nối MongoDB!")

def get_db():
    return db_instance.db
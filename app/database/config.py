import os
import pymongo
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/cv-ranking")

import redis.asyncio as aioredis

class Database:
    client: AsyncIOMotorClient = None
    db = None
    redis: aioredis.Redis = None

db_instance = Database()

class Collections:
    USERS = "users"
    COMPANIES = "companies"
    JOBS = "jobs"
    CVS = "cvs"
    APPLICATIONS = "applications"
    NOTIFICATIONS = "notifications"
    AUDIT_LOGS = "audit_logs"
    DEPARTMENTS = "departments"
    SKILLS = "skills"
    ADMINISTRATIVE_UNITS = "administrative_units"
    REFRESH_TOKENS = "refresh_tokens"
    SUBSCRIPTION_PLANS = "subscription_plans"
    PROMOTIONS = "promotions"
    QUOTA_TRANSACTIONS = "quota_transactions"
    SYSTEM_SETTINGS = "system_settings"
    APPLICANT_PROFILES = "applicant_profiles"
    COMPANY_REVIEWS = "company_reviews"
    SAVED_JOBS = "saved_jobs"
    SAVED_COMPANIES = "saved_companies"
    TALENT_POOLS = "talent_pools"
    MATCHING_PREFERENCES = "matching_preferences"
    INTERVIEWS = "interviews"
    INTERVIEW_FEEDBACKS = "interview_feedbacks"

MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "cv-ranking")

async def connect_to_mongo():
    try:
        db_instance.client = AsyncIOMotorClient(MONGO_URL)
        db_instance.db = db_instance.client.get_default_database(MONGO_DB_NAME)
        
        await db_instance.db[Collections.AUDIT_LOGS].create_index(
            [("created_at", pymongo.ASCENDING)],
            expireAfterSeconds=7776000,
            name="ttl_90_days_audit_logs"
        )
        
        REDIS_URL = os.getenv("REDIS_URL", "")
        if REDIS_URL.startswith(("redis://", "rediss://", "unix://")):
            db_instance.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            print("Đã kết nối thành công với MongoDB và Redis Cache!")
        else:
            db_instance.redis = None
            print("Đã kết nối MongoDB! (Bỏ qua Redis Cache do REDIS_URL đang dùng RAM ảo)")
    except Exception as e:
        print(f"Lỗi kết nối DB/Redis: {e}")

async def close_mongo_connection():
    if db_instance.client is not None:
        db_instance.client.close()
    if db_instance.redis is not None:
        await db_instance.redis.close()
    print("Đã ngắt kết nối DB & Redis!")

def get_db():
    return db_instance.db
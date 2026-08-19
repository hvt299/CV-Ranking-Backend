from app.core import env

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from app.middleware.rate_limit import limiter

import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database.config import connect_to_mongo, close_mongo_connection
from app.routers import auth_router, cv_router, job_router, admin_router, applicant_router, company_router, system_router, interview_router, subscription_router
from app.routers.upload_router import router as upload_router
from app.services.nlp_engine import initialize_skill_map
from datetime import timedelta
from app.repositories.job_repository import JobRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.audit_repository import AuditRepository
from app.schemas.common_schema import JobStatus, SubscriptionTier

logger = logging.getLogger("ats_cron")
scheduler = AsyncIOScheduler()

async def auto_expire_jobs():
    try:
        now = datetime.now(timezone.utc)
        modified_count = await JobRepository.update_many(
            {"status": JobStatus.OPEN.value, "deadline": {"$lt": now}},
            {"status": JobStatus.EXPIRED.value, "updated_at": now}
        )
        if modified_count > 0:
            logger.info(f"Cronjob Auto-Expire: Đã tự động đóng {modified_count} chiến dịch hết hạn.")
    except Exception as e:
        logger.error(f"Cronjob Lỗi auto_expire_jobs: {str(e)}")

async def auto_downgrade_subscriptions():
    try:
        now = datetime.now(timezone.utc)
        modified_count = await CompanyRepository.update_many(
            {
                "subscription_expires_at": {"$lt": now}, 
                "subscription_tier": {"$ne": SubscriptionTier.FREE.value}
            },
            {"subscription_tier": SubscriptionTier.FREE.value, "updated_at": now}
        )
        if modified_count > 0:
            logger.info(f"Cronjob Subscriptions: Đã tự động hạ cấp {modified_count} công ty về gói FREE.")
    except Exception as e:
        logger.error(f"Cronjob Lỗi auto_downgrade_subscriptions: {str(e)}")

async def cleanup_audit_logs():
    try:
        now = datetime.now(timezone.utc)
        ninety_days_ago = now - timedelta(days=90)
        
        deleted_count = await AuditRepository.delete_many({"created_at": {"$lt": ninety_days_ago}})
        if deleted_count > 0:
            logger.info(f"Cronjob Audit Logs: Đã xóa cứng {deleted_count} bản ghi cũ hơn 90 ngày.")
    except Exception as e:
        logger.error(f"Cronjob Lỗi cleanup_audit_logs: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    await initialize_skill_map()
    
    scheduler.add_job(auto_expire_jobs, CronTrigger(minute=0)) 
    
    scheduler.add_job(auto_downgrade_subscriptions, CronTrigger(hour=0, minute=0))
    
    scheduler.add_job(cleanup_audit_logs, CronTrigger(day_of_week='sun', hour=2, minute=0))
    
    scheduler.start()
    logger.info("Background Schedulers (Cronjobs) đã khởi động toàn diện.")
    
    yield
    
    scheduler.shutdown()
    await close_mongo_connection()

app = FastAPI(
    title="ATS SYSTEM",
    version="2.0.0", 
    description="Hệ thống Quản lý Tuyển dụng và Đánh giá Ứng viên tự động bằng AI",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(job_router.router)
app.include_router(cv_router.router)
app.include_router(applicant_router.router)
app.include_router(company_router.router)
app.include_router(upload_router)
app.include_router(system_router.router)
app.include_router(interview_router.router)
app.include_router(subscription_router.router)

@app.get("/", tags=["Health Check"])
def root():
    return {"message": "ATS System API is running smoothly!"}

@app.get("/ping", tags=["Health Check"])
def ping():
    return {"status": "ok"}
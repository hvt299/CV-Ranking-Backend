from app.core import env

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from app.middleware.rate_limit import limiter

from app.database.config import connect_to_mongo, close_mongo_connection
from app.routers import auth_router, cv_router, job_router, admin_router, applicant_router, company_router, system_router
from app.routers.upload_router import router as upload_router
from app.services.nlp_engine import initialize_skill_map

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    await initialize_skill_map()
    yield
    await close_mongo_connection()

app = FastAPI(
    title="AI CV Ranking ATS",
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

@app.get("/", tags=["Health Check"])
def root():
    return {"message": "CV Ranking System API is running smoothly!"}

@app.get("/ping", tags=["Health Check"])
def ping():
    return {"status": "ok"}
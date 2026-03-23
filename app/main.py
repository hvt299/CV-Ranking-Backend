from fastapi import FastAPI
from app.database.config import connect_to_mongo, close_mongo_connection
from app.routers import auth_router, cv_router, job_router
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()

app = FastAPI(
    title="CV Ranking System API",
    version="1.0.0",
    description="Hệ thống phân tích và xếp hạng hồ sơ ứng viên bằng AI",
    lifespan=lifespan
)

app.include_router(auth_router.router)
app.include_router(cv_router.router)
app.include_router(job_router.router)

@app.get("/", tags=["Health Check"])
def root():
    return {"message": "CV Ranking System API is running smoothly!"}

@app.get("/ping", tags=["Health Check"])
def ping():
    return {"status": "ok"}

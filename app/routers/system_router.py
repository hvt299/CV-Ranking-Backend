from fastapi import APIRouter, Query
from typing import Optional
import re

from app.repositories.administrative_unit_repository import AdministrativeUnitRepository
from app.repositories.skill_repository import SkillRepository
from app.schemas.common_schema import AdminLevel, UserRole, CompanyStatus, JobStatus, ApplicationStatus

from app.repositories.user_repository import UserRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.job_repository import JobRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.support_ticket_repository import SupportTicketRepository
from app.repositories.blog_repository import BlogRepository
from app.schemas.report_schema import ReportCreate
from app.schemas.support_ticket_schema import SupportTicketCreate
from app.schemas.common_schema import TicketStatus
from fastapi import HTTPException
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/system", tags=["System & Master Data"])

@router.post("/reports")
async def submit_report(payload: ReportCreate):
    record = payload.model_dump()
    record["created_at"] = datetime.now(timezone.utc)
    record["updated_at"] = datetime.now(timezone.utc)
    
    _id = await ReportRepository.create(record)
    return {"status": "success", "message": "Cảm ơn bạn đã báo cáo. Chúng tôi sẽ xem xét và xử lý sớm nhất có thể."}

@router.post("/support-tickets")
async def submit_support_ticket(payload: SupportTicketCreate):
    record = payload.model_dump()
    record["status"] = TicketStatus.OPEN.value
    record["created_at"] = datetime.now(timezone.utc)
    record["updated_at"] = datetime.now(timezone.utc)
    
    _id = await SupportTicketRepository.create(record)
    return {"status": "success", "message": "Gửi yêu cầu hỗ trợ thành công. Chúng tôi sẽ phản hồi qua email của bạn sớm nhất."}

@router.get("/blogs")
async def get_public_blogs(
    category: Optional[str] = Query(None, description="Lọc theo danh mục"),
    limit: int = Query(10, ge=1, le=50)
):
    query = {"is_published": True}
    if category and category != "all":
        query["category"] = category
        
    blogs = await BlogRepository.find_many(query, sort=[("created_at", -1)], limit=limit)
    return {"status": "success", "data": blogs}

@router.get("/blogs/{slug}")
async def get_blog_detail(slug: str):
    blog = await BlogRepository.find_one({"slug": slug, "is_published": True})
    if not blog:
        raise HTTPException(status_code=404, detail="Bài viết không tồn tại hoặc đã bị ẩn")
        
    await BlogRepository.update_custom(
        {"_id": blog.get("id")},
        {"$inc": {"view_count": 1}}
    )
    
    blog["view_count"] = blog.get("view_count", 0) + 1
    return {"status": "success", "data": blog}

@router.get("/locations")
async def get_locations():
    query = {"level": AdminLevel.PROVINCE.value}
    locations = await AdministrativeUnitRepository.find_many(query, limit=200)
    
    result = []
    for loc in locations:
        result.append({
            "id": loc.get("id"),
            "code": loc.get("code"),
            "name": loc.get("name"),
            "version": loc.get("version", "old")
        })
        
    result.sort(key=lambda x: x.get("name", ""))
    return result

@router.get("/skills")
async def search_skills(
    q: Optional[str] = Query(None, description="Từ khóa tìm kiếm kỹ năng"),
    industry: Optional[str] = Query(None, description="Lọc theo ngành nghề (Cross-filtering)")
):
    query = {}
    conditions = []
    
    if q and q.strip():
        regex_pattern = re.compile(f".*{re.escape(q.strip())}.*", re.IGNORECASE)
        conditions.append({
            "$or": [
                {"canonical_name": {"$regex": regex_pattern}},
                {"aliases": {"$regex": regex_pattern}}
            ]
        })
        
    if industry and industry.strip():
        conditions.append({"industry": industry})
        
    if conditions:
        query["$and"] = conditions
        
    skills = await SkillRepository.find_many(query, limit=50)
    return skills

@router.get("/locations/{parent_code}/children")
async def get_sub_locations(parent_code: str):
    query = {"parent_code": parent_code}
    locations = await AdministrativeUnitRepository.find_many(query, limit=500)
    
    result = []
    for loc in locations:
        result.append({
            "id": loc.get("id"),
            "code": loc.get("code"),
            "name": loc.get("name"),
            "parent_code": loc.get("parent_code"),
            "version": loc.get("version", "old")
        })
        
    result.sort(key=lambda x: x.get("name", ""))
    return result

@router.get("/statistics")
async def get_system_statistics():
    total_candidates = await UserRepository.count_documents({"role": UserRole.APPLICANT.value, "deleted_at": None})
    total_companies = await CompanyRepository.count_documents({"status": CompanyStatus.VERIFIED.value, "deleted_at": None})
    total_jobs = await JobRepository.count_documents({"status": JobStatus.OPEN.value, "deleted_at": None})
    
    success_rate = 0
    
    if total_jobs > 0:
        jobs_with_hq_cvs = await ApplicationRepository.distinct("job_id", {"ai_score.total_score": {"$gte": 50}})
        rate_quality = (len(jobs_with_hq_cvs) / total_jobs) * 100
        
        total_apps = await ApplicationRepository.count_documents({})
        rate_conversion = 0
        if total_apps > 0:
            success_apps = await ApplicationRepository.count_documents({
                "status": {"$in": [ApplicationStatus.INTERVIEW.value, ApplicationStatus.OFFERED.value, ApplicationStatus.HIRED.value]}
            })
            rate_conversion = (success_apps / total_apps) * 100
            
        success_rate = round((rate_quality + rate_conversion) / 2)
        success_rate = min(100, max(0, success_rate))

    return {
        "total_candidates": total_candidates,
        "total_companies": total_companies,
        "total_jobs": total_jobs,
        "success_rate": success_rate
    }
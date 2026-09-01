from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Query, HTTPException, Depends
from typing import List
from datetime import datetime, timezone
from bson import ObjectId

from app.core.security import CurrentUser, require_hr, require_hr_or_admin, get_scope_filter
from app.middleware.subscription import get_company_plan_features, require_tier
from app.database.config import Collections
from app.schemas.job_schema import JobCreateEnterprise, JobResponse
from app.schemas.common_schema import JobStatus, UserRole, CompanyStatus, AuditAction
from app.repositories.job_repository import JobRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.cv_repository import CVRepository

from app.services.nlp_engine import score_cv
from app.services.vector_engine import compress_jd_data, get_embedding, get_top_contributing_sentences
from app.services.audit_service import log_action
from app.services.analytics_service import AnalyticsService
from app.middleware.rate_limit import limiter
from fastapi import Request, Response
import os
import httpx
from app.core.security import require_qstash_signature
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/jobs", tags=["Job Management & Ranking"])

QSTASH_TOKEN = os.getenv("QSTASH_TOKEN", "")
QSTASH_URL = os.getenv("QSTASH_URL", "https://qstash-eu-central-1.upstash.io")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

async def rescore_all_applications_for_job(job_id: str, jd_data: dict):
    applications = await ApplicationRepository.find_all({"job_id": job_id}, limit=None)
    jd_search_text = jd_data.get("jd_search_text", "")
    
    for app in applications:
        cv_id = app.get("cv_snapshot", {}).get("cv_document_id")
        if not cv_id:
            continue
            
        cv_record = await CVRepository.get_by_id(cv_id)
        if not cv_record:
            continue
            
        raw_text = cv_record.get("raw_text", "")
        top_sentences = get_top_contributing_sentences(raw_text, jd_search_text)
            
        cv_data_for_scoring = {
            "raw_text": raw_text,
            "word_count": len((raw_text or "").split()),
            "skills": cv_record.get("extracted_skills", []),
            "years_of_experience": cv_record.get("candidate_info", {}).get("years_of_experience", 0),
            "skill_experience": cv_record.get("candidate_info", {}).get("skill_experience", {}),
            "education_level": cv_record.get("candidate_info", {}).get("education_level", "Không đề cập"),
            "job_hops": cv_record.get("candidate_info", {}).get("job_hops", 1),
            "gap_months": cv_record.get("candidate_info", {}).get("gap_months", 0),
            "cv_vector": cv_record.get("cv_vector_ref", []),
            "fraud_analysis": cv_record.get("candidate_info", {}).get("fraud_analysis", {}),
            "top_sentences": top_sentences
        }
        
        new_score = score_cv(cv_data_for_scoring, jd_data)
        
        await ApplicationRepository.update_by_query({"_id": ObjectId(app.get("id"))}, {"$set": {"ai_score": new_score}})
    print(f"Background Task Hoàn tất: Đã chấm lại {len(applications)} CV cho Job {job_id}")

@router.post("/")
async def create_job(job: JobCreateEnterprise, current_user: CurrentUser = Depends(require_hr)):
    features = await get_company_plan_features(current_user.company_id)
    max_active = features.get("max_active_jobs", 3)
    
    active_jobs = await JobRepository.count_documents({
        "company_id": current_user.company_id, 
        "status": JobStatus.OPEN.value
    })
    
    if active_jobs >= max_active:
        raise HTTPException(
            status_code=403, 
            detail=f"Công ty đã đạt giới hạn mở tối đa {max_active} chiến dịch cùng lúc. Vui lòng nâng cấp gói cước."
        )
    
    job_dict = job.model_dump()

    if current_user.role != UserRole.ADMIN:
        job_dict["company_id"] = current_user.company_id

        features = await get_company_plan_features(current_user.company_id)
        if not features.get("can_set_hot_job", False):
            job_dict.pop("is_hot", None)

    company = await CompanyRepository.get_by_id(job_dict["company_id"])
    if not company or company.get("status") != CompanyStatus.VERIFIED.value:
        raise HTTPException(
            status_code=403, 
            detail="Công ty của bạn chưa được xác thực (KYC). Vui lòng chờ Admin duyệt để có thể đăng chiến dịch tuyển dụng."
        )

    if not job_dict.get("industry") or job_dict["industry"] == "other":
        company_industries = company.get("industries", ["other"])
        job_dict["industry"] = company_industries[0] if company_industries else "other"

    compressed_jd = compress_jd_data(job_dict)
    jd_vector = await get_embedding(compressed_jd)
    
    jd_search_text = f"{job.description} {job.requirements} {job.benefits or ''} {job.other_info or ''}".lower()
    
    job_dict.update({
        "created_by_user_id": current_user.id,
        "created_at": datetime.now(timezone.utc),
        "status": JobStatus.OPEN.value,
        "jd_search_text": jd_search_text,
        "jd_vector_ref": jd_vector
    })
    
    job_id = await JobRepository.create(job_dict)
    return {"message": "Tạo chiến dịch thành công", "job_id": job_id}

@router.get("/", response_model=List[JobResponse], dependencies=[Depends(require_hr_or_admin)])
async def get_my_jobs(scope_filter: dict = Depends(get_scope_filter)):
    pipeline = []
    if scope_filter:
        pipeline.append({"$match": scope_filter})
        
    pipeline.extend([
        {"$sort": {"created_at": -1}},
        {"$limit": 100},
        {
            "$lookup": {
                "from": Collections.COMPANIES,
                "let": {"c_id": {"$toObjectId": "$company_id"}},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$_id", "$$c_id"]}}},
                    {"$project": {"name": 1}}
                ],
                "as": "company_info"
            }
        },
        {"$unwind": {"path": "$company_info", "preserveNullAndEmptyArrays": True}}
    ])
    
    jobs = await JobRepository.aggregate_jobs(pipeline)
    
    result = []
    for job in jobs:
        job["id"] = job.get("id") or str(job.pop("_id", ""))
        
        job["company_name"] = job.get("company_info", {}).get("name", "Công ty Ẩn danh")
        
        job.pop("company_info", None)
        
        result.append(job)
        
    return result

@router.get("/{job_id}", response_model=JobResponse, dependencies=[Depends(require_hr_or_admin)])
async def get_job_detail(job_id: str, scope_filter: dict = Depends(get_scope_filter)):
    try:
        obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Định dạng ID không hợp lệ")

    job = await JobRepository.find_one({"_id": obj_id, **scope_filter})
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch hoặc bạn không có quyền xem")
    return job

@router.put("/{job_id}")
@limiter.limit("20/day")
async def update_job(
    request: Request,
    response: Response,
    job_id: str,
    background_tasks: BackgroundTasks,
    job_update: JobCreateEnterprise = Body(...),
    current_user: CurrentUser = Depends(require_hr),
    scope_filter: dict = Depends(get_scope_filter)
):
    update_data = job_update.model_dump()
    
    if current_user.role != UserRole.ADMIN:
        features = await get_company_plan_features(current_user.company_id)
        if not features.get("can_set_hot_job", False):
            update_data.pop("is_hot", None)

        company = await CompanyRepository.get_by_id(current_user.company_id)
        if not company or company.get("status") != CompanyStatus.VERIFIED.value:
            raise HTTPException(
                status_code=403, 
                detail="Công ty của bạn chưa được xác thực (KYC). Vui lòng chờ Admin duyệt để có thể cập nhật chiến dịch tuyển dụng."
            )
    
    existing_job = await JobRepository.get_by_id(job_id, extra_query=scope_filter)
    
    if not existing_job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job hoặc bạn không có quyền chỉnh sửa")

    features = await get_company_plan_features(current_user.company_id)
    max_edits = features.get("max_job_edits", 5)
    current_edits = existing_job.get("edit_count", 0)
    
    if current_edits >= max_edits:
        raise HTTPException(status_code=403, detail=f"Chiến dịch đã đạt giới hạn chỉnh sửa ({max_edits} lần). Nhằm tối ưu hệ thống AI, vui lòng tạo chiến dịch mới nếu thay đổi quá nhiều.")

    update_data = job_update.model_dump()
    update_data["edit_count"] = current_edits + 1
    
    if current_user.role != UserRole.ADMIN:
        update_data.pop("is_hot", None)

    if not update_data.get("industry") or update_data["industry"] == "other":
        target_company_id = update_data.get("company_id") or existing_job.get("company_id")
        if target_company_id:
            company_data = await CompanyRepository.get_by_id(target_company_id)
            if company_data:
                company_industries = company_data.get("industries", ["other"])
                update_data["industry"] = company_industries[0] if company_industries else "other"

    compressed_jd = compress_jd_data(update_data)
    
    new_jd_vector = await get_embedding(compressed_jd)
    
    jd_search_text = f"{job_update.description} {job_update.requirements} {job_update.benefits or ''} {job_update.other_info or ''}".lower()
    
    update_data.update({
        "updated_at": datetime.now(timezone.utc), 
        "jd_search_text": jd_search_text,
        "jd_vector_ref": new_jd_vector
    })

    await JobRepository.update(job_id, update_data, extra_query=scope_filter)

    before_state = {k: v for k, v in existing_job.items() if k != "_id"}
    after_state = {**before_state, **update_data}

    await log_action(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action=AuditAction.JOB_UPDATED if hasattr(AuditAction, 'JOB_UPDATED') else "job_updated",
        target_type="job",
        target_id=job_id,
        note="Cập nhật JD hoặc Trọng số AI",
        before_state=before_state,
        after_state=after_state
    )

    max_rescores = features.get("max_rescores_per_job", 2)
    current_rescores = existing_job.get("rescore_count", 0)

    if current_rescores < max_rescores:
        # Cập nhật số lần rescore ngầm
        await JobRepository.update_custom({"_id": ObjectId(job_id)}, {"$inc": {"rescore_count": 1}})
        
        if QSTASH_TOKEN:
            try:
                target_webhook_url = f"{BACKEND_URL}/api/v1/jobs/internal/webhook/rescore"
                async with httpx.AsyncClient() as client:
                    await client.post(
                    f"{QSTASH_URL}{target_webhook_url}",
                    headers={
                        "Authorization": f"Bearer {QSTASH_TOKEN}",
                        "Content-Type": "application/json"
                    },
                    json={"job_id": job_id}
                )
            except Exception as e:
                print(f"[QStash Error] Không thể gửi lệnh rescore cho job {job_id}: {e}")
    else:
        background_tasks.add_task(rescore_all_applications_for_job, job_id, update_data)

    return {
        "status": "success", 
        "message": "Cập nhật JD thành công. Hệ thống đã đưa tác vụ chấm lại CV vào hàng đợi Serverless."
    }

@router.delete("/{job_id}", dependencies=[Depends(require_hr)])
async def delete_job(job_id: str, scope_filter: dict = Depends(get_scope_filter)):
    deleted_count = await JobRepository.delete(job_id, extra_query=scope_filter)
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job hoặc bạn không có quyền xóa")
        
    await ApplicationRepository.delete_many({"job_id": job_id})
    return {"status": "success", "message": "Đã xóa chiến dịch. CV ứng viên vẫn được bảo lưu trong Kho hồ sơ."}

@router.get("/{job_id}/ranking", dependencies=[Depends(require_hr_or_admin)])
async def get_job_ranking(job_id: str, scope_filter: dict = Depends(get_scope_filter)):
    try:
        job = await JobRepository.get_by_id(job_id, extra_query=scope_filter)
    except:
        raise HTTPException(status_code=400, detail="Mã Job không hợp lệ")
        
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch hoặc bạn không có quyền xem")

    company_info = None
    if job.get("company_id"):
        try:
            company = await CompanyRepository.get_by_id(job["company_id"])
            if company:
                company["id"] = company.get("id") or str(company.pop("_id", ""))
                company_info = company
        except:
            pass

    match_stage = {"job_id": job_id}
    if scope_filter:
        match_stage.update(scope_filter)

    pipeline = [
        {"$match": match_stage},
        {"$sort": {"ai_score.total_score": -1}},
        {"$limit": 200}
    ]
    
    applications = await ApplicationRepository.aggregate_applications(pipeline)
    
    leaderboard = []
    for app in applications:
        app["id"] = app.get("id") or str(app.pop("_id", ""))
        
        cv_snap = app.get("cv_snapshot", {})
        app["candidate_info"] = cv_snap.get("candidate_info", {})
        app["filename"] = cv_snap.get("filename", "CV Không xác định")
        app["extracted_skills"] = cv_snap.get("extracted_skills", [])
        app["file_url"] = cv_snap.get("file_url", "")
        
        leaderboard.append(app)
        
    job["id"] = job.get("id") or str(job.pop("_id", ""))
    
    return {
        "job_info": job,
        "company_info": company_info,
        "total_candidates": len(leaderboard),
        "leaderboard": leaderboard
    }

@router.get("/{job_id}/export", dependencies=[Depends(require_tier("can_export_analytics"))])
async def export_job_analytics(
    job_id: str, 
    format: str = Query("excel", description="Định dạng: excel hoặc pdf"), 
    scope_filter: dict = Depends(get_scope_filter)
):
    job = await JobRepository.get_by_id(job_id, extra_query=scope_filter)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch tuyển dụng")
        
    # TODO: Tích hợp thư viện Pandas/ReportLab trả về StreamingResponse ở Phase 5
    return {
        "status": "success", 
        "message": f"Yêu cầu xuất báo cáo {format.upper()} đã được tiếp nhận.",
        "download_url": f"https://s3.cloud/reports/mock_{job_id}.{format}"
    }

@router.get("/dashboard/metrics")
async def get_dashboard_metrics(
    scope: str = Query("company", description="Góc nhìn: 'company' (Owner) hoặc 'me' (Member)"),
    current_user: CurrentUser = Depends(require_hr)
):
    if scope == "me":
        data = await AnalyticsService.get_member_workspace_metrics(current_user.id)
        return {"status": "success", "data": data}
    else:
        if current_user.role != UserRole.HR_OWNER.value:
            raise HTTPException(status_code=403, detail="Chỉ HR Owner mới được xem số liệu toàn công ty")
            
        data = await AnalyticsService.get_owner_dashboard_metrics(current_user.company_id)
        return {"status": "success", "data": data}

@router.get("/public/list", response_model=List[JobResponse])
async def get_public_jobs():
    pipeline = [
        {"$match": {"status": JobStatus.OPEN.value}},
        {"$sort": {"created_at": -1}},
        {"$limit": 100},
        {
            "$lookup": {
                "from": Collections.COMPANIES,
                "let": {"c_id": {"$toObjectId": "$company_id"}},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$_id", "$$c_id"]}}},
                    {"$project": {"name": 1}}
                ],
                "as": "company_info"
            }
        },
        {"$unwind": {"path": "$company_info", "preserveNullAndEmptyArrays": True}}
    ]
    
    jobs = await JobRepository.aggregate_jobs(pipeline)
    
    result = []
    for job in jobs:
        job["id"] = job.get("id") or str(job.pop("_id", ""))
        job["company_name"] = job.get("company_info", {}).get("name", "Công ty Ẩn danh")
        job.pop("company_info", None)
        result.append(job)
        
    return result

@router.get("/public/{job_id}", response_model=JobResponse)
async def get_public_job_detail(job_id: str):
    try:
        obj_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Định dạng ID không hợp lệ")

    pipeline = [
        {"$match": {"_id": obj_id, "status": JobStatus.OPEN.value}},
        {
            "$lookup": {
                "from": Collections.COMPANIES,
                "let": {"c_id": {"$toObjectId": "$company_id"}},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$_id", "$$c_id"]}}},
                    {"$project": {"name": 1}}
                ],
                "as": "company_info"
            }
        },
        {"$unwind": {"path": "$company_info", "preserveNullAndEmptyArrays": True}}
    ]

    jobs = await JobRepository.aggregate_jobs(pipeline)
    
    if not jobs or len(jobs) == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy việc làm hoặc chiến dịch đã đóng")
        
    job = jobs[0]
    job["id"] = job.get("id") or str(job.pop("_id", ""))
    
    current_views = job.get("view_count", 0)
    await JobRepository.update_custom({"_id": obj_id}, {"$inc": {"view_count": 1}})
    job["view_count"] = current_views + 1
    
    job["company_name"] = job.get("company_info", {}).get("name", "Công ty Ẩn danh")
    job.pop("company_info", None)
    
    return job

class RescoreWebhookPayload(BaseModel):
    job_id: str

@router.post("/internal/webhook/rescore", dependencies=[Depends(require_qstash_signature)], include_in_schema=False)
async def webhook_rescore_job(payload: RescoreWebhookPayload):
    job_id = payload.job_id
    
    jd_data = await JobRepository.get_by_id(job_id)
    if not jd_data:
        return {"status": "ignored", "message": "Job không còn tồn tại"}
        
    await rescore_all_applications_for_job(job_id, jd_data)
    
    return {"status": "success", "message": f"Đã chấm lại toàn bộ CV cho Job {job_id}"}
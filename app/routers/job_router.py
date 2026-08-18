from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Query, HTTPException, Depends
from typing import List
from datetime import datetime, timezone
from bson import ObjectId

from app.core.security import CurrentUser, require_hr, require_hr_or_admin, get_scope_filter
from app.middleware.subscription import verify_job_quota
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

router = APIRouter(prefix="/api/v1/jobs", tags=["Job Management & Ranking"])

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
        
        await ApplicationRepository.update_by_query({"_id": app["_id"]}, {"$set": {"ai_score": new_score}})
    print(f"Background Task Hoàn tất: Đã chấm lại {len(applications)} CV cho Job {job_id}")

@router.post("/")
async def create_job(job: JobCreateEnterprise, current_user: CurrentUser = Depends(verify_job_quota)):
    job_dict = job.model_dump()

    if current_user.role != UserRole.ADMIN:
        job_dict["company_id"] = current_user.company_id

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
        job["id"] = str(job["_id"])
        
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
        
    job["id"] = str(job["_id"])
    return job

@router.put("/{job_id}")
async def update_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    job_update: JobCreateEnterprise = Body(...),
    current_user: CurrentUser = Depends(require_hr),
    scope_filter: dict = Depends(get_scope_filter)
):
    if current_user.role != UserRole.ADMIN:
        company = await CompanyRepository.get_by_id(current_user.company_id)
        if not company or company.get("status") != CompanyStatus.VERIFIED.value:
            raise HTTPException(
                status_code=403, 
                detail="Công ty của bạn chưa được xác thực (KYC). Vui lòng chờ Admin duyệt để có thể cập nhật chiến dịch tuyển dụng."
            )
    
    existing_job = await JobRepository.get_by_id(job_id, extra_query=scope_filter)
    
    if not existing_job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job hoặc bạn không có quyền chỉnh sửa")

    update_data = job_update.model_dump()
    
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

    background_tasks.add_task(rescore_all_applications_for_job, job_id, update_data)

    return {
        "status": "success", 
        "message": "Cập nhật JD thành công. Hệ thống đang tự động chấm lại điểm ứng viên ở chế độ chạy ngầm."
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
                company["id"] = str(company["_id"])
                del company["_id"]
                company_info = company
        except:
            pass

    pipeline = [
        {"$match": {"job_id": job_id}},
        {"$sort": {"ai_score.total_score": -1}},
        {"$limit": 200}
    ]
    
    applications = await ApplicationRepository.aggregate_applications(pipeline)
    
    leaderboard = []
    for app in applications:
        app["id"] = str(app["_id"])
        del app["_id"]
        
        cv_snap = app.get("cv_snapshot", {})
        app["candidate_info"] = cv_snap.get("candidate_info", {})
        app["filename"] = cv_snap.get("filename", "CV Không xác định")
        app["extracted_skills"] = cv_snap.get("extracted_skills", [])
        app["file_url"] = cv_snap.get("file_url", "")
        
        leaderboard.append(app)
        
    job["id"] = str(job["_id"])
    del job["_id"]
    
    return {
        "job_info": job,
        "company_info": company_info,
        "total_candidates": len(leaderboard),
        "leaderboard": leaderboard
    }

@router.get("/dashboard/metrics", dependencies=[Depends(require_hr)])
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
        job["id"] = str(job["_id"])
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
    job["id"] = str(job["_id"])
    
    current_views = job.get("view_count", 0)
    await JobRepository.update_custom({"_id": obj_id}, {"$inc": {"view_count": 1}})
    job["view_count"] = current_views + 1
    
    job["company_name"] = job.get("company_info", {}).get("name", "Công ty Ẩn danh")
    job.pop("company_info", None)
    
    return job
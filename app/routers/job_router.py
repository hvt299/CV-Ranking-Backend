from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks
from typing import List
from datetime import datetime, timezone
from bson import ObjectId

from app.auth import CurrentUser, require_hr, require_hr_or_admin, get_scope_filter
from app.database.config import get_db, Collections
from app.database.models import JobCreateEnterprise, JobResponse, JobStatus, UserRole, ApplicationStatus, CompanyStatus
from app.services.nlp_engine import score_cv
from app.services.vector_engine import compress_jd_data, get_embedding

router = APIRouter(prefix="/api/v1/jobs", tags=["Job Management & Ranking"])

async def rescore_all_applications_for_job(job_id: str, jd_data: dict):
    db = get_db()
    cursor = db[Collections.APPLICATIONS].find({"job_id": job_id})
    applications = await cursor.to_list(length=None)
    
    for app in applications:
        cv_id = app["cv_id"]
        cv_record = await db[Collections.CVS].find_one({"_id": ObjectId(cv_id)})
        if not cv_record:
            continue
            
        cv_data_for_scoring = {
            "raw_text": cv_record.get("raw_text", ""),
            "word_count": len((cv_record.get("raw_text", "") or "").split()),
            "skills": cv_record.get("extracted_skills", []),
            "years_of_experience": cv_record.get("candidate_info", {}).get("years_of_experience", 0),
            "skill_experience": cv_record.get("candidate_info", {}).get("skill_experience", {}),
            "education_level": cv_record.get("candidate_info", {}).get("education_level", "Không đề cập"),
            "job_hops": cv_record.get("candidate_info", {}).get("job_hops", 1),
            "gap_months": cv_record.get("candidate_info", {}).get("gap_months", 0),
            "cv_vector": cv_record.get("cv_vector_ref", [])
        }
        
        new_score = score_cv(cv_data_for_scoring, jd_data)
        
        await db[Collections.APPLICATIONS].update_one(
            {"_id": app["_id"]},
            {"$set": {"ai_score": new_score}}
        )
    print(f"Background Task Hoàn tất: Đã chấm lại {len(applications)} CV cho Job {job_id}")


@router.post("/")
async def create_job(job: JobCreateEnterprise, current_user: CurrentUser = Depends(require_hr)):
    db = get_db()
    job_dict = job.model_dump()

    if current_user.role != UserRole.ADMIN:
        job_dict["company_id"] = current_user.company_id

    company = await db[Collections.COMPANIES].find_one({"_id": ObjectId(job_dict["company_id"])})
    if not company or company.get("status") != CompanyStatus.VERIFIED.value:
        raise HTTPException(
            status_code=403, 
            detail="Công ty của bạn chưa được xác thực (KYC). Vui lòng chờ Admin duyệt để có thể đăng chiến dịch tuyển dụng."
        )

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
    
    result = await db[Collections.JOBS].insert_one(job_dict)
    return {"message": "Tạo chiến dịch thành công", "job_id": str(result.inserted_id)}

@router.get("/", response_model=List[JobResponse], dependencies=[Depends(require_hr_or_admin)])
async def get_my_jobs(scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
    
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
    
    jobs = await db[Collections.JOBS].aggregate(pipeline).to_list(length=100)
    
    result = []
    for job in jobs:
        job["id"] = str(job["_id"])
        
        job["company_name"] = job.get("company_info", {}).get("name", "Công ty Ẩn danh")
        
        job.pop("company_info", None)
        
        result.append(job)
        
    return result

@router.get("/{job_id}", response_model=JobResponse, dependencies=[Depends(require_hr_or_admin)])
async def get_job_detail(job_id: str, scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
    filter_query = {"_id": ObjectId(job_id), **scope_filter}
    
    job = await db[Collections.JOBS].find_one(filter_query)
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
    db = get_db()

    if current_user.role != UserRole.ADMIN:
        company = await db[Collections.COMPANIES].find_one({"_id": ObjectId(current_user.company_id)})
        if not company or company.get("status") != CompanyStatus.VERIFIED.value:
            raise HTTPException(
                status_code=403, 
                detail="Công ty của bạn chưa được xác thực (KYC). Vui lòng chờ Admin duyệt để có thể cập nhật chiến dịch tuyển dụng."
            )
    
    filter_query = {"_id": ObjectId(job_id), **scope_filter}
    existing_job = await db[Collections.JOBS].find_one(filter_query)
    
    if not existing_job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job hoặc bạn không có quyền chỉnh sửa")

    update_data = job_update.model_dump()
    compressed_jd = compress_jd_data(update_data)
    
    new_jd_vector = await get_embedding(compressed_jd)
    
    jd_search_text = f"{job_update.description} {job_update.requirements} {job_update.benefits or ''} {job_update.other_info or ''}".lower()
    
    update_data.update({
        "updated_at": datetime.now(timezone.utc), 
        "jd_search_text": jd_search_text,
        "jd_vector_ref": new_jd_vector
    })

    await db[Collections.JOBS].update_one(filter_query, {"$set": update_data})
    
    background_tasks.add_task(rescore_all_applications_for_job, job_id, update_data)
    
    return {
        "status": "success", 
        "message": "Cập nhật JD thành công. Hệ thống đang tự động chấm lại điểm ứng viên ở chế độ chạy ngầm."
    }


@router.delete("/{job_id}", dependencies=[Depends(require_hr)])
async def delete_job(job_id: str, scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
    filter_query = {"_id": ObjectId(job_id), **scope_filter}
    
    result = await db[Collections.JOBS].delete_one(filter_query)
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job hoặc bạn không có quyền xóa")
        
    await db[Collections.APPLICATIONS].delete_many({"job_id": job_id})
    return {"status": "success", "message": "Đã xóa chiến dịch. CV ứng viên vẫn được bảo lưu trong Kho hồ sơ."}


@router.get("/{job_id}/ranking", dependencies=[Depends(require_hr_or_admin)])
async def get_job_ranking(job_id: str, scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
    
    try:
        job_filter = {"_id": ObjectId(job_id), **scope_filter}
        job = await db[Collections.JOBS].find_one(job_filter)
    except:
        raise HTTPException(status_code=400, detail="Mã Job không hợp lệ")
        
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch hoặc bạn không có quyền xem")

    company_info = None
    if job.get("company_id"):
        try:
            company = await db[Collections.COMPANIES].find_one({"_id": ObjectId(job["company_id"])})
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
    
    applications = await db[Collections.APPLICATIONS].aggregate(pipeline).to_list(length=200)
    
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

@router.get("/dashboard/analytics", dependencies=[Depends(require_hr_or_admin)])
async def get_dashboard_analytics(scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
    
    total_jobs = await db[Collections.JOBS].count_documents(scope_filter)
    
    open_jobs_filter = {"status": JobStatus.OPEN.value, **scope_filter}
    open_jobs = await db[Collections.JOBS].count_documents(open_jobs_filter)
    
    total_cvs_in_pool = await db[Collections.CVS].count_documents(scope_filter)
    
    pipeline = []
    if scope_filter:
        pipeline.append({"$match": scope_filter})
    pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})
    
    status_counts = await db[Collections.APPLICATIONS].aggregate(pipeline).to_list(length=None)
    
    status_breakdown = {
        item["_id"] if item["_id"] else ApplicationStatus.NEW.value: item["count"] 
        for item in status_counts
    }
    
    return {
        "total_jobs": total_jobs,
        "open_jobs": open_jobs,
        "total_cvs_in_pool": total_cvs_in_pool,
        "status_breakdown": status_breakdown
    }
from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks
from typing import List
from datetime import datetime, timezone
from bson import ObjectId

from app.auth import get_current_user
from app.database.config import get_db
from app.database.models import JobCreateEnterprise, JobResponse
from app.services.nlp_engine import score_cv

router = APIRouter(prefix="/api/v1/jobs", tags=["Job Management & Ranking"])

async def rescore_all_applications_for_job(job_id: str, jd_data: dict, current_hr: str):
    db = get_db()
    cursor = db["hr_applications"].find({"job_id": job_id})
    applications = await cursor.to_list(length=None)
    
    for app in applications:
        cv_id = app["cv_id"]
        cv_record = await db["hr_cvs"].find_one({"_id": ObjectId(cv_id)})
        if not cv_record:
            continue
            
        cv_data_for_scoring = {
            "raw_text": cv_record.get("raw_text", ""),
            "skills": cv_record.get("extracted_skills", []),
            "years_of_experience": cv_record["candidate_info"].get("years_of_experience", 0),
            "skill_experience": cv_record["candidate_info"].get("skill_experience", {}),
            "education_level": cv_record["candidate_info"].get("education_level", "Không đề cập")
        }
        
        new_score = score_cv(cv_data_for_scoring, jd_data)
        
        await db["hr_applications"].update_one(
            {"_id": app["_id"]},
            {"$set": {"ai_score": new_score}}
        )
    print(f"Background Task Hoàn tất: Đã chấm lại {len(applications)} CV cho Job {job_id}")

@router.post("/")
async def create_job(job: JobCreateEnterprise, current_hr: str = Depends(get_current_user)):
    db = get_db()
    job_dict = job.model_dump()
    jd_search_text = f"{job.description} {job.requirements} {job.benefits or ''} {job.other_info or ''}".lower()
    
    job_dict.update({
        "created_by": current_hr,
        "created_at": datetime.now(timezone.utc),
        "status": "open",
        "jd_search_text": jd_search_text
    })
    
    result = await db["hr_jobs"].insert_one(job_dict)
    return {"message": "Tạo chiến dịch thành công", "job_id": str(result.inserted_id)}

@router.get("/", response_model=List[JobResponse])
async def get_my_jobs(current_hr: str = Depends(get_current_user)):
    db = get_db()
    cursor = db["hr_jobs"].find({"created_by": current_hr}).sort("created_at", -1)
    jobs = await cursor.to_list(length=100)
    for job in jobs:
        job["id"] = str(job["_id"])
    return jobs

@router.get("/{job_id}", response_model=JobResponse)
async def get_job_detail(job_id: str, current_hr: str = Depends(get_current_user)):
    db = get_db()
    job = await db["hr_jobs"].find_one({"_id": ObjectId(job_id), "created_by": current_hr})
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")
    job["id"] = str(job["_id"])
    return job

@router.put("/{job_id}")
async def update_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    job_update: JobCreateEnterprise = Body(...),
    current_hr: str = Depends(get_current_user)
):
    db = get_db()
    existing_job = await db["hr_jobs"].find_one({"_id": ObjectId(job_id), "created_by": current_hr})
    if not existing_job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job hoặc bạn không có quyền chỉnh sửa")

    update_data = job_update.model_dump()
    jd_search_text = f"{job_update.description} {job_update.requirements} {job_update.benefits or ''} {job_update.other_info or ''}".lower()
    update_data.update({"updated_at": datetime.now(timezone.utc), "jd_search_text": jd_search_text})

    await db["hr_jobs"].update_one({"_id": ObjectId(job_id)}, {"$set": update_data})
    
    background_tasks.add_task(rescore_all_applications_for_job, job_id, update_data, current_hr)
    
    return {
        "status": "success", 
        "message": "Cập nhật JD thành công. Hệ thống đang tự động chấm lại điểm ứng viên ở chế độ chạy ngầm."
    }

@router.delete("/{job_id}")
async def delete_job(job_id: str, current_hr: str = Depends(get_current_user)):
    db = get_db()
    result = await db["hr_jobs"].delete_one({"_id": ObjectId(job_id), "created_by": current_hr})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job hoặc bạn không có quyền xóa")
        
    await db["hr_applications"].delete_many({"job_id": job_id})
    return {"status": "success", "message": "Đã xóa chiến dịch. CV ứng viên vẫn được bảo lưu trong Kho hồ sơ."}

@router.get("/{job_id}/ranking")
async def get_job_ranking(job_id: str, current_hr: str = Depends(get_current_user)):
    db = get_db()
    job = await db["hr_jobs"].find_one({"_id": ObjectId(job_id), "created_by": current_hr})
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")

    cursor = db["hr_applications"].find({"job_id": job_id}).sort("ai_score.total_score", -1)
    applications = await cursor.to_list(length=200)
    
    leaderboard = []
    for app in applications:
        app["id"] = str(app["_id"])
        del app["_id"]
        
        cv_record = await db["hr_cvs"].find_one({"_id": ObjectId(app["cv_id"])})
        if cv_record:
            app["candidate_info"] = cv_record.get("candidate_info", {})
            app["filename"] = cv_record.get("filename", "")
            app["extracted_skills"] = cv_record.get("extracted_skills", [])
            
        leaderboard.append(app)
        
    job["id"] = str(job["_id"])
    del job["_id"]
    
    return {
        "job_info": job,
        "total_candidates": len(leaderboard),
        "leaderboard": leaderboard
    }

@router.get("/dashboard/analytics")
async def get_dashboard_analytics(current_hr: str = Depends(get_current_user)):
    db = get_db()
    total_jobs = await db["hr_jobs"].count_documents({"created_by": current_hr})
    open_jobs = await db["hr_jobs"].count_documents({"created_by": current_hr, "status": "open"})
    total_cvs_in_pool = await db["hr_cvs"].count_documents({"hr_email": current_hr})
    
    pipeline = [
        {"$match": {"hr_email": current_hr}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    status_counts = await db["hr_applications"].aggregate(pipeline).to_list(length=None)
    status_breakdown = {item["_id"] if item["_id"] else "Mới": item["count"] for item in status_counts}
    
    return {
        "total_jobs": total_jobs,
        "open_jobs": open_jobs,
        "total_cvs_in_pool": total_cvs_in_pool,
        "status_breakdown": status_breakdown
    }
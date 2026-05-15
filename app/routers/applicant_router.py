from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from bson import ObjectId
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel

from app.auth import get_current_user
from app.database.config import get_db
from app.services.nlp_engine import extract_text, analyze_cv_text, score_cv

router = APIRouter(prefix="/api/v1/apply", tags=["Applicant"])

MAX_FILE_SIZE = 5 * 1024 * 1024

class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str = "info"  # success, error, info, warning
    job_title: Optional[str] = None
    application_id: Optional[str] = None
    application_status: Optional[str] = None

async def require_applicant(current_user: str = Depends(get_current_user)):
    db = get_db()
    user = await db["hr_users"].find_one({"email": current_user})
    if not user or user.get("role") not in ("applicant", "admin"):
        raise HTTPException(status_code=403, detail="Chỉ Applicant mới có thể nộp đơn ứng tuyển")
    return current_user

@router.get("/jobs")
async def list_open_jobs():
    """Danh sách job đang mở — public, không cần đăng nhập"""
    db = get_db()
    cursor = db["hr_jobs"].find({"status": "open"}).sort("created_at", -1)
    jobs = await cursor.to_list(length=100)
    result = []
    for job in jobs:
        result.append({
            "id": str(job["_id"]),
            "title": job.get("title"),
            "company_name": job.get("company_name"),
            "job_level": job.get("job_level"),
            "work_mode": job.get("work_mode"),
            "employment_type": job.get("employment_type"),
            "location": job.get("location"),
            "salary": job.get("salary"),
            "deadline": job.get("deadline"),
            "description": job.get("description"),
            "requirements": job.get("requirements"),
            "benefits": job.get("benefits"),
            "required_skills": [s.get("name") for s in job.get("required_skills", [])],
            "created_at": job.get("created_at"),
        })
    return result

@router.post("/jobs/{job_id}")
async def apply_to_job(
    job_id: str,
    file: UploadFile = File(...),
    current_applicant: str = Depends(require_applicant)
):
    db = get_db()

    try:
        job = await db["hr_jobs"].find_one({"_id": ObjectId(job_id), "status": "open"})
    except Exception:
        raise HTTPException(status_code=400, detail="Job ID không hợp lệ")

    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy vị trí tuyển dụng hoặc đã đóng")

    deadline = job.get("deadline")
    if deadline:
        if isinstance(deadline, str):
            from datetime import timezone as tz
            deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > deadline:
            raise HTTPException(status_code=400, detail="Chiến dịch tuyển dụng đã hết hạn nộp hồ sơ")

    # Kiểm tra đã nộp chưa
    existing = await db["applicant_submissions"].find_one({
        "applicant_email": current_applicant,
        "job_id": job_id
    })
    if existing:
        raise HTTPException(status_code=400, detail="Bạn đã nộp hồ sơ cho vị trí này rồi!")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File vượt quá 5MB")

    raw_text = await extract_text(file, content)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Không thể đọc nội dung file")

    cv_data = analyze_cv_text(raw_text)
    scoring_result = score_cv({
        "raw_text": raw_text,
        "skills": cv_data.get("skills", []),
        "years_of_experience": cv_data.get("years_of_experience", 0),
        "skill_experience": cv_data.get("skill_experience", {}),
        "education_level": cv_data.get("education_level", "Không đề cập")
    }, job)

    submission = {
        "applicant_email": current_applicant,
        "job_id": job_id,
        "job_title": job.get("title"),
        "hr_email": job.get("created_by"),
        "filename": file.filename,
        "candidate_info": {
            "email": cv_data.get("email") or current_applicant,
            "phone": cv_data.get("phone"),
            "github": cv_data.get("github"),
            "linkedin": cv_data.get("linkedin"),
            "education_level": cv_data.get("education_level"),
            "years_of_experience": cv_data.get("years_of_experience", 0),
            "skill_experience": cv_data.get("skill_experience", {}),
        },
        "extracted_skills": cv_data.get("skills", []),
        "raw_text": raw_text,
        "ai_score": scoring_result,
        "status": "Mới",
        "note": "",
        "submitted_at": datetime.now(timezone.utc)
    }

    result = await db["applicant_submissions"].insert_one(submission)

    # Đồng thời tạo bản ghi trong hr_applications để HR thấy trong leaderboard
    cv_pool_record = {
        "hr_email": job.get("created_by"),
        "filename": file.filename,
        "raw_text": raw_text,
        "candidate_info": submission["candidate_info"],
        "extracted_skills": cv_data.get("skills", []),
        "applicant_email": current_applicant,
        "created_at": datetime.now(timezone.utc)
    }
    cv_result = await db["hr_cvs"].insert_one(cv_pool_record)

    app_record = {
        "hr_email": job.get("created_by"),
        "job_id": job_id,
        "cv_id": str(cv_result.inserted_id),
        "ai_score": scoring_result,
        "status": "Mới",
        "note": "",
        "applied_at": datetime.now(timezone.utc),
        "source": "applicant",
        "applicant_email": current_applicant
    }
    await db["hr_applications"].insert_one(app_record)

    return {
        "status": "success",
        "message": f"Nộp hồ sơ thành công cho vị trí '{job.get('title')}'",
        "submission_id": str(result.inserted_id)
    }

@router.get("/my-applications")
async def my_applications(current_applicant: str = Depends(require_applicant)):
    db = get_db()
    cursor = db["applicant_submissions"].find(
        {"applicant_email": current_applicant},
        {"raw_text": 0, "ai_score": 0}
    ).sort("submitted_at", -1)
    apps = await cursor.to_list(length=100)
    for a in apps:
        a["id"] = str(a["_id"])
        del a["_id"]
    return apps

# Notification endpoints
@router.get("/notifications")
async def get_notifications(current_applicant: str = Depends(require_applicant)):
    """Lấy danh sách thông báo của ứng viên"""
    db = get_db()
    cursor = db["applicant_notifications"].find(
        {"applicant_email": current_applicant}
    ).sort("created_at", -1)
    notifications = await cursor.to_list(length=100)
    
    for notification in notifications:
        notification["id"] = str(notification["_id"])
        del notification["_id"]
    
    return notifications

@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_applicant: str = Depends(require_applicant)
):
    """Đánh dấu thông báo đã đọc"""
    db = get_db()
    
    try:
        result = await db["applicant_notifications"].update_one(
            {
                "_id": ObjectId(notification_id),
                "applicant_email": current_applicant
            },
            {"$set": {"status": "read", "read_at": datetime.now(timezone.utc)}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
            
        return {"status": "success", "message": "Đã đánh dấu thông báo là đã đọc"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="ID thông báo không hợp lệ")

@router.patch("/notifications/read-all")
async def mark_all_notifications_read(current_applicant: str = Depends(require_applicant)):
    """Đánh dấu tất cả thông báo đã đọc"""
    db = get_db()
    
    result = await db["applicant_notifications"].update_many(
        {
            "applicant_email": current_applicant,
            "status": "unread"
        },
        {"$set": {"status": "read", "read_at": datetime.now(timezone.utc)}}
    )
    
    return {
        "status": "success", 
        "message": f"Đã đánh dấu {result.modified_count} thông báo là đã đọc"
    }

@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_applicant: str = Depends(require_applicant)
):
    """Xóa thông báo"""
    db = get_db()
    
    try:
        result = await db["applicant_notifications"].delete_one(
            {
                "_id": ObjectId(notification_id),
                "applicant_email": current_applicant
            }
        )
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
            
        return {"status": "success", "message": "Đã xóa thông báo"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="ID thông báo không hợp lệ")

# Helper function to create notifications
async def create_notification(
    applicant_email: str,
    title: str,
    message: str,
    notification_type: str = "info",
    job_title: Optional[str] = None,
    application_id: Optional[str] = None,
    application_status: Optional[str] = None
):
    """Tạo thông báo mới cho ứng viên"""
    db = get_db()
    
    notification = {
        "applicant_email": applicant_email,
        "title": title,
        "message": message,
        "type": notification_type,
        "status": "unread",
        "job_title": job_title,
        "application_id": application_id,
        "application_status": application_status,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db["applicant_notifications"].insert_one(notification)
    return notification
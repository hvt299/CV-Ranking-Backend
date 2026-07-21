from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request, Form, Response

from pydantic import BaseModel
from bson import ObjectId
from datetime import datetime, timezone

from app.auth import get_current_user, CurrentUser
from app.database.config import get_db, Collections
from app.database.models import (
    UserRole, 
    JobStatus, 
    ApplicationStatus, 
    ApplicationSource, 
    NotificationReadStatus
)
from app.services.nlp_engine import extract_text, analyze_cv_text, score_cv
from app.services.vector_engine import compress_cv_data, get_embedding, get_cv_embeddings, get_top_contributing_sentences
from app.services.document_forensics import detect_hidden_text
from app.middleware.rate_limit import limiter
from app.services.storage_service import upload_file_to_cloudinary, delete_file_from_cloudinary
from typing import Optional

router = APIRouter(prefix="/api/v1/apply", tags=["Applicant"])
MAX_FILE_SIZE = 5 * 1024 * 1024

async def require_applicant(current_user: CurrentUser = Depends(get_current_user)):
    if current_user.role != UserRole.APPLICANT:
        raise HTTPException(
            status_code=403, 
            detail="Chỉ ứng viên (Applicant) mới có thể thực hiện thao tác này"
        )
    return current_user

@router.get("/jobs")
async def list_open_jobs():
    db = get_db()
    pipeline = [
        {"$match": {"status": JobStatus.OPEN.value}},
        {"$sort": {"created_at": -1}},
        {"$limit": 100},
        {
            "$lookup": {
                "from": Collections.COMPANIES,
                "let": {"comp_id": {"$toObjectId": "$company_id"}},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$_id", "$$comp_id"]}}},
                    {"$project": {"name": 1}}
                ],
                "as": "company_info"
            }
        },
        {
            "$unwind": {
                "path": "$company_info",
                "preserveNullAndEmptyArrays": True
            }
        }
    ]
    
    jobs = await db[Collections.JOBS].aggregate(pipeline).to_list(length=100)
    
    result = []
    for job in jobs:
        company_name = job.get("company_info", {}).get("name", "Công ty Ẩn danh")
        
        result.append({
            "id": str(job["_id"]),
            "title": job.get("title"),
            "company_id": job.get("company_id"),
            "company_name": company_name,

            "status": job.get("status"),
            "is_hot": job.get("is_hot", False),
            "industry": job.get("industry"),

            "job_level": job.get("job_level"),
            "employment_type": job.get("employment_type"),
            "work_mode": job.get("work_mode"),

            "headcount": job.get("headcount"),
            "min_yoe": job.get("min_yoe"),

            "location": job.get("location"),
            "salary": job.get("salary"),
            "deadline": job.get("deadline"),
            "education": job.get("education"),

            "description": job.get("description"),
            "requirements": job.get("requirements"),
            "benefits": job.get("benefits"),

            "required_skills": [
                s.get("name") for s in job.get("required_skills", [])
            ],

            "created_at": job.get("created_at"),
        })
    return result

@router.get("/my-applications")
async def my_applications(current_applicant: CurrentUser = Depends(require_applicant)):
    db = get_db()
    
    pipeline = [
        {"$match": {"applicant_user_id": current_applicant.id}},
        {"$sort": {"applied_at": -1}},
        {"$limit": 100},
        {"$project": {
            "ai_score": 0, 
            "note": 0, 
            "notes": 0 
        }},
        {
            "$lookup": {
                "from": Collections.JOBS,
                "let": {"j_id": {"$toObjectId": "$job_id"}},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$_id", "$$j_id"]}}},
                    {"$project": {"title": 1}}
                ],
                "as": "job_info"
            }
        },
        {"$unwind": {"path": "$job_info", "preserveNullAndEmptyArrays": True}},
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
    
    apps = await db[Collections.APPLICATIONS].aggregate(pipeline).to_list(length=100)
    
    result = []
    for a in apps:
        a["id"] = str(a["_id"])
        del a["_id"]
                
        a["job_title"] = a.get("job_info", {}).get("title", "Chiến dịch đã xóa")
        a["company_name"] = a.get("company_info", {}).get("name", "Công ty Ẩn danh")
        
        a.pop("job_info", None)
        a.pop("company_info", None)
        
        result.append(a)
        
    return result

@router.get("/notifications")
async def get_notifications(current_applicant: CurrentUser = Depends(require_applicant)):
    db = get_db()
    cursor = db[Collections.NOTIFICATIONS].find(
        {"recipient_user_id": current_applicant.id}
    ).sort("created_at", -1)
    
    notifications = await cursor.to_list(length=100)
    for notification in notifications:
        notification["id"] = str(notification["_id"])
        del notification["_id"]
    
    return notifications

@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    db = get_db()
    try:
        result = await db[Collections.NOTIFICATIONS].update_one(
            {
                "_id": ObjectId(notification_id),
                "recipient_user_id": current_applicant.id
            },
            {
                "$set": {
                    "status": NotificationReadStatus.READ.value, 
                    "read_at": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
            
        return {"status": "success", "message": "Đã đánh dấu thông báo là đã đọc"}
    except Exception:
        raise HTTPException(status_code=400, detail="ID thông báo không hợp lệ")

@router.patch("/notifications/read-all")
async def mark_all_notifications_read(current_applicant: CurrentUser = Depends(require_applicant)):
    db = get_db()
    
    result = await db[Collections.NOTIFICATIONS].update_many(
        {
            "recipient_user_id": current_applicant.id,
            "status": NotificationReadStatus.UNREAD.value
        },
        {
            "$set": {
                "status": NotificationReadStatus.READ.value, 
                "read_at": datetime.now(timezone.utc)
            }
        }
    )
    
    return {
        "status": "success", 
        "message": f"Đã đánh dấu {result.modified_count} thông báo là đã đọc"
    }

@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    db = get_db()
    try:
        result = await db[Collections.NOTIFICATIONS].delete_one(
            {
                "_id": ObjectId(notification_id),
                "recipient_user_id": current_applicant.id
            }
        )
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
            
        return {"status": "success", "message": "Đã xóa thông báo"}
    except Exception:
        raise HTTPException(status_code=400, detail="ID thông báo không hợp lệ")

class ApplyJobRequest(BaseModel):
    cv_document_id: str
    cover_letter: Optional[str] = None

class SelfScoreRequest(BaseModel):
    cv_document_id: str
    job_id: str

@router.post("/library/upload")
@limiter.limit("20/day")
async def upload_cv_to_library(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    display_name: str = Form("CV Của Tôi"),
    current_applicant: CurrentUser = Depends(require_applicant)
):
    db = get_db()
    content = await file.read()
    
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Dung lượng file vượt quá 5MB.")
        
    raw_text = await extract_text(file, content)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Không thể đọc nội dung file")

    fraud_result = None
    if file.filename.lower().endswith((".pdf", ".docx")):
        fraud_result = detect_hidden_text(content, file.filename)
        
    cv_data = await analyze_cv_text(raw_text)
    
    file_url = await upload_file_to_cloudinary(content, file.filename)
    compressed_text = compress_cv_data(raw_text, cv_data, cv_data.get("skills", []))
    cv_vector = await get_cv_embeddings(compressed_text)
    
    cv_doc = {
        "display_name": display_name,
        "filename": file.filename,
        "file_url": file_url,
        "raw_text": raw_text,
        "cv_vector_ref": cv_vector,
        "candidate_info": {
            "email": cv_data.get("email") or current_applicant.email,
            "phone": cv_data.get("phone"),
            "education_level": cv_data.get("education_level", "Không đề cập"),
            "years_of_experience": cv_data.get("years_of_experience", 0),
            "skill_experience": cv_data.get("skill_experience", {}),
            "job_hops": cv_data.get("job_hops", 1),
            "gap_months": cv_data.get("gap_months", 0),
            "fraud_analysis": fraud_result
        },
        "extracted_skills": cv_data.get("skills", []),
        "owner_user_id": current_applicant.id,
        "created_at": datetime.now(timezone.utc)
    }
    
    result = await db[Collections.CVS].insert_one(cv_doc)
    return {
        "status": "success",
        "cv_document_id": str(result.inserted_id),
        "file_url": file_url,
        "filename": file.filename
    }

@router.post("/jobs/{job_id}")
@limiter.limit("20/day")
async def apply_to_job(
    request: Request,
    response: Response,
    job_id: str,
    payload: ApplyJobRequest,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    db = get_db()
    
    job = await db[Collections.JOBS].find_one({"_id": ObjectId(job_id), "status": JobStatus.OPEN.value})
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy vị trí tuyển dụng hoặc đã đóng")
        
    if await db[Collections.APPLICATIONS].find_one({"applicant_user_id": current_applicant.id, "job_id": job_id}):
        raise HTTPException(status_code=400, detail="Bạn đã nộp hồ sơ cho vị trí này rồi!")

    cv_doc = await db[Collections.CVS].find_one({"_id": ObjectId(payload.cv_document_id), "owner_user_id": current_applicant.id})
    if not cv_doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy CV trong thư viện cá nhân")

    raw_text = cv_doc.get("raw_text", "")
    top_sentences = get_top_contributing_sentences(raw_text, job.get("jd_search_text", ""))
    cover_letter=payload.cover_letter

    scoring_result = score_cv({
        "raw_text": raw_text,
        "word_count": len((raw_text or "").split()),
        "skills": cv_doc.get("extracted_skills", []),
        "years_of_experience": cv_doc.get("candidate_info", {}).get("years_of_experience", 0),
        "skill_experience": cv_doc.get("candidate_info", {}).get("skill_experience", {}),
        "education_level": cv_doc.get("candidate_info", {}).get("education_level", "Không đề cập"),
        "job_hops": cv_doc.get("candidate_info", {}).get("job_hops", 1),
        "gap_months": cv_doc.get("candidate_info", {}).get("gap_months", 0),
        "cv_vector": cv_doc.get("cv_vector_ref", []),
        "fraud_analysis": cv_doc.get("candidate_info", {}).get("fraud_analysis", {}),
        "top_sentences": top_sentences
    }, job)

    cv_snapshot = {
        "cv_document_id": str(cv_doc["_id"]),
        "display_name": cv_doc.get("display_name", "CV Ứng tuyển"),
        "filename": cv_doc.get("filename"),
        "file_url": cv_doc.get("file_url", ""),
        "candidate_info": cv_doc.get("candidate_info", {}),
        "extracted_skills": cv_doc.get("extracted_skills", [])
    }

    app_record = {
        "job_id": job_id,
        "cv_snapshot": cv_snapshot,
        "company_id": job.get("company_id"),
        "applicant_user_id": current_applicant.id,
        "source": ApplicationSource.APPLICANT_APPLY.value,
        "status": ApplicationStatus.NEW.value,
        "ai_score": scoring_result,
        "applied_at": datetime.now(timezone.utc),
        "cover_letter": cover_letter
    }
    await db[Collections.APPLICATIONS].insert_one(app_record)

    return {"status": "success", "message": "Nộp hồ sơ thành công bằng CV từ thư viện!"}

@router.get("/library")
async def get_my_cv_library(current_applicant: CurrentUser = Depends(require_applicant)):
    db = get_db()
    cursor = db[Collections.CVS].find(
        {"owner_user_id": current_applicant.id}, 
        {"raw_text": 0, "cv_vector_ref": 0}
    ).sort("created_at", -1)
    
    cvs = await cursor.to_list(length=10)
    for cv in cvs:
        cv["id"] = str(cv["_id"])
        del cv["_id"]
    return cvs

@router.post("/self-score")
@limiter.limit("20/day")
async def self_score_cv(
    request: Request,
    response: Response,
    payload: SelfScoreRequest,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    db = get_db()
    
    job = await db[Collections.JOBS].find_one({"_id": ObjectId(payload.job_id), "status": JobStatus.OPEN.value})
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy vị trí tuyển dụng hoặc đã đóng")
        
    cv_doc = await db[Collections.CVS].find_one({"_id": ObjectId(payload.cv_document_id), "owner_user_id": current_applicant.id})
    if not cv_doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy CV trong thư viện cá nhân")

    raw_text = cv_doc.get("raw_text", "")
    top_sentences = get_top_contributing_sentences(raw_text, job.get("jd_search_text", ""))

    scoring_result = score_cv({
        "raw_text": raw_text,
        "word_count": len((raw_text or "").split()),
        "skills": cv_doc.get("extracted_skills", []),
        "years_of_experience": cv_doc.get("candidate_info", {}).get("years_of_experience", 0),
        "skill_experience": cv_doc.get("candidate_info", {}).get("skill_experience", {}),
        "education_level": cv_doc.get("candidate_info", {}).get("education_level", "Không đề cập"),
        "job_hops": cv_doc.get("candidate_info", {}).get("job_hops", 1),
        "gap_months": cv_doc.get("candidate_info", {}).get("gap_months", 0),
        "cv_vector": cv_doc.get("cv_vector_ref", []),
        "fraud_analysis": cv_doc.get("candidate_info", {}).get("fraud_analysis", {}),
        "top_sentences": top_sentences
    }, job)

    return {
        "status": "success", 
        "message": "Tính điểm dự kiến thành công",
        "ai_score": scoring_result
    }

@router.delete("/library/{cv_id}")
async def delete_cv_from_library(cv_id: str, current_applicant: CurrentUser = Depends(require_applicant)):
    db = get_db()
    
    cv_record = await db[Collections.CVS].find_one({
        "_id": ObjectId(cv_id), 
        "owner_user_id": current_applicant.id
    })
    
    if not cv_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy CV")
        
    if cv_record.get("file_url"):
        await delete_file_from_cloudinary(cv_record["file_url"])
        
    await db[Collections.CVS].delete_one({"_id": ObjectId(cv_id)})
        
    return {"status": "success", "message": "Đã xóa CV khỏi thư viện cá nhân"}
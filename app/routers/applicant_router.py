from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request, Form, Response

from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, timezone

from app.core.security import get_current_user, CurrentUser
from app.database.config import Collections
from app.repositories.applicant_profile_repository import ApplicantProfileRepository
from app.schemas.common_schema import UserRole, JobStatus, ApplicationStatus, ApplicationSource, NotificationReadStatus, NotificationType, NotificationActorType, NotificationActionType
from app.schemas.user_interaction_schema import SavedCompanyCreate, MatchingPreferencesCreate, MatchingPreferencesUpdate
from app.repositories.job_repository import JobRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.cv_repository import CVRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_interactions_repository import SavedCompanyRepository, MatchingPreferencesRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.audit_repository import AuditRepository

from app.services.audit_service import log_action
from app.services.nlp_engine import extract_text, analyze_cv_text, score_cv
from app.services.vector_engine import compress_cv_data, get_cv_embeddings, get_top_contributing_sentences
from app.services.document_forensics import detect_hidden_text
from app.middleware.rate_limit import limiter
from app.services.storage_service import upload_file_to_cloudinary, delete_file_from_cloudinary, is_safe_url
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

def _prepare_cv_for_scoring(cv_doc: dict, job: dict) -> dict:
    raw_text = cv_doc.get("raw_text", "")
    top_sentences = get_top_contributing_sentences(raw_text, job.get("jd_search_text", ""))
    return {
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
    }

@router.get("/jobs")
async def list_open_jobs():
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
    
    jobs = await JobRepository.aggregate_jobs(pipeline)
    
    result = []
    for job in jobs:
        company_name = job.get("company_info", {}).get("name", "Công ty Ẩn danh")
        
        result.append({
            "id": job.get("id") or str(job.pop("_id", "")),
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
    
    apps = await ApplicationRepository.aggregate_applications(pipeline)
    
    result = []
    for a in apps:
        a["id"] = a.get("id") or str(a.pop("_id", ""))
        
        a["job_title"] = a.get("job_info", {}).get("title", "Chiến dịch đã xóa")
        a["company_name"] = a.get("company_info", {}).get("name", "Công ty Ẩn danh")
        
        a.pop("job_info", None)
        a.pop("company_info", None)
        
        result.append(a)
        
    return result

@router.get("/notifications")
async def get_notifications(current_applicant: CurrentUser = Depends(require_applicant)):
    notifications = await NotificationRepository.find_all({"recipient_user_id": current_applicant.id}, limit=100)
    return notifications

@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    try:
        modified_count = await NotificationRepository.update(
            notif_id=notification_id, 
            recipient_user_id=current_applicant.id, 
            update_data={"status": NotificationReadStatus.READ.value, "read_at": datetime.now(timezone.utc)}
        )
        if modified_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
            
        return {"status": "success", "message": "Đã đánh dấu thông báo là đã đọc"}
    except Exception:
        raise HTTPException(status_code=400, detail="ID thông báo không hợp lệ")

@router.patch("/notifications/read-all")
async def mark_all_notifications_read(current_applicant: CurrentUser = Depends(require_applicant)):
    modified_count = await NotificationRepository.update_many(
        {"recipient_user_id": current_applicant.id, "status": NotificationReadStatus.UNREAD.value},
        {"status": NotificationReadStatus.READ.value, "read_at": datetime.now(timezone.utc)}
    )
    
    return {
        "status": "success", 
        "message": f"Đã đánh dấu {modified_count} thông báo là đã đọc"
    }

@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    try:
        deleted_count = await NotificationRepository.delete(notif_id=notification_id, recipient_user_id=current_applicant.id)
        if deleted_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
            
        return {"status": "success", "message": "Đã xóa thông báo"}
    except Exception:
        raise HTTPException(status_code=400, detail="ID thông báo không hợp lệ")

class ApplyJobRequest(BaseModel):
    cv_document_id: Optional[str] = Field(default=None, description="Để trống nếu muốn dùng CV Mặc định (1-Click Apply)")
    cover_letter_id: Optional[str] = Field(default=None, description="ID của Thư giới thiệu (Optional)")

class SelfScoreRequest(BaseModel):
    cv_document_id: str
    job_id: str

async def get_applicant_plan_features(user_id: str) -> dict:
    async def _get_free_features():
        free_plan = await SubscriptionPlanRepository.find_one({"plan_code": "app_free", "is_active": True})
        if free_plan:
            return free_plan.get("features", {})
        return {
            "max_cv_uploads": 3, 
            "max_cover_letters_uploads": 3, 
            "max_job_applies_per_day": 10, 
            "max_self_scores_per_day": 3, 
            "ai_credits": 0
        }

    profile = await ApplicantProfileRepository.get_by_user_id(user_id)
    if not profile:
        return await _get_free_features()
    
    plan_id = profile.get("current_plan_id")
    if not plan_id:
        return await _get_free_features()
        
    plan = await SubscriptionPlanRepository.get_by_id(plan_id)
    return plan.get("features", {}) if plan else await _get_free_features()

@router.post("/library/upload")
@limiter.limit("20/day")
async def upload_cv_to_library(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    display_name: str = Form("CV Của Tôi"),
    current_applicant: CurrentUser = Depends(require_applicant)
):
    features = await get_applicant_plan_features(current_applicant.id)
    max_uploads = features.get("max_cv_uploads", 3)
    
    current_cv_count = await CVRepository.count_documents({"owner_user_id": current_applicant.id})
    if current_cv_count >= max_uploads:
        raise HTTPException(
            status_code=403, 
            detail=f"Thư viện của bạn đã đạt giới hạn {max_uploads} CV. Vui lòng xóa bớt hoặc nâng cấp gói cước."
        )
    
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

    existing_cvs = await CVRepository.count_documents({"owner_user_id": current_applicant.id})
    is_primary = True if existing_cvs == 0 else False
    
    if existing_cvs >= max_uploads:
        raise HTTPException(
            status_code=403, 
            detail=f"Thư viện của bạn đã đạt giới hạn {max_uploads} CV. Vui lòng xóa bớt hoặc nâng cấp gói cước."
        )
    
    cv_doc = {
        "display_name": display_name,
        "is_primary": is_primary,
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
    
    cv_id = await CVRepository.create(cv_doc)
    return {
        "status": "success",
        "cv_document_id": str(cv_id),
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
    features = await get_applicant_plan_features(current_applicant.id)
    max_applies = features.get("max_job_applies_per_day", 10)

    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    apps_today = await ApplicationRepository.count_documents({
        "applicant_user_id": current_applicant.id,
        "applied_at": {"$gte": start_of_day}
    })
    if apps_today >= max_applies:
        raise HTTPException(
            status_code=403, 
            detail=f"Bạn đã đạt giới hạn ứng tuyển {max_applies} công việc/ngày. Vui lòng quay lại vào ngày mai."
        )
    
    job = await JobRepository.find_one({"_id": ObjectId(job_id), "status": JobStatus.OPEN.value})
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy vị trí tuyển dụng hoặc đã đóng")
        
    deadline = job.get("deadline")
    if deadline:
        now_utc = datetime.now(timezone.utc)
        deadline_dt = datetime.fromisoformat(deadline.replace("Z", "+00:00")) if isinstance(deadline, str) else deadline
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            
        if now_utc > deadline_dt:
            raise HTTPException(
                status_code=400, 
                detail=f"Chiến dịch đã hết hạn vào {deadline_dt.strftime('%d/%m/%Y %H:%M')}. Bạn không thể ứng tuyển."
            )
        
    if await ApplicationRepository.find_one({"applicant_user_id": current_applicant.id, "job_id": job_id}):
        raise HTTPException(status_code=400, detail="Bạn đã nộp hồ sơ cho vị trí này rồi!")

    # Validate Cover Letter ID nếu có truyền lên
    if payload.cover_letter_id:
        from app.repositories.cover_letter_repository import CoverLetterRepository
        cl_doc = await CoverLetterRepository.find_one({"_id": ObjectId(payload.cover_letter_id), "owner_user_id": current_applicant.id})
        if not cl_doc:
            raise HTTPException(status_code=404, detail="Không tìm thấy Thư giới thiệu trong thư viện cá nhân.")

    if not payload.cv_document_id:
        cv_doc = await CVRepository.find_one({"owner_user_id": current_applicant.id, "is_primary": True})
        if not cv_doc:
            raise HTTPException(status_code=400, detail="Bạn chưa có CV mặc định. Vui lòng chọn 1 CV cụ thể hoặc tải lên thư viện.")
    else:
        cv_doc = await CVRepository.find_one({"_id": ObjectId(payload.cv_document_id), "owner_user_id": current_applicant.id})
        if not cv_doc:
            raise HTTPException(status_code=404, detail="Không tìm thấy CV trong thư viện cá nhân.")

    cv_data_for_scoring = _prepare_cv_for_scoring(cv_doc, job)
    scoring_result = score_cv(cv_data_for_scoring, job)

    cv_snapshot = {
        "cv_document_id": str(cv_doc.get("id")),
        "display_name": cv_doc.get("display_name", "CV Ứng tuyển"),
        "filename": cv_doc.get("filename"),
        "file_url": cv_doc.get("file_url", ""),
        "candidate_info": cv_doc.get("candidate_info", {}),
        "extracted_skills": cv_doc.get("extracted_skills", [])
    }

    app_record = {
        "job_id": job_id,
        "cv_id": str(cv_doc.get("id")),
        "cv_snapshot": cv_snapshot,
        "company_id": job.get("company_id"),
        "applicant_user_id": current_applicant.id,
        "source": ApplicationSource.APPLICANT_APPLY.value,
        "status": ApplicationStatus.NEW.value,
        "ai_score": scoring_result,
        "applied_at": datetime.now(timezone.utc),
        "cover_letter_id": payload.cover_letter_id
    }
    app_id = await ApplicationRepository.create(app_record)

    hr_owner_id = job.get("created_by_user_id")
    if hr_owner_id:
        await NotificationRepository.create({
            "recipient_user_id": hr_owner_id,
            "recipient_type": NotificationActorType.HR_USER.value,
            "sender_id": current_applicant.id,
            "sender_type": NotificationActorType.APPLICANT.value,
            "action_type": NotificationActionType.NEW_CV_RECEIVED.value,
            "title": "Hồ sơ ứng tuyển mới",
            "message": f"Bạn có 1 hồ sơ mới cho vị trí '{job.get('title')}'",
            "type": NotificationType.INFO.value,
            "entity_ref": {"type": "application", "id": str(app_id)},
            "payload": {"job_id": job_id, "applicant_name": cv_snapshot.get("display_name")},
            "action_url": f"/hr/jobs/{job_id}",
            "status": NotificationReadStatus.UNREAD.value,
            "created_at": datetime.now(timezone.utc)
        })

    return {"status": "success", "message": "Nộp hồ sơ thành công bằng CV từ thư viện!"}

@router.get("/library")
async def get_my_cv_library(current_applicant: CurrentUser = Depends(require_applicant)):
    cvs = await CVRepository.find_all(
        {"owner_user_id": current_applicant.id}, 
        projection={"raw_text": 0, "cv_vector_ref": 0},
        limit=10
    )
    return cvs

@router.post("/self-score")
@limiter.limit("20/day")
async def self_score_cv(
    request: Request,
    response: Response,
    payload: SelfScoreRequest,
    current_applicant: CurrentUser = Depends(require_applicant)
):    
    features = await get_applicant_plan_features(current_applicant.id)
    max_scores = features.get("max_self_scores_per_day", 3)
    
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    scores_today = await AuditRepository.count_documents({
        "actor_id": current_applicant.id,
        "action": "APPLICANT_SELF_SCORE",
        "created_at": {"$gte": start_of_day}
    })
    
    if scores_today >= max_scores:
        raise HTTPException(
            status_code=403, 
            detail=f"Bạn đã đạt giới hạn {max_scores} lần chấm điểm thử AI trong ngày. Vui lòng quay lại vào ngày mai hoặc nâng cấp gói cước."
        )

    job = await JobRepository.find_one({"_id": ObjectId(payload.job_id), "status": JobStatus.OPEN.value})
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy vị trí tuyển dụng hoặc đã đóng")
        
    if not payload.cv_document_id:
        cv_doc = await CVRepository.find_one({"owner_user_id": current_applicant.id, "is_primary": True})
        if not cv_doc:
            raise HTTPException(status_code=400, detail="Bạn chưa có CV mặc định. Vui lòng chọn 1 CV cụ thể hoặc tải lên thư viện.")
    else:
        cv_doc = await CVRepository.find_one({"_id": ObjectId(payload.cv_document_id), "owner_user_id": current_applicant.id})
        if not cv_doc:
            raise HTTPException(status_code=404, detail="Không tìm thấy CV trong thư viện cá nhân.")

    cv_data_for_scoring = _prepare_cv_for_scoring(cv_doc, job)
    scoring_result = score_cv(cv_data_for_scoring, job)

    await log_action(
        actor_id=current_applicant.id,
        actor_role=current_applicant.role,
        action="APPLICANT_SELF_SCORE",
        target_type="job",
        target_id=payload.job_id,
        note="Ứng viên dùng tính năng chấm điểm AI thử"
    )

    return {
        "status": "success", 
        "message": "Tính điểm dự kiến thành công",
        "ai_score": scoring_result
    }

@router.delete("/library/{cv_id}")
async def delete_cv_from_library(cv_id: str, current_applicant: CurrentUser = Depends(require_applicant)):
    cv_record = await CVRepository.find_one({"_id": ObjectId(cv_id), "owner_user_id": current_applicant.id})
    if not cv_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy CV")
        
    if cv_record.get("file_url"):
        await delete_file_from_cloudinary(cv_record["file_url"])
        
    await CVRepository.delete(cv_id, scope_filter={"owner_user_id": current_applicant.id})
        
    return {"status": "success", "message": "Đã xóa CV khỏi thư viện cá nhân"}

@router.post("/saved-companies")
async def save_company(
    payload: SavedCompanyCreate,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    is_saved = await SavedCompanyRepository.check_saved(current_applicant.id, payload.company_id)
    if is_saved:
        raise HTTPException(status_code=400, detail="Bạn đã theo dõi công ty này rồi")

    record = {
        "company_id": payload.company_id,
        "applicant_user_id": current_applicant.id,
        "created_at": datetime.now(timezone.utc)
    }
    _id = await SavedCompanyRepository.create(record)
    
    await CompanyRepository.update_custom(
        {"_id": ObjectId(payload.company_id)}, 
        {"$inc": {"follower_count": 1}}
    )
    
    return {"status": "success", "message": "Đã theo dõi công ty", "id": _id}

@router.get("/saved-companies")
async def get_saved_companies(current_applicant: CurrentUser = Depends(require_applicant)):
    records = await SavedCompanyRepository.get_by_applicant_id(current_applicant.id)
    return records

@router.delete("/saved-companies/{company_id}")
async def unsave_company(
    company_id: str,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    deleted = await SavedCompanyRepository.delete_many(
        {"applicant_user_id": current_applicant.id, "company_id": company_id}
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Chưa theo dõi công ty này")
        
    await CompanyRepository.update_custom(
        {"_id": ObjectId(company_id)}, 
        {"$inc": {"follower_count": -deleted}}
    )
    
    return {"status": "success", "message": "Đã hủy theo dõi công ty"}

@router.post("/matching-preferences")
async def setup_matching_preferences(
    payload: MatchingPreferencesCreate,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    await MatchingPreferencesRepository.delete_many({"applicant_user_id": current_applicant.id})
    
    record = payload.model_dump()
    record["applicant_user_id"] = current_applicant.id
    record["is_active"] = True
    record["created_at"] = datetime.now(timezone.utc)
    record["updated_at"] = datetime.now(timezone.utc)
    
    _id = await MatchingPreferencesRepository.create(record)
    return {"status": "success", "message": "Đã lưu tiêu chí AI Matching", "id": _id}

@router.patch("/matching-preferences")
async def update_matching_preferences(
    payload: MatchingPreferencesUpdate,
    current_applicant: CurrentUser = Depends(require_applicant)
):
    existing_record = await MatchingPreferencesRepository.get_by_applicant_id(current_applicant.id)
    if not existing_record:
        raise HTTPException(status_code=404, detail="Chưa có cấu hình AI Matching. Vui lòng thiết lập (POST) trước.")
    
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return {"status": "success", "message": "Không có dữ liệu mới để cập nhật"}
        
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    await MatchingPreferencesRepository.update(
        doc_id=str(existing_record.get("id")),
        update_data=update_data
    )
    
    return {"status": "success", "message": "Đã cập nhật tiêu chí AI Matching"}

@router.get("/matching-preferences")
async def get_matching_preferences(current_applicant: CurrentUser = Depends(require_applicant)):
    record = await MatchingPreferencesRepository.get_by_applicant_id(current_applicant.id)
    if not record:
        return {"status": "success", "data": None}
    return {"status": "success", "data": record}

@router.get("/notifications/unread-count")
async def get_unread_notifications_count(current_applicant: CurrentUser = Depends(require_applicant)):
    count = await NotificationRepository.get_unread_count(current_applicant.id)
    return {"status": "success", "data": {"unread_count": count}}

from app.repositories.cover_letter_repository import CoverLetterRepository

@router.post("/cover-letters/upload")
@limiter.limit("20/day")
async def upload_cover_letter(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    display_name: str = Form("Thư giới thiệu của tôi"),
    current_applicant: CurrentUser = Depends(require_applicant)
):
    # Lấy giới hạn từ gói cước
    features = await get_applicant_plan_features(current_applicant.id)
    max_uploads = features.get("max_cover_letters_uploads", 3)
    
    current_cl_count = await CoverLetterRepository.count_documents({"owner_user_id": current_applicant.id})
    if current_cl_count >= max_uploads:
        raise HTTPException(
            status_code=403, 
            detail=f"Thư viện của bạn đã đạt giới hạn {max_uploads} Thư giới thiệu. Vui lòng xóa bớt hoặc nâng cấp gói cước."
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Dung lượng file vượt quá 5MB.")
        
    file_url = await upload_file_to_cloudinary(content, file.filename)
    
    cl_doc = {
        "display_name": display_name,
        "filename": file.filename,
        "file_url": file_url,
        "owner_user_id": current_applicant.id,
        "created_at": datetime.now(timezone.utc)
    }
    
    cl_id = await CoverLetterRepository.create(cl_doc)
    return {
        "status": "success",
        "cover_letter_id": str(cl_id),
        "file_url": file_url,
        "filename": file.filename
    }

@router.get("/cover-letters")
async def get_my_cover_letters(current_applicant: CurrentUser = Depends(require_applicant)):
    letters = await CoverLetterRepository.find_all(
        {"owner_user_id": current_applicant.id}, 
        limit=10
    )
    return letters

@router.delete("/cover-letters/{cl_id}")
async def delete_cover_letter(cl_id: str, current_applicant: CurrentUser = Depends(require_applicant)):
    cl_record = await CoverLetterRepository.find_one({"_id": ObjectId(cl_id), "owner_user_id": current_applicant.id})
    if not cl_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy Thư giới thiệu")
        
    if cl_record.get("file_url"):
        await delete_file_from_cloudinary(cl_record["file_url"])
        
    await CoverLetterRepository.delete(cl_id, scope_filter={"owner_user_id": current_applicant.id})
    return {"status": "success", "message": "Đã xóa Thư giới thiệu khỏi thư viện cá nhân"}
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Body, Request, Response, BackgroundTasks
from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional

from app.database.config import Collections
from app.schemas.application_schema import ApplicationUpdate
from app.schemas.common_schema import ApplicationStatus, ApplicationSource, NotificationType, NotificationReadStatus, AuditAction, NotificationActorType, NotificationActionType
from app.schemas.user_interaction_schema import TalentPoolCreate
from app.repositories.job_repository import JobRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.cv_repository import CVRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_interactions_repository import TalentPoolRepository
from app.repositories.applicant_profile_repository import ApplicantProfileRepository
from app.repositories.quota_transaction_repository import QuotaTransactionRepository

from app.services.ai_scoring_service import AIScoringService
from app.services.audit_service import log_action
from app.services.vector_engine import compress_jd_data, get_embedding
from app.services.nlp_engine import GLOBAL_SYSTEM_SETTINGS
from app.core.security import require_hr, require_hr_or_admin, get_scope_filter, CurrentUser
from app.middleware.rate_limit import limiter
from app.middleware.subscription import require_tier, require_credits
from app.services.storage_service import upload_file_to_cloudinary, delete_file_from_cloudinary
from app.services.email_service import send_interview_email
from app.services.llm_service import generate_interview_questions

router = APIRouter(prefix="/api/v1/cv", tags=["CV Processing & Talent Pool"])

MAX_FILE_SIZE = 5 * 1024 * 1024

class MapCVRequest(BaseModel):
    job_id: str

class MapBatchCVRequest(BaseModel):
    cv_ids: list[str]
    job_id: str

class SalaryFilter(BaseModel):
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None

class LocationFilter(BaseModel):
    province_code: Optional[str] = None
    district_code: Optional[str] = None

class DiscoveryRequest(BaseModel):
    title: str = Field(..., description="Vị trí cần tìm (VD: Senior Backend Dev)")
    industry: str = Field(default="it")
    required_skills: list[dict] = Field(..., description="Danh sách kỹ năng cần thiết")
    min_yoe: float = Field(default=0.0)
    salary: SalaryFilter = Field(default_factory=SalaryFilter, description="Bộ lọc lương an toàn")
    location: LocationFilter = Field(default_factory=LocationFilter, description="Bộ lọc địa điểm an toàn")
    work_mode: str = Field(default="Office")
    employment_type: str = Field(default="Full-time")
    description: str = Field(..., description="Mô tả công việc (Dùng để so khớp ngữ nghĩa Vector)")

def get_notification_content(status: str, job_title: str):
    status_map = {
        ApplicationStatus.NEW.value: ("Hồ sơ đã được tiếp nhận", f"Hồ sơ của bạn cho vị trí '{job_title}' đã được tiếp nhận và đang chờ xem xét.", NotificationType.INFO.value),
        ApplicationStatus.REVIEWING.value: ("Hồ sơ đang được xem xét", f"Hồ sơ của bạn cho vị trí '{job_title}' đang được HR xem xét kỹ lưỡng.", NotificationType.INFO.value),
        ApplicationStatus.INTERVIEW.value: ("Mời phỏng vấn", f"Chúc mừng! Bạn đã được mời phỏng vấn cho vị trí '{job_title}'. HR sẽ liên hệ với bạn sớm.", NotificationType.SUCCESS.value),
        ApplicationStatus.HIRED.value: ("Chúc mừng - Trúng tuyển!", f"Chúc mừng bạn đã trúng tuyển vị trí '{job_title}'! Chào mừng bạn đến với đội ngũ của chúng tôi.", NotificationType.SUCCESS.value),
        ApplicationStatus.REJECTED.value: ("Thông báo kết quả", f"Cảm ơn bạn đã quan tâm đến vị trí '{job_title}'. Rất tiếc lần này chúng tôi không thể tiếp tục với hồ sơ của bạn.", NotificationType.ERROR.value),
    }
    
    return status_map.get(status, ("Cập nhật trạng thái", f"Trạng thái hồ sơ của bạn cho vị trí '{job_title}' đã được cập nhật thành '{status}'.", NotificationType.INFO.value))


@router.post("/upload")
@limiter.limit("50/hour")
async def upload_cv_to_pool(
    request: Request,
    response: Response,
    file: UploadFile = File(..., description="File CV định dạng PDF hoặc DOCX"),
    current_user: CurrentUser = Depends(require_credits(action_type="HR_PARSE_CV"))
):
    content = await file.read()
    
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Dung lượng file vượt quá 5MB giới hạn")
    
    try:
        raw_text, cv_data, fraud_result, cv_vector = await AIScoringService.process_uploaded_cv(file, content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Hệ thống không thể xử lý file này: {str(e)}")
        
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Không thể trích xuất văn bản.")

    candidate_email = cv_data.get("email")
    
    if candidate_email:
        existing_cv = await CVRepository.find_one({"company_id": current_user.company_id, "candidate_info.email": candidate_email})
        if existing_cv:
            return {
                "message": "CV đã tồn tại trong Kho hồ sơ của công ty",
                "cv_id": str(existing_cv["_id"]),
                "candidate_email": candidate_email,
                "is_existing": True
            }
        
    file_url = await upload_file_to_cloudinary(content, file.filename)
    
    pool_record = {
        "filename": file.filename,
        "file_url": file_url,
        "raw_text": raw_text,
        "cv_vector_ref": cv_vector,
        "candidate_info": {
            "email": cv_data.get("email"),
            "phone": cv_data.get("phone"),
            "github": cv_data.get("github"),
            "linkedin": cv_data.get("linkedin"),
            "portfolio": cv_data.get("portfolio", []),
            "skill_experience": cv_data.get("skill_experience", {}),
            "education_level": cv_data.get("education_level", "Không đề cập"),
            "years_of_experience": cv_data.get("years_of_experience", 0),
            "fraud_analysis": fraud_result
        },
        "extracted_skills": cv_data.get("skills", []),
        "uploaded_by_user_id": current_user.id,
        "company_id": current_user.company_id,
        "created_at": datetime.now(timezone.utc)
    }

    cv_id = await CVRepository.create(pool_record)

    return {
        "message": "Tải CV lên Kho hồ sơ (Talent Pool) thành công",
        "cv_id": str(cv_id),
        "candidate_email": candidate_email,
        "is_existing": False
    }

@router.post("/{cv_id}/map")
async def map_cv_to_job(
    cv_id: str,
    payload: MapCVRequest,
    current_user: CurrentUser = Depends(require_hr),
    scope_filter: dict = Depends(get_scope_filter),
    _ = Depends(require_credits(action_type="HR_MAP_CV_AI_SCORE"))
):
    job_id = payload.job_id
    
    try:
        jd_data = await JobRepository.find_one({"_id": ObjectId(payload.job_id), **scope_filter})
    except:
        raise HTTPException(status_code=400, detail="Mã Job ID không hợp lệ")
        
    if not jd_data:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch tuyển dụng")

    deadline = jd_data.get("deadline")
    if deadline:
        now_utc = datetime.now(timezone.utc)
        if isinstance(deadline, str):
            deadline_dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        else:
            deadline_dt = deadline
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            
        if now_utc > deadline_dt:
            raise HTTPException(
                status_code=400, 
                detail=f"Chiến dịch đã hết hạn vào {deadline_dt.strftime('%d/%m/%Y %H:%M')} (UTC)"
            )
        
    cv_record = await CVRepository.find_one({"_id": ObjectId(cv_id), **scope_filter})
    if not cv_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy CV trong Kho hồ sơ")

    existing_app = await ApplicationRepository.find_one({"job_id": payload.job_id, "cv_snapshot.cv_document_id": cv_id})
    if existing_app:
        raise HTTPException(status_code=400, detail="Hồ sơ này đã được đưa vào chiến dịch này rồi!")

    jd_search_text = jd_data.get("jd_search_text", "")
    
    scoring_result, top_sentences = AIScoringService.prepare_and_score_cv(cv_record, jd_data, jd_search_text)

    cv_snapshot = {
        "cv_document_id": cv_id,
        "display_name": cv_record.get("display_name", cv_record.get("filename")),
        "filename": cv_record.get("filename"),
        "file_url": cv_record.get("file_url", ""),
        "candidate_info": cv_record.get("candidate_info", {}),
        "extracted_skills": cv_record.get("extracted_skills", [])
    }

    application_record = {
        "job_id": job_id,
        "cv_snapshot": cv_snapshot,
        "company_id": current_user.company_id,
        "source": ApplicationSource.HR_SOURCED.value,
        "status": ApplicationStatus.NEW.value,
        "ai_score": scoring_result,
        "applied_at": datetime.now(timezone.utc)
    }

    app_id = await ApplicationRepository.create(application_record)

    return {
        "message": "Ghép nối CV vào chiến dịch và chấm điểm thành công",
        "application_id": str(app_id),
        "ai_score": scoring_result
    }

@router.post("/map-batch")
async def map_multiple_cvs_to_job(
    payload: MapBatchCVRequest,
    current_user: CurrentUser = Depends(require_hr),
    scope_filter: dict = Depends(get_scope_filter)
):
    job_id = payload.job_id
    cv_ids = payload.cv_ids

    if not cv_ids:
         raise HTTPException(status_code=400, detail="Danh sách CV không được để trống")

    if len(cv_ids) > 50:
         raise HTTPException(status_code=400, detail="Chỉ được phép xử lý tối đa 50 CV trong một lần để đảm bảo hiệu suất.")
         
    unit_cost = GLOBAL_SYSTEM_SETTINGS.get("action_costs", {}).get("HR_MAP_BATCH_CV_AI_SCORE")
    if unit_cost is None:
        raise HTTPException(status_code=503, detail="Hệ thống chưa cấu hình giá cho tính năng chấm điểm hàng loạt.")
        
    cost = len(cv_ids) * unit_cost
    success = await CompanyRepository.deduct_ai_credits(current_user.company_id, cost)
    if not success:
        raise HTTPException(
            status_code=402, 
            detail=f"Tài khoản không đủ Credit AI. Cần {cost} credits để chấm điểm {len(cv_ids)} CV."
        )
        
    company = await CompanyRepository.get_by_id(current_user.company_id)
    await QuotaTransactionRepository.create({
        "company_id": current_user.company_id,
        "user_id": current_user.id,
        "action_type": "HR_MAP_BATCH_CV_AI_SCORE",
        "credit_cost": cost,
        "balance_after": company.get("credits_remaining", 0),
        "created_at": datetime.now(timezone.utc)
    })

    try:
        jd_data = await JobRepository.find_one({"_id": ObjectId(job_id), **scope_filter})
    except:
        raise HTTPException(status_code=400, detail="Mã Job ID không hợp lệ")
        
    if not jd_data:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch tuyển dụng")

    deadline = jd_data.get("deadline")
    if deadline:
        now_utc = datetime.now(timezone.utc)
        deadline_dt = datetime.fromisoformat(deadline.replace("Z", "+00:00")) if isinstance(deadline, str) else deadline
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            
        if now_utc > deadline_dt:
            raise HTTPException(
                status_code=400, 
                detail=f"Chiến dịch đã hết hạn vào {deadline_dt.strftime('%d/%m/%Y %H:%M')} (UTC)"
            )

    successful_maps = 0
    errors = []

    jd_search_text = jd_data.get("jd_search_text", "")

    for cv_id in cv_ids:
        try:
            cv_record = await CVRepository.find_one({"_id": ObjectId(cv_id), **scope_filter})
            if not cv_record:
                errors.append(f"Không tìm thấy CV ID: {cv_id}")
                continue

            existing_app = await ApplicationRepository.find_one({"job_id": job_id, "cv_snapshot.cv_document_id": cv_id})
            if existing_app:
                errors.append(f"CV {cv_record.get('filename')} đã tồn tại trong chiến dịch này")
                continue

            jd_search_text = jd_data.get("jd_search_text", "")
            
            scoring_result, top_sentences = AIScoringService.prepare_and_score_cv(cv_record, jd_data, jd_search_text)

            cv_snapshot = {
                "cv_document_id": cv_id,
                "display_name": cv_record.get("display_name", cv_record.get("filename")),
                "filename": cv_record.get("filename"),
                "file_url": cv_record.get("file_url", ""),
                "candidate_info": cv_record.get("candidate_info", {}),
                "extracted_skills": cv_record.get("extracted_skills", [])
            }

            application_record = {
                "job_id": job_id,
                "cv_snapshot": cv_snapshot,
                "company_id": current_user.company_id,
                "source": ApplicationSource.HR_SOURCED.value,
                "status": ApplicationStatus.NEW.value,
                "ai_score": scoring_result,
                "applied_at": datetime.now(timezone.utc)
            }

            await ApplicationRepository.create(application_record)
            successful_maps += 1

        except Exception as e:
            errors.append(f"Lỗi khi xử lý CV ID {cv_id}: {str(e)}")

    return {
        "message": f"Đã ghép nối thành công {successful_maps}/{len(cv_ids)} CV.",
        "successful_maps": successful_maps,
        "errors": errors
    }

@router.patch("/applications/{app_id}")
async def update_application_status(
    app_id: str, 
    background_tasks: BackgroundTasks,
    update_data: ApplicationUpdate = Body(...),
    current_user: CurrentUser = Depends(require_hr_or_admin),
    scope_filter: dict = Depends(get_scope_filter)
):
    try:
        filter_query = {"_id": ObjectId(app_id), **scope_filter}
        current_app = await ApplicationRepository.find_one(filter_query)
        if not current_app:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển này")

        update_query = {"$set": {}, "$push": {}}

        if update_data.status is not None and update_data.status.value != current_app.get("status"):
            update_query["$set"]["status"] = update_data.status.value

            update_query["$push"]["status_history"] = {
                "from_status": current_app.get("status"),
                "to_status": update_data.status.value,
                "changed_by_user_id": current_user.id,
                "changed_at": datetime.now(timezone.utc)
            }

            if update_data.status.value == ApplicationStatus.INTERVIEW.value and update_data.interview_schedule:
                schedule_dict = update_data.interview_schedule.model_dump()
                schedule_dict["created_at"] = datetime.now(timezone.utc)
                update_query["$push"]["interview_schedules"] = schedule_dict

        if getattr(update_data, "note_to_add", None): 
            update_query["$push"]["notes"] = update_data.note_to_add

        if not update_query["$set"]: del update_query["$set"]
        if not update_query["$push"]: del update_query["$push"]

        if not update_query:
            return {"message": "Không có dữ liệu mới nào để cập nhật"}

        update_query["$set"]["updated_at"] = datetime.now(timezone.utc)
        await ApplicationRepository.update_by_query(filter_query, update_query)
        
        if update_data.status is not None and update_data.status.value != current_app.get("status"):
            applicant_user_id = current_app.get("applicant_user_id")
            job = await JobRepository.get_by_id(current_app["job_id"])
            
            if update_data.status.value == ApplicationStatus.INTERVIEW.value and update_data.send_email and update_data.interview_schedule:
                candidate_email = current_app.get("cv_snapshot", {}).get("candidate_info", {}).get("email")
                candidate_name = current_app.get("cv_snapshot", {}).get("display_name", current_app.get("cv_snapshot", {}).get("filename", "Ứng viên"))
                
                if candidate_email:
                    company = await CompanyRepository.get_by_id(current_app["company_id"])
                    company_name = company.get("name", "Công ty của chúng tôi") if company else "Công ty của chúng tôi"
                    job_title = job.get("title", "Vị trí tuyển dụng") if job else "Vị trí tuyển dụng"
                    
                    send_interview_email(
                        background_tasks=background_tasks,
                        to=candidate_email,
                        name=candidate_name,
                        job_title=job_title,
                        company_name=company_name,
                        interview_time=update_data.interview_schedule.interview_time,
                        location=update_data.interview_schedule.location,
                        meeting_link=update_data.interview_schedule.meeting_link,
                        custom_message=update_data.interview_schedule.message
                    )

            if applicant_user_id:               
                title, message, notif_type = get_notification_content(
                    update_data.status.value, 
                    job.get("title", "Vị trí tuyển dụng") if job else "Vị trí tuyển dụng"
                )
                
                notification = {
                    "recipient_user_id": applicant_user_id,
                    "recipient_type": NotificationActorType.APPLICANT.value,
                    "sender_id": current_user.id,
                    "sender_type": NotificationActorType.HR_USER.value,
                    "action_type": NotificationActionType.APPLICATION_UPDATED.value,
                    "title": title,
                    "message": message,
                    "type": notif_type,
                    "entity_ref": {"type": "application", "id": str(current_app["_id"])},
                    "payload": {
                        "job_title": job.get("title", "Vị trí tuyển dụng") if job else "Vị trí tuyển dụng",
                        "status": update_data.status.value
                    },
                    "action_url": "/applicant/my-applications",
                    "status": NotificationReadStatus.UNREAD.value,
                    "created_at": datetime.now(timezone.utc)
                }

                await NotificationRepository.create(notification)

        await log_action(
            actor_id=current_user.id,
            actor_role=current_user.role,
            action=AuditAction.APPLICATION_STATUS_CHANGED,
            target_type="application",
            target_id=app_id,
            note=f"Đổi trạng thái ứng viên: {current_app.get('status')} -> {update_data.status.value if update_data.status else 'Giữ nguyên'}",
            before_state={"status": current_app.get("status")},
            after_state={"status": update_data.status.value if update_data.status else current_app.get("status")}
        )

        return {"status": "success", "message": "Đã cập nhật trạng thái ứng viên thành công"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{cv_id}", dependencies=[Depends(require_hr_or_admin)])
async def delete_cv_from_pool(cv_id: str, scope_filter: dict = Depends(get_scope_filter)):
    try:
        cv_record = await CVRepository.find_one({"_id": ObjectId(cv_id), **scope_filter})
        
        if not cv_record:
            raise HTTPException(status_code=404, detail="Không tìm thấy CV trong kho hoặc từ chối quyền truy cập")
            
        if cv_record.get("file_url"):
            await delete_file_from_cloudinary(cv_record["file_url"])

        await CVRepository.delete(cv_id, scope_filter)
        await ApplicationRepository.delete_many({"cv_snapshot.cv_document_id": cv_id})
            
        return {"status": "success", "message": "Đã xóa vĩnh viễn CV khỏi hệ thống"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pool", dependencies=[Depends(require_hr_or_admin)])
async def get_talent_pool(scope_filter: dict = Depends(get_scope_filter)):
    try:
        cvs = await CVRepository.find_all(scope_filter, projection={"raw_text": 0, "cv_vector_ref": 0}, limit=500)
        
        for cv in cvs:
            cv["id"] = str(cv["_id"])
            del cv["_id"]
                
        return cvs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/applications/{app_id}", dependencies=[Depends(require_hr_or_admin)])
async def remove_application_from_job(app_id: str, scope_filter: dict = Depends(get_scope_filter)):
    try:
        deleted_count = await ApplicationRepository.delete(app_id, scope_filter)
        if deleted_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển này")
            
        return {"status": "success", "message": "Đã gỡ CV khỏi chiến dịch thành công"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/applications/recent", dependencies=[Depends(require_hr_or_admin)])
async def get_recent_applications(scope_filter: dict = Depends(get_scope_filter)):
    try:
        pipeline = []
        if scope_filter:
            pipeline.append({"$match": scope_filter})
            
        pipeline.extend([
            {"$sort": {"applied_at": -1}},
            {"$limit": 100},
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
            {"$unwind": {"path": "$job_info", "preserveNullAndEmptyArrays": True}}
        ])
        
        applications = await ApplicationRepository.aggregate_applications(pipeline)
        
        result = []
        for app in applications:
            app["id"] = str(app["_id"])
            del app["_id"]
            
            cv_snap = app.get("cv_snapshot", {})
            app["filename"] = cv_snap.get("filename", "CV Ẩn")
            app["candidate_email"] = cv_snap.get("candidate_info", {}).get("email", "")
            app["file_url"] = cv_snap.get("file_url", "")
            
            job_info = app.get("job_info", {})
            app["job_title"] = job_info.get("title", "Chiến dịch đã xóa")
            
            app.pop("job_info", None)
            app.pop("cv_snapshot", None)
                
            result.append(app)
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ViewToggleRequest(BaseModel):
    is_viewed: bool

@router.patch("/applications/{app_id}/view", dependencies=[Depends(require_hr_or_admin)])
async def toggle_application_viewed(
    app_id: str, 
    payload: ViewToggleRequest = Body(...),
    scope_filter: dict = Depends(get_scope_filter)
):
    set_data = {"is_viewed": payload.is_viewed, "updated_at": datetime.now(timezone.utc)}
    if payload.is_viewed:
        set_data["viewed_at"] = datetime.now(timezone.utc)

    modified = await ApplicationRepository.update_by_query(
        {"_id": ObjectId(app_id), **scope_filter},
        {"$set": set_data}
    )
    if modified == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển")
    return {"status": "success", "is_viewed": payload.is_viewed}

@router.get("/applications/{app_id}/ai-interview", dependencies=[Depends(require_hr_or_admin)])
async def get_ai_interview_questions(
    app_id: str, 
    scope_filter: dict = Depends(get_scope_filter),
    _ = Depends(require_credits(action_type="AI_INTERVIEW_GEN"))
):
    filter_query = {"_id": ObjectId(app_id), **scope_filter}
    app_record = await ApplicationRepository.find_one(filter_query)
    if not app_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển này")

    existing_questions = app_record.get("ai_interview_questions")
    if existing_questions:
        return {"status": "success", "data": existing_questions}

    cv_id = app_record.get("cv_snapshot", {}).get("cv_document_id")
    job_id = app_record.get("job_id")

    cv_record = await CVRepository.get_by_id(cv_id)
    job_record = await JobRepository.get_by_id(job_id)

    if not cv_record or not job_record:
        raise HTTPException(status_code=400, detail="Dữ liệu CV hoặc JD không tồn tại để sinh câu hỏi")

    cv_text = cv_record.get("raw_text", "")
    jd_text = job_record.get("jd_search_text", "")

    questions = await generate_interview_questions(cv_text, jd_text)

    if not questions:
        raise HTTPException(status_code=500, detail="AI đang bận, không thể sinh câu hỏi lúc này")

    await ApplicationRepository.update_by_query(filter_query, {"$set": {"ai_interview_questions": questions, "updated_at": datetime.now(timezone.utc)}})

    return {"status": "success", "data": questions}

@router.post("/talent-pool/bookmark")
async def bookmark_candidate_to_pool(
    payload: TalentPoolCreate,
    current_user: CurrentUser = Depends(require_hr)
):
    existing = await TalentPoolRepository.find_one({
        "applicant_user_id": payload.applicant_user_id,
        "company_id": current_user.company_id
    })
    if existing:
        raise HTTPException(status_code=400, detail="Ứng viên này đã có trong Talent Pool của công ty")

    record = payload.model_dump()
    record.update({
        "hr_user_id": current_user.id,
        "company_id": current_user.company_id,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })
    
    _id = await TalentPoolRepository.create(record)
    return {"status": "success", "message": "Đã lưu ứng viên vào Talent Pool", "id": _id}

@router.get("/talent-pool/bookmarked", dependencies=[Depends(require_hr)])
async def get_bookmarked_candidates(current_user: CurrentUser = Depends(require_hr)):
    records = await TalentPoolRepository.get_by_company_id(current_user.company_id)
    for r in records:
        r["id"] = str(r["_id"])
        del r["_id"]
    return records

@router.post("/talent-pool/discover", dependencies=[Depends(require_hr)])
@limiter.limit("20/day")
async def discover_talents(
    request: Request,
    response: Response,
    payload: DiscoveryRequest,
    current_user: CurrentUser = Depends(require_tier("can_use_reverse_matching")),
    _ = Depends(require_credits(action_type="REVERSE_MATCHING"))
):
    job_data = payload.model_dump(exclude_none=True, exclude_unset=True)
    
    compressed_jd = compress_jd_data(job_data)
    jd_vector = await get_embedding(compressed_jd)
    
    jd_search_text = f"{payload.title} {payload.description}".lower()
    
    job_data.update({
        "jd_search_text": jd_search_text,
        "jd_vector_ref": jd_vector
    })

    candidates = await ApplicantProfileRepository.find_candidates_for_job(job_data, limit=50)
    
    if not candidates:
        return {"status": "success", "message": "Không có ứng viên nào phù hợp với mức lương/địa điểm này.", "leaderboard": []}

    leaderboard = []
    
    for candidate in candidates:
        cv_data_raw = candidate.get("cv_data")
        if not cv_data_raw:
            continue
            
        cv_id = str(cv_data_raw.get("_id"))
            
        cv_record_for_scoring = {
            "raw_text": cv_data_raw.get("raw_text", ""),
            "cv_vector_ref": cv_data_raw.get("cv_vector_ref", []),
            "candidate_info": cv_data_raw.get("candidate_info", {}),
            "extracted_skills": cv_data_raw.get("extracted_skills", []),
        }
        
        scoring_result, _ = AIScoringService.prepare_and_score_cv(
            cv_record=cv_record_for_scoring, 
            jd_data=job_data, 
            jd_search_text=jd_search_text
        )
        
        if scoring_result.get("total_score", 0) >= 50:
            candidate_info = cv_data_raw.get("candidate_info", {})
            
            leaderboard.append({
                "applicant_user_id": str(candidate["user_id"]),
                "cv_document_id": cv_id,
                "headline": candidate.get("headline", "Ứng viên Tiềm năng"),
                "expected_salary": f"{candidate.get('expected_salary_min')} - {candidate.get('expected_salary_max')}",
                "total_score": scoring_result.get("total_score"),
                "match_tier": scoring_result.get("match_tier"),
                "badges": scoring_result.get("badges", []),
                "skills_score": scoring_result.get("score_breakdown", {}).get("skills_score"),
                "matched_skills": scoring_result.get("matched_skills", [])
            })

    leaderboard.sort(key=lambda x: x["total_score"], reverse=True)

    return {
        "status": "success", 
        "total_scanned": len(candidates),
        "total_matched": len(leaderboard),
        "leaderboard": leaderboard
    }
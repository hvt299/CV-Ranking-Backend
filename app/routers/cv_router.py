from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Body, Request, Response, BackgroundTasks
from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel

from app.database.config import get_db, Collections
from app.database.models import ApplicationUpdate, ApplicationStatus, ApplicationSource, NotificationType, NotificationReadStatus
from app.services.nlp_engine import extract_text, analyze_cv_text, score_cv
from app.services.vector_engine import compress_cv_data, get_embedding, get_top_contributing_sentences
from app.services.document_forensics import detect_hidden_text
from app.auth import require_hr, require_hr_or_admin, get_scope_filter, CurrentUser
from app.middleware.rate_limit import limiter
from app.services.storage_service import upload_file_to_cloudinary, delete_file_from_cloudinary
from app.services.email_service import send_interview_email

router = APIRouter(prefix="/api/v1/cv", tags=["CV Processing & Talent Pool"])

MAX_FILE_SIZE = 5 * 1024 * 1024

class MapCVRequest(BaseModel):
    job_id: str

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
    current_user: CurrentUser = Depends(require_hr)
):
    db = get_db()
    content = await file.read()
    
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Dung lượng file vượt quá 5MB giới hạn")
    
    try:
        raw_text = await extract_text(file, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Hệ thống không thể đọc được file này: {str(e)}")
        
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Không thể trích xuất văn bản.")

    fraud_result = None
    if file.filename.lower().endswith((".pdf", ".docx")):
        fraud_result = detect_hidden_text(content, file.filename)

    cv_data = analyze_cv_text(raw_text)
    candidate_email = cv_data.get("email")
    
    if candidate_email:
        existing_cv = await db[Collections.CVS].find_one({
            "company_id": current_user.company_id, 
            "candidate_info.email": candidate_email
        })
        if existing_cv:
            return {
                "message": "CV đã tồn tại trong Kho hồ sơ của công ty",
                "cv_id": str(existing_cv["_id"]),
                "candidate_email": candidate_email,
                "is_existing": True
            }
        
    file_url = await upload_file_to_cloudinary(content, file.filename)
        
    compressed_text = compress_cv_data(raw_text, cv_data, cv_data.get("skills", []))
    cv_vector = await get_embedding(compressed_text)
    
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

    result = await db[Collections.CVS].insert_one(pool_record)

    return {
        "message": "Tải CV lên Kho hồ sơ (Talent Pool) thành công",
        "cv_id": str(result.inserted_id),
        "candidate_email": candidate_email,
        "is_existing": False
    }

@router.post("/{cv_id}/map")
async def map_cv_to_job(
    cv_id: str,
    payload: MapCVRequest,
    current_user: CurrentUser = Depends(require_hr),
    scope_filter: dict = Depends(get_scope_filter)
):
    db = get_db()
    job_id = payload.job_id
    
    try:
        job_filter = {"_id": ObjectId(job_id), **scope_filter}
        jd_data = await db[Collections.JOBS].find_one(job_filter)
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
        
    cv_filter = {"_id": ObjectId(cv_id), **scope_filter}
    cv_record = await db[Collections.CVS].find_one(cv_filter)
    if not cv_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy CV trong Kho hồ sơ")

    existing_app = await db[Collections.APPLICATIONS].find_one({
        "job_id": job_id,
        "cv_snapshot.cv_document_id": cv_id
    })
    if existing_app:
        raise HTTPException(status_code=400, detail="Hồ sơ này đã được đưa vào chiến dịch này rồi!")

    jd_search_text = jd_data.get("jd_search_text", "")
    raw_text = cv_record.get("raw_text", "")

    top_sentences = get_top_contributing_sentences(raw_text, jd_search_text)

    cv_data_for_scoring = {
        "raw_text": cv_record.get("raw_text", ""),
        "word_count": len((cv_record.get("raw_text", "") or "").split()),
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

    scoring_result = score_cv(cv_data_for_scoring, jd_data)

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

    result = await db[Collections.APPLICATIONS].insert_one(application_record)

    return {
        "message": "Ghép nối CV vào chiến dịch và chấm điểm thành công",
        "application_id": str(result.inserted_id),
        "ai_score": scoring_result
    }

@router.patch("/applications/{app_id}", dependencies=[Depends(require_hr_or_admin)])
async def update_application_status(
    app_id: str, 
    background_tasks: BackgroundTasks,
    update_data: ApplicationUpdate = Body(...),
    scope_filter: dict = Depends(get_scope_filter)
):
    db = get_db()
    
    try:
        filter_query = {"_id": ObjectId(app_id), **scope_filter}
        current_app = await db[Collections.APPLICATIONS].find_one(filter_query)
        if not current_app:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển này")
            
        update_query = {"$set": {}}
        
        if update_data.status is not None:
            update_query["$set"]["status"] = update_data.status.value
            
        if getattr(update_data, "note_to_add", None): 
            update_query["$push"] = {"notes": update_data.note_to_add}
            
        if not update_query.get("$set") and not update_query.get("$push"):
            return {"message": "Không có dữ liệu mới nào để cập nhật"}

        update_query["$set"]["updated_at"] = datetime.now(timezone.utc)
        result = await db[Collections.APPLICATIONS].update_one(filter_query, update_query) 
        
        if update_data.status is not None and update_data.status.value != current_app.get("status"):
            applicant_user_id = current_app.get("applicant_user_id")
            job = await db[Collections.JOBS].find_one({"_id": ObjectId(current_app["job_id"])})
            
            if update_data.status.value == ApplicationStatus.INTERVIEW.value and update_data.send_email and update_data.interview_schedule:
                candidate_email = current_app.get("cv_snapshot", {}).get("candidate_info", {}).get("email")
                candidate_name = current_app.get("cv_snapshot", {}).get("display_name", current_app.get("cv_snapshot", {}).get("filename", "Ứng viên"))
                
                if candidate_email:
                    company = await db[Collections.COMPANIES].find_one({"_id": ObjectId(current_app["company_id"])})
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
                    "application_id": str(current_app["_id"]),
                    "title": title,
                    "message": message,
                    "type": notif_type,
                    "status": NotificationReadStatus.UNREAD.value,
                    "job_title_snapshot": job.get("title") if job else None,
                    "application_status_snapshot": update_data.status.value,
                    "created_at": datetime.now(timezone.utc)
                }
                
                await db[Collections.NOTIFICATIONS].insert_one(notification)

        return {"status": "success", "message": "Đã cập nhật trạng thái ứng viên thành công"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{cv_id}", dependencies=[Depends(require_hr_or_admin)])
async def delete_cv_from_pool(cv_id: str, scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
    try:
        filter_query = {"_id": ObjectId(cv_id), **scope_filter}
        cv_record = await db[Collections.CVS].find_one(filter_query)
        
        if not cv_record:
            raise HTTPException(status_code=404, detail="Không tìm thấy CV trong kho hoặc từ chối quyền truy cập")
            
        if cv_record.get("file_url"):
            await delete_file_from_cloudinary(cv_record["file_url"])

        await db[Collections.CVS].delete_one(filter_query)
        
        await db[Collections.APPLICATIONS].delete_many({"cv_snapshot.cv_document_id": cv_id})
            
        return {"status": "success", "message": "Đã xóa vĩnh viễn CV khỏi hệ thống"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pool", dependencies=[Depends(require_hr_or_admin)])
async def get_talent_pool(scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
    try:
        projection = {"raw_text": 0, "cv_vector_ref": 0}
        cursor = db[Collections.CVS].find(scope_filter, projection).sort("created_at", -1)
        cvs = await cursor.to_list(length=500)
        
        for cv in cvs:
            cv["id"] = str(cv["_id"])
            del cv["_id"]
                
        return cvs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/applications/{app_id}", dependencies=[Depends(require_hr_or_admin)])
async def remove_application_from_job(app_id: str, scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
    try:
        filter_query = {"_id": ObjectId(app_id), **scope_filter}
        result = await db[Collections.APPLICATIONS].delete_one(filter_query)
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển này")
            
        return {"status": "success", "message": "Đã gỡ CV khỏi chiến dịch thành công"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/applications/recent", dependencies=[Depends(require_hr_or_admin)])
async def get_recent_applications(scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
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
        
        applications = await db[Collections.APPLICATIONS].aggregate(pipeline).to_list(length=100)
        
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

@router.patch("/applications/{app_id}/view", dependencies=[Depends(require_hr_or_admin)])
async def mark_application_viewed(app_id: str, scope_filter: dict = Depends(get_scope_filter)):
    db = get_db()
    result = await db[Collections.APPLICATIONS].update_one(
        {"_id": ObjectId(app_id), **scope_filter},
        {"$set": {"is_viewed": True, "updated_at": datetime.now(timezone.utc)}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển")
    return {"status": "success"}
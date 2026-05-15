from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form, Body
from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel

from app.database.config import get_db
from app.database.models import CVUpdate

from app.services.nlp_engine import extract_text, analyze_cv_text, score_cv
from app.services.vector_engine import compress_cv_data, get_embedding
from app.auth import get_current_user, get_current_user_with_role

router = APIRouter(prefix="/api/v1/cv", tags=["CV Processing & Talent Pool"])
MAX_FILE_SIZE = 5 * 1024 * 1024

class MapCVRequest(BaseModel):
    job_id: str

@router.post("/upload")
async def upload_cv_to_pool(
    file: UploadFile = File(..., description="File CV định dạng PDF hoặc DOCX"),
    current_hr: str = Depends(get_current_user)
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

    cv_data = analyze_cv_text(raw_text)
    candidate_email = cv_data.get("email")
    
    if candidate_email:
        existing_cv = await db["hr_cvs"].find_one({
            "hr_email": current_hr, 
            "candidate_info.email": candidate_email
        })
        if existing_cv:
            return {
                "message": "CV đã tồn tại trong Kho hồ sơ",
                "cv_id": str(existing_cv["_id"]),
                "candidate_email": candidate_email,
                "is_existing": True
            }
        
    compressed_text = compress_cv_data(raw_text, cv_data, cv_data.get("skills", []))
    cv_vector = get_embedding(compressed_text)
    
    pool_record = {
        "hr_email": current_hr,
        "filename": file.filename,
        "raw_text": raw_text,
        "cv_vector": cv_vector,
        "candidate_info": {
            "email": cv_data.get("email"),
            "phone": cv_data.get("phone"),
            "github": cv_data.get("github"),
            "linkedin": cv_data.get("linkedin"),
            "portfolio": cv_data.get("portfolio", []),
            "skill_experience": cv_data.get("skill_experience", {}),
            "education_level": cv_data.get("education_level"),
            "years_of_experience": cv_data.get("years_of_experience", 0)
        },
        "extracted_skills": cv_data.get("skills", []),
        "created_at": datetime.now(timezone.utc)
    }

    result = await db["hr_cvs"].insert_one(pool_record)

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
    current_hr: str = Depends(get_current_user)
):
    db = get_db()
    job_id = payload.job_id
    
    try:
        jd_data = await db["hr_jobs"].find_one({"_id": ObjectId(job_id), "created_by": current_hr})
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
        
    cv_record = await db["hr_cvs"].find_one({"_id": ObjectId(cv_id), "hr_email": current_hr})
    if not cv_record:
        raise HTTPException(status_code=404, detail="Không tìm thấy CV trong Kho hồ sơ")

    existing_app = await db["hr_applications"].find_one({
        "cv_id": cv_id,
        "job_id": job_id
    })
    if existing_app:
        raise HTTPException(status_code=400, detail="Hồ sơ này đã được đưa vào chiến dịch này rồi!")

    cv_data_for_scoring = {
        "skills": cv_record.get("extracted_skills", []),
        "years_of_experience": cv_record["candidate_info"].get("years_of_experience", 0),
        "skill_experience": cv_record["candidate_info"].get("skill_experience", {}),
        "education_level": cv_record["candidate_info"].get("education_level", "Không đề cập"),
        "cv_vector": cv_record.get("cv_vector", []),
        "word_count": len((cv_record.get("raw_text", "") or "").split()),
        "raw_text": cv_record.get("raw_text", "")
    }

    scoring_result = score_cv(cv_data_for_scoring, jd_data)

    application_record = {
        "hr_email": current_hr,
        "job_id": job_id,
        "cv_id": cv_id,
        "ai_score": scoring_result,
        "status": "Mới",
        "note": "",
        "applied_at": datetime.now(timezone.utc)
    }

    result = await db["hr_applications"].insert_one(application_record)

    return {
        "message": "Ghép nối CV vào chiến dịch và chấm điểm thành công",
        "application_id": str(result.inserted_id),
        "ai_score": scoring_result
    }

@router.patch("/applications/{app_id}")
async def update_application_status(
    app_id: str, 
    update_data: CVUpdate = Body(...),
    user_info: dict = Depends(get_current_user_with_role)
):
    db = get_db()
    current_hr = user_info["email"]
    user_role = user_info["role"]
    
    try:
        # Admin có thể update bất kỳ application nào, HR thường chỉ update applications của mình
        if user_role == "admin":
            filter_query = {"_id": ObjectId(app_id)}
        else:
            filter_query = {"_id": ObjectId(app_id), "hr_email": current_hr}
        
        # Get current application data before update
        current_app = await db["hr_applications"].find_one(filter_query)
        if not current_app:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển này")
            
        update_query = {"$set": {}}
        
        if update_data.status is not None:
            update_query["$set"]["status"] = update_data.status
            
        if update_data.note is not None:
            update_query["$set"]["note"] = update_data.note
            
        if not update_query["$set"]:
            return {"message": "Không có dữ liệu mới nào để cập nhật"}

        result = await db["hr_applications"].update_one(filter_query, update_query) 
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển này")

        # Create notification for applicant if status changed
        if update_data.status is not None and update_data.status != current_app.get("status"):
            # Get job and applicant info
            job = await db["hr_jobs"].find_one({"_id": ObjectId(current_app["job_id"])})
            cv = await db["hr_cvs"].find_one({"_id": ObjectId(current_app["cv_id"])})
            
            # Check if this is from applicant submission
            applicant_submission = await db["applicant_submissions"].find_one({
                "job_id": current_app["job_id"],
                "applicant_email": {"$exists": True}
            })
            
            if applicant_submission and job:
                # Create notification for applicant
                notification_title, notification_message, notification_type = get_notification_content(
                    update_data.status, job.get("title", "Vị trí tuyển dụng")
                )
                
                notification = {
                    "applicant_email": applicant_submission["applicant_email"],
                    "title": notification_title,
                    "message": notification_message,
                    "type": notification_type,
                    "status": "unread",
                    "job_title": job.get("title"),
                    "application_id": str(current_app["_id"]),
                    "application_status": update_data.status,
                    "created_at": datetime.now(timezone.utc)
                }
                
                await db["applicant_notifications"].insert_one(notification)
                
                # Also update the applicant_submissions status
                await db["applicant_submissions"].update_one(
                    {
                        "job_id": current_app["job_id"],
                        "applicant_email": applicant_submission["applicant_email"]
                    },
                    {"$set": {"status": update_data.status}}
                )

        return {"status": "success", "message": "Đã cập nhật trạng thái ứng viên thành công"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_notification_content(status: str, job_title: str):
    """Generate notification content based on application status"""
    status_map = {
        "Mới": ("Hồ sơ đã được tiếp nhận", f"Hồ sơ của bạn cho vị trí '{job_title}' đã được tiếp nhận và đang chờ xem xét.", "info"),
        "Đang xem xét": ("Hồ sơ đang được xem xét", f"Hồ sơ của bạn cho vị trí '{job_title}' đang được HR xem xét kỹ lưỡng.", "info"),
        "Phỏng vấn": ("Mời phỏng vấn", f"Chúc mừng! Bạn đã được mời phỏng vấn cho vị trí '{job_title}'. HR sẽ liên hệ với bạn sớm.", "success"),
        "Đề nghị (Offer)": ("Đề nghị làm việc", f"Tuyệt vời! Bạn đã nhận được đề nghị làm việc cho vị trí '{job_title}'. Hãy kiểm tra email để biết thêm chi tiết.", "success"),
        "Trúng tuyển": ("Chúc mừng - Trúng tuyển!", f"Chúc mừng bạn đã trúng tuyển vị trí '{job_title}'! Chào mừng bạn đến với đội ngũ của chúng tôi.", "success"),
        "Từ chối": ("Thông báo kết quả", f"Cảm ơn bạn đã quan tâm đến vị trí '{job_title}'. Rất tiếc lần này chúng tôi không thể tiếp tục với hồ sơ của bạn.", "error"),
    }
    
    return status_map.get(status, ("Cập nhật trạng thái", f"Trạng thái hồ sơ của bạn cho vị trí '{job_title}' đã được cập nhật thành '{status}'.", "info"))

@router.delete("/{cv_id}")
async def delete_cv_from_pool(
    cv_id: str, 
    user_info: dict = Depends(get_current_user_with_role)
):
    db = get_db()
    current_hr = user_info["email"]
    user_role = user_info["role"]
    
    try:
        # Admin có thể xóa bất kỳ CV nào, HR thường chỉ xóa CV của mình
        if user_role == "admin":
            result = await db["hr_cvs"].delete_one({"_id": ObjectId(cv_id)})
        else:
            result = await db["hr_cvs"].delete_one({"_id": ObjectId(cv_id), "hr_email": current_hr})
            
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy CV trong kho")
        
        await db["hr_applications"].delete_many({"cv_id": cv_id})
            
        return {"status": "success", "message": "Đã xóa vĩnh viễn CV khỏi hệ thống"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pool")
async def get_talent_pool(user_info: dict = Depends(get_current_user_with_role)):
    db = get_db()
    current_hr = user_info["email"]
    user_role = user_info["role"]
    
    try:
        # Admin thấy tất cả CVs, HR thường chỉ thấy CVs của mình
        if user_role == "admin":
            cursor = db["hr_cvs"].find({}).sort("created_at", -1)
            print(f"DEBUG: Admin viewing all CVs")
        else:
            cursor = db["hr_cvs"].find({"hr_email": current_hr}).sort("created_at", -1)
            print(f"DEBUG: HR {current_hr} viewing own CVs")
            
        cvs = await cursor.to_list(length=500)
        
        for cv in cvs:
            cv["id"] = str(cv["_id"])
            del cv["_id"]
            if "raw_text" in cv:
                del cv["raw_text"]
                
        return cvs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/applications/{app_id}")
async def remove_application_from_job(
    app_id: str, 
    user_info: dict = Depends(get_current_user_with_role)
):
    db = get_db()
    current_hr = user_info["email"]
    user_role = user_info["role"]
    
    try:
        # Admin có thể xóa bất kỳ application nào, HR thường chỉ xóa applications của mình
        if user_role == "admin":
            result = await db["hr_applications"].delete_one({"_id": ObjectId(app_id)})
        else:
            result = await db["hr_applications"].delete_one({
                "_id": ObjectId(app_id), 
                "hr_email": current_hr
            })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng tuyển này")
            
        return {"status": "success", "message": "Đã gỡ CV khỏi chiến dịch thành công"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/applications/recent")
async def get_recent_applications(user_info: dict = Depends(get_current_user_with_role)):
    db = get_db()
    current_hr = user_info["email"]
    user_role = user_info["role"]
    
    try:
        # Admin thấy tất cả applications, HR thường chỉ thấy applications của mình
        if user_role == "admin":
            cursor = db["hr_applications"].find({}).sort("applied_at", -1).limit(100)
            print(f"DEBUG: Admin viewing all applications")
        else:
            cursor = db["hr_applications"].find({"hr_email": current_hr}).sort("applied_at", -1).limit(100)
            print(f"DEBUG: HR {current_hr} viewing own applications")
            
        applications = await cursor.to_list(length=100)
        
        result = []
        for app in applications:
            app["id"] = str(app["_id"])
            del app["_id"]
            
            cv = await db["hr_cvs"].find_one({"_id": ObjectId(app["cv_id"])})
            if cv:
                app["filename"] = cv.get("filename", "CV Ẩn")
                app["candidate_email"] = cv.get("candidate_info", {}).get("email", "")
            else:
                app["filename"] = "CV Ẩn"
                
            job = await db["hr_jobs"].find_one({"_id": ObjectId(app["job_id"])})
            app["job_title"] = job.get("title", "Chiến dịch đã xóa") if job else "Chiến dịch đã xóa"
                
            result.append(app)
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
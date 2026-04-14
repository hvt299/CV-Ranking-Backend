from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form, Body
from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel

from app.database.config import get_db
from app.database.models import CVUpdate

from app.services.nlp_engine import extract_text, analyze_cv_text, score_cv
from app.auth import get_current_user

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
    
    pool_record = {
        "hr_email": current_hr,
        "filename": file.filename,
        "raw_text": raw_text,
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
        "raw_text": cv_record.get("raw_text", ""),
        "skills": cv_record.get("extracted_skills", []),
        "years_of_experience": cv_record["candidate_info"].get("years_of_experience", 0),
        "skill_experience": cv_record["candidate_info"].get("skill_experience", {}),
        "education_level": cv_record["candidate_info"].get("education_level", "Không đề cập")
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
    current_hr: str = Depends(get_current_user)
):
    db = get_db()
    try:
        filter_query = {"_id": ObjectId(app_id), "hr_email": current_hr} 
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

        return {"status": "success", "message": "Đã cập nhật trạng thái ứng viên thành công"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{cv_id}")
async def delete_cv_from_pool(
    cv_id: str, 
    current_hr: str = Depends(get_current_user)
):
    db = get_db()
    try:
        result = await db["hr_cvs"].delete_one({"_id": ObjectId(cv_id), "hr_email": current_hr})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy CV trong kho")
        
        await db["hr_applications"].delete_many({"cv_id": cv_id})
            
        return {"status": "success", "message": "Đã xóa vĩnh viễn CV khỏi hệ thống"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pool")
async def get_talent_pool(current_hr: str = Depends(get_current_user)):
    db = get_db()
    try:
        cursor = db["hr_cvs"].find({"hr_email": current_hr}).sort("created_at", -1)
        cvs = await cursor.to_list(length=500)
        
        for cv in cvs:
            cv["id"] = str(cv["_id"])
            del cv["_id"]
            if "raw_text" in cv:
                del cv["raw_text"]
                
        return cvs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
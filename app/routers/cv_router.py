from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form, Body
from bson import ObjectId
from datetime import datetime, timezone

from app.database.config import get_db
from app.database.models import CVUpdate

from app.services.nlp_engine import extract_text, analyze_cv_text, score_cv
from app.auth import get_current_user

router = APIRouter(prefix="/api/v1/cv", tags=["CV Processing"])
MAX_FILE_SIZE = 5 * 1024 * 1024

@router.post("/upload")
async def upload_and_score_cv(
    job_id: str = Form(..., description="Mã chiến dịch tuyển dụng (Job ID)"),
    file: UploadFile = File(..., description="File CV định dạng PDF hoặc DOCX"),
    current_hr: str = Depends(get_current_user)
):
    db = get_db()
    
    try:
        jd_data = await db["hr_jobs"].find_one({"_id": ObjectId(job_id), "created_by": current_hr})
    except Exception:
        raise HTTPException(status_code=400, detail="Mã Job ID không hợp lệ định dạng")
        
    if not jd_data:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch tuyển dụng này")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Dung lượng file vượt quá 5MB giới hạn")
    
    try:
        raw_text = await extract_text(file, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Hệ thống không thể đọc được file này: {str(e)}")
        
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Không thể trích xuất văn bản. File có thể là ảnh quét.")

    cv_data = analyze_cv_text(raw_text)
    cv_data["raw_text"] = raw_text
    cv_data["filename"] = file.filename

    candidate_email = cv_data.get("email")
    if candidate_email:
        existing_cv = await db["hr_cvs"].find_one({
            "job_id": job_id, 
            "candidate_info.email": candidate_email
        })
        if existing_cv:
            raise HTTPException(status_code=400, detail=f"Ứng viên có email {candidate_email} đã được tải lên trong chiến dịch này rồi!")

    scoring_result = score_cv(cv_data, jd_data)

    applicant_record = {
        "job_id": job_id,
        "hr_email": current_hr,
        "filename": file.filename,
        "candidate_info": {
            "email": candidate_email,
            "phone": cv_data.get("phone"),
            "github": cv_data.get("github"),
            "education_level": cv_data.get("education_level"),
            "years_of_experience": cv_data.get("years_of_experience"),
        },
        "extracted_skills": cv_data.get("skills", []),
        "ai_score": scoring_result, 
        "status": "Mới", 
        "note": "",
        "created_at": datetime.now(timezone.utc)
    }

    result = await db["hr_cvs"].insert_one(applicant_record)

    return {
        "message": "Phân tích và chấm điểm CV thành công",
        "cv_id": str(result.inserted_id),
        "candidate_email": candidate_email,
        "ai_score": scoring_result
    }
    
@router.patch("/{cv_id}")
async def update_cv_status_and_notes(
    cv_id: str, 
    update_data: CVUpdate = Body(...),
    current_hr: str = Depends(get_current_user)
):
    db = get_db()
    
    try:
        filter_query = {"_id": ObjectId(cv_id), "hr_email": current_hr} 
        
        update_query = {}
        
        if update_data.status:
            update_query.setdefault("$set", {})["status"] = update_data.status
            
        if update_data.note:
            update_query.setdefault("$push", {})["notes"] = update_data.note
            
        if not update_query:
            return {"message": "Không có dữ liệu mới nào để cập nhật"}

        result = await db["hr_cvs"].update_one(filter_query, update_query) 
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy CV này hoặc bạn không có quyền thao tác")

        return {
            "status": "success",
            "message": "Đã cập nhật hồ sơ ứng viên thành công"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật CV: {str(e)}")
    
@router.delete("/{cv_id}")
async def delete_cv(
    cv_id: str, 
    current_hr: str = Depends(get_current_user)
):
    db = get_db()
    try:
        result = await db["hr_cvs"].delete_one({
            "_id": ObjectId(cv_id), 
            "hr_email": current_hr
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy CV hoặc bạn không có quyền xóa!")
            
        return {"status": "success", "message": "Đã xóa hồ sơ ứng viên vĩnh viễn"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {str(e)}")
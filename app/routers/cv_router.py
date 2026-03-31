from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form, Body
from bson import ObjectId
from datetime import datetime, timezone

from app.database.config import get_db
from app.database.models import CVUpdate

from app.services.nlp_engine import (
    extract_text, 
    analyze_cv_text, 
    score_cv, 
    calculate_nlp_similarity
)

from app.auth import get_current_user

router = APIRouter(prefix="/api/v1/cv", tags=["CV Processing"])

MAX_FILE_SIZE = 5 * 1024 * 1024

@router.post("/parse")
async def parse_cv(file: UploadFile = File(...)):
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(400, "Only PDF or DOCX allowed")

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large")

    text = await extract_text(file, content)

    return {
        "filename": file.filename,
        "text_length": len(text)
    }

@router.post("/analyze")
async def analyze_cv(file: UploadFile = File(...)):
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(400, "Only PDF or DOCX allowed")

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large")

    text = await extract_text(file, content)

    result = analyze_cv_text(text)

    return {
        "filename": file.filename,
        "result": result
    }

@router.post("/rank")
async def rank_cv(
    file: UploadFile = File(...),
    required_skills: str = Form(...),
    jd_description: str = Form(""),
    required_experience: float = Form(0.0)
):
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(400, "Hệ thống chỉ hỗ trợ định dạng PDF hoặc DOCX")

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "Dung lượng file vượt quá 5MB giới hạn")

    text = await extract_text(file, content)
    extracted = analyze_cv_text(text)

    jd_skills = [s.strip().lower() for s in required_skills.split(",") if s.strip()]
    skill_ranking = score_cv(extracted["skills"], jd_skills)
    skill_score = skill_ranking["score"]

    nlp_score = calculate_nlp_similarity(text, jd_description) if jd_description else 0.0

    candidate_yoe = extracted.get("years_of_experience", 0.0)
    yoe_score = 100.0 if candidate_yoe >= required_experience else (candidate_yoe / required_experience) * 100 if required_experience > 0 else 100.0

    final_score = round((0.5 * skill_score) + (0.3 * nlp_score) + (0.2 * yoe_score), 2)

    return {
        "filename": file.filename,
        "scores": {
            "final_score": final_score,
            "skill_score": skill_score,
            "nlp_score": nlp_score,
            "yoe_score": round(yoe_score, 2)
        },
        "details": {
            "candidate_education": extracted.get("education_level", "Không đề cập"),
            "candidate_yoe": candidate_yoe,
            "candidate_skills": extracted["skills"],
            "matched_skills": skill_ranking["matched_skills"],
            "missing_skills": skill_ranking["missing_skills"]
        }
    }

@router.post("/upload", status_code=201)
async def upload_and_save_cv(
    file: UploadFile = File(...),
    current_hr: str = Depends(get_current_user)
):
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(400, "Hệ thống chỉ hỗ trợ định dạng PDF hoặc DOCX")

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "Dung lượng file vượt quá 5MB giới hạn")

    text = await extract_text(file, content)
    extracted_info = analyze_cv_text(text)

    db = get_db()

    candidate_email = extracted_info.get("email")
    if candidate_email:
        existing_cv = await db["cvs"].find_one({
            "email": candidate_email,
            "uploaded_by": current_hr
        })
        if existing_cv:
            raise HTTPException(
                status_code=400, 
                detail=f"Ứng viên {candidate_email} đã tồn tại trong kho dữ liệu của bạn!"
            )

    cv_document = {
        "filename": file.filename,
        "email": candidate_email,
        "phone": extracted_info.get("phone"),
        "github": extracted_info.get("github"),
        "skills": extracted_info.get("skills", []),
        "skill_count": extracted_info.get("skill_count", 0),
        "years_of_experience": extracted_info.get("years_of_experience", 0.0),
        "education_level": extracted_info.get("education_level", "Không đề cập"),
        "raw_text": text,
        "status": "new",
        "notes": [],
        "uploaded_by": current_hr,
        "created_at": datetime.now(timezone.utc)
    }

    try:
        result = await db["cvs"].insert_one(cv_document)
        
        return {
            "status": "success",
            "message": "CV đã được phân tích và lưu trữ an toàn",
            "cv_id": str(result.inserted_id),
            "data": extracted_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu vào Database: {str(e)}")
    
@router.patch("/{cv_id}")
async def update_cv_status_and_notes(cv_id: str, update_data: CVUpdate = Body(...)):
    db = get_db()
    
    try:
        filter_query = {"_id": ObjectId(cv_id)}
        
        update_query = {}
        
        if update_data.status:
            update_query.setdefault("$set", {})["status"] = update_data.status
            
        if update_data.note:
            update_query.setdefault("$push", {})["notes"] = update_data.note
            
        if not update_query:
            return {"message": "Không có dữ liệu mới nào để cập nhật"}

        result = await db["cvs"].update_one(filter_query, update_query)
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Không tìm thấy CV này")

        return {
            "status": "success",
            "message": "Đã cập nhật hồ sơ ứng viên thành công"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi cập nhật CV: {str(e)}")
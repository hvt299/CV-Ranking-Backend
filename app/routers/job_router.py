from fastapi import APIRouter, HTTPException, Body, Query, Depends
from bson import ObjectId
from datetime import datetime, timezone

from app.database.config import get_db
from app.database.models import JobDescriptionCreate
from app.auth import get_current_user

from app.services.nlp_engine import score_cv, calculate_nlp_similarity

router = APIRouter(prefix="/api/v1/jobs", tags=["Job Management & Ranking"])

@router.post("/", status_code=201)
async def create_job(
    job: JobDescriptionCreate = Body(...),
    current_hr: str = Depends(get_current_user)
):
    db = get_db()
    
    job_dict = job.model_dump()
    job_dict["created_at"] = datetime.now(timezone.utc)
    job_dict["required_skills"] = [s.strip().lower() for s in job_dict["required_skills"]]
    job_dict["created_by"] = current_hr
    
    new_job = await db["jobs"].insert_one(job_dict)
    
    return {
        "status": "success",
        "message": "Đã tạo Job Description thành công",
        "job_id": str(new_job.inserted_id)
    }

@router.get("/{job_id}/ranking")
async def get_job_ranking(
    job_id: str,
    page: int = Query(1, ge=1, description="Số trang hiện tại (mặc định: 1)"),
    limit: int = Query(10, ge=1, le=50, description="Số CV mỗi trang (mặc định: 10, tối đa: 50)"),
    min_score: float = Query(0.0, ge=0.0, le=100.0, description="Lọc CV có điểm lớn hơn hoặc bằng"),
    start_date: str = Query(None, description="Từ ngày (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Đến ngày (YYYY-MM-DD)"),
    current_hr: str = Depends(get_current_user)
):
    db = get_db()
    
    try:
        job = await db["jobs"].find_one({"_id": ObjectId(job_id)})
        if not job:
            raise HTTPException(status_code=404, detail="Không tìm thấy Job Description")
        
        if job.get("created_by") and job.get("created_by") != current_hr:
            raise HTTPException(status_code=403, detail="Bạn không có quyền xem bảng xếp hạng của Job này")

        cv_query = {"uploaded_by": current_hr}
        if start_date or end_date:
            date_filter = {}
            if start_date:
                dt_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                date_filter["$gte"] = dt_start
            if end_date:
                dt_end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
                date_filter["$lte"] = dt_end
                
            cv_query["created_at"] = date_filter

        cvs_cursor = db["cvs"].find(cv_query)
        cvs = await cvs_cursor.to_list(length=None)

        if not cvs:
            return {"message": "Không có CV nào trong khoảng thời gian này."}

        leaderboard = []
        for cv in cvs:
            skill_ranking = score_cv(cv.get("skills", []), job.get("required_skills", []))
            nlp_score = calculate_nlp_similarity(cv.get("raw_text", ""), job.get("description", ""))
            req_yoe = job.get("required_experience", 0.0)
            cand_yoe = cv.get("years_of_experience", 0.0)
            yoe_score = 100.0 if cand_yoe >= req_yoe else (cand_yoe / req_yoe) * 100 if req_yoe > 0 else 100.0
            final_score = round((0.5 * skill_ranking["score"]) + (0.3 * nlp_score) + (0.2 * yoe_score), 2)
            
            leaderboard.append({
                "cv_id": str(cv["_id"]),
                "filename": cv["filename"],
                "candidate_email": cv.get("email", "Không có"),
                "scores": {
                    "final_score": final_score,
                    "skill_score": skill_ranking["score"],
                    "nlp_score": nlp_score,
                    "yoe_score": round(yoe_score, 2)
                },
                "matched_skills": skill_ranking["matched_skills"],
                "years_of_experience": cand_yoe,
                "education_level": cv.get("education_level", "Không đề cập")
            })

        if min_score > 0:
            leaderboard = [cv for cv in leaderboard if cv["scores"]["final_score"] >= min_score]

        leaderboard.sort(key=lambda x: x["scores"]["final_score"], reverse=True)

        total_candidates = len(leaderboard)
        total_pages = (total_candidates + limit - 1) // limit
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        
        paginated_leaderboard = leaderboard[start_idx:end_idx]

        return {
            "status": "success",
            "job_title": job.get("title"),
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_candidates_matched": total_candidates,
                "limit": limit
            },
            "leaderboard": paginated_leaderboard
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Định dạng ngày không hợp lệ. Vui lòng dùng YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {str(e)}")
from datetime import datetime
import os
import io
import re
import csv
import pdfplumber
import docx
from typing import List, Dict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_FILE_PATH = os.path.join(BASE_DIR, "data", "skills.csv")

def load_skills(file_path: str) -> Dict[str, List[str]]:
    skill_map = {}
    with open(file_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            main = row[0].strip().lower()
            variants = [v.strip().lower() for v in row if v.strip()]
            skill_map[main] = variants
    return skill_map

SKILL_MAP = load_skills(SKILLS_FILE_PATH)

def extract_text_from_pdf(file_bytes: bytes) -> str:
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    return text

def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs)

def extract_skills(text: str) -> List[str]:
    text_lower = text.lower()
    found = set()

    for main, variants in SKILL_MAP.items():
        for v in variants:
            pattern = rf"\b{re.escape(v)}\b"
            if re.search(pattern, text_lower):
                found.add(main)
                break

    return list(found)

def extract_basic_info(text: str) -> Dict:
    email = re.search(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text)
    phone_match = re.search(r"(?:\+84|0)(?:[ .-]?\d){9,10}", text)
    phone = None
    if phone_match:
        phone = re.sub(r"[ .-]", "", phone_match.group(0))
    github = re.search(r"(https?://)?(www\.)?github\.com/[A-Za-z0-9_-]+", text)

    return {
        "email": email.group(0) if email else None,
        "phone": phone,
        "github": github.group(0) if github else None,
    }

def remove_duplicate_semantic(skills: list) -> list:
    skills_sorted = sorted(skills, key=len, reverse=True)
    filtered = []
    for skill in skills_sorted:
        if not any(skill.lower() in s.lower() for s in filtered):
            filtered.append(skill)
    return filtered

def analyze_cv_text(text: str) -> Dict:
    info = extract_basic_info(text)
    skills = extract_skills(text)
    skills = remove_duplicate_semantic(skills)

    return {
        **info,
        "skills": skills,
        "skill_count": len(skills)
    }

from app.database.config import connect_to_mongo, close_mongo_connection, get_db
from app.database.models import JobDescriptionCreate
from bson import ObjectId
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Body
from fastapi.concurrency import run_in_threadpool
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = FastAPI(
    title="CV Ranking System API",
    version="1.0.0"
)

MAX_FILE_SIZE = 5 * 1024 * 1024

def score_cv(candidate_skills, required_skills):
    candidate_set = set([s.lower() for s in candidate_skills])
    required_set = set([s.lower() for s in required_skills])

    if not required_set:
        return {
            "score": 0,
            "matched_skills": [],
            "missing_skills": []
        }

    matched = candidate_set.intersection(required_set)

    score = (len(matched) / len(required_set)) * 100

    return {
        "score": round(score, 2),
        "matched_skills": list(matched),
        "missing_skills": list(required_set - candidate_set)
    }

def calculate_nlp_similarity(cv_text: str, jd_text: str) -> float:
    if not cv_text or not jd_text:
        return 0.0

    vectorizer = TfidfVectorizer(stop_words='english')

    try:
        tfidf_matrix = vectorizer.fit_transform([cv_text, jd_text])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return round(similarity * 100, 2)
    except Exception as e:
        print(f"Lỗi khi chạy TF-IDF: {e}")
        return 0.0

async def extract_text(file: UploadFile, content: bytes):
    if file.filename.endswith(".pdf"):
        return await run_in_threadpool(extract_text_from_pdf, content)
    elif file.filename.endswith(".docx"):
        return await run_in_threadpool(extract_text_from_docx, content)
    else:
        raise HTTPException(400, "Unsupported file format")

@app.get("/")
def root():
    return {"message": "CV Ranking System API running"}

@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()

@app.post("/api/v1/cv/parse")
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

@app.post("/api/v1/cv/analyze")
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

@app.post("/api/v1/cv/rank")
async def rank_cv(
    file: UploadFile = File(...),
    required_skills: str = Form(...),
    jd_description: str = Form("")
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

    final_score = round((0.7 * skill_score) + (0.3 * nlp_score), 2)

    return {
        "filename": file.filename,
        "scores": {
            "final_score": final_score,
            "skill_score": skill_score,
            "nlp_score": nlp_score
        },
        "details": {
            "candidate_skills": extracted["skills"],
            "matched_skills": skill_ranking["matched_skills"],
            "missing_skills": skill_ranking["missing_skills"]
        }
    }

@app.post("/api/v1/jobs", status_code=201)
async def create_job(job: JobDescriptionCreate = Body(...)):
    db = get_db()
    
    job_dict = job.dict()
    job_dict["created_at"] = datetime.utcnow()
    job_dict["required_skills"] = [s.strip().lower() for s in job_dict["required_skills"]]
    
    new_job = await db["jobs"].insert_one(job_dict)
    
    return {
        "status": "success",
        "message": "Đã tạo Job Description thành công",
        "job_id": str(new_job.inserted_id)
    }

@app.post("/api/v1/cv/upload", status_code=201)
async def upload_and_save_cv(file: UploadFile = File(...)):
    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(400, "Hệ thống chỉ hỗ trợ định dạng PDF hoặc DOCX")

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "Dung lượng file vượt quá 5MB giới hạn")

    text = await extract_text(file, content)
    extracted_info = analyze_cv_text(text)

    db = get_db()
    cv_document = {
        "filename": file.filename,
        "email": extracted_info.get("email"),
        "phone": extracted_info.get("phone"),
        "github": extracted_info.get("github"),
        "skills": extracted_info.get("skills", []),
        "skill_count": extracted_info.get("skill_count", 0),
        "raw_text": text,
        "created_at": datetime.utcnow()
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
    
@app.get("/api/v1/jobs/{job_id}/ranking")
async def get_job_ranking(job_id: str):
    db = get_db()
    
    try:
        job = await db["jobs"].find_one({"_id": ObjectId(job_id)})
        if not job:
            raise HTTPException(status_code=404, detail="Không tìm thấy Job Description")

        cvs_cursor = db["cvs"].find({})
        cvs = await cvs_cursor.to_list(length=100)

        if not cvs:
            return {"message": "Chưa có CV nào trong hệ thống để xếp hạng."}

        leaderboard = []
        for cv in cvs:
            skill_ranking = score_cv(cv.get("skills", []), job.get("required_skills", []))
            skill_score = skill_ranking["score"]
            
            nlp_score = calculate_nlp_similarity(cv.get("raw_text", ""), job.get("description", ""))
            
            final_score = round((0.7 * skill_score) + (0.3 * nlp_score), 2)
            
            leaderboard.append({
                "cv_id": str(cv["_id"]),
                "filename": cv["filename"],
                "candidate_email": cv.get("email", "Không có"),
                "scores": {
                    "final_score": final_score,
                    "skill_score": skill_score,
                    "nlp_score": nlp_score
                },
                "matched_skills": skill_ranking["matched_skills"]
            })

        leaderboard.sort(key=lambda x: x["scores"]["final_score"], reverse=True)

        return {
            "status": "success",
            "job_title": job.get("title"),
            "total_candidates": len(leaderboard),
            "leaderboard": leaderboard
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý xếp hạng: {str(e)}")
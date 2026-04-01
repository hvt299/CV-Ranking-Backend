import os
import io
import re
import csv
from typing import Set, Dict, List, Tuple

import pdfplumber
import docx

from fastapi import UploadFile, HTTPException
from fastapi.concurrency import run_in_threadpool

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS_FILE_PATH = os.path.join(BASE_DIR, "data", "skills.csv")

tfidf_vectorizer = TfidfVectorizer(stop_words='english')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

async def extract_text(file: UploadFile, content: bytes):
    if file.filename.endswith(".pdf"):
        return await run_in_threadpool(extract_text_from_pdf, content)
    elif file.filename.endswith(".docx"):
        return await run_in_threadpool(extract_text_from_docx, content)
    else:
        raise HTTPException(400, "Unsupported file format")

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

def extract_years_of_experience(text: str) -> float:
    text_lower = text.lower()
    
    pattern1 = r"(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:năm|years?)\s*(?:kinh nghiệm|kinh nghiem|of experience|experience|exp)"
    pattern2 = r"(?:kinh nghiệm|kinh nghiem|experience|exp).{0,20}?(\d+(?:\.\d+)?)\s*(?:năm|years?)"

    yoe = 0.0
    
    for pattern in [pattern1, pattern2]:
        matches = re.findall(pattern, text_lower)
        if matches:
            numbers = [float(m) for m in matches]
            yoe = max(max(numbers), yoe)
            
    if yoe > 40:
        return 0.0
        
    return round(yoe, 1)

def extract_education_level(text: str) -> str:
    text_lower = text.lower()
    
    education_patterns = {
        "Tiến sĩ (PhD)": r"\b(tiến sĩ|phd|ph\.d|doctorate)\b",
        "Thạc sĩ (Master)": r"\b(thạc sĩ|thac si|master|mba|msc|m\.s|m\.a)\b",
        "Cử nhân/Kỹ sư (Bachelor)": r"\b(cử nhân|cu nhan|kỹ sư|ky su|bachelor|bsc|b\.s|b\.a|engineer)\b",
        "Cao đẳng (College)": r"\b(cao đẳng|cao dang|associate degree|college)\b"
    }

    for level, pattern in education_patterns.items():
        if re.search(pattern, text_lower):
            return level

    return "Không đề cập"

def analyze_cv_text(text: str) -> Dict:
    info = extract_basic_info(text)
    skills = extract_skills(text)
    skills = remove_duplicate_semantic(skills)
    yoe = extract_years_of_experience(text)
    edu_level = extract_education_level(text)

    return {
        **info,
        "skills": skills,
        "skill_count": len(skills),
        "years_of_experience": yoe,
        "education_level": edu_level
    }

def calculate_skill_score(cv_skills: Set[str], required_skills: List[dict], preferred_skills: List[dict]) -> float:
    if not required_skills and not preferred_skills:
        return 0.0

    cv_skills_lower = {skill.lower().strip() for skill in cv_skills}
    
    total_required_weight = sum(skill.get("weight", 0.5) for skill in required_skills)
    earned_required_score = 0.0
    
    for req_skill in required_skills:
        skill_name = req_skill.get("name", "").lower().strip()
        if skill_name in cv_skills_lower:
            earned_required_score += req_skill.get("weight", 0.5)
            
    base_skill_score = (earned_required_score / total_required_weight) * 100 if total_required_weight > 0 else 0

    bonus_score = 0.0
    for pref_skill in preferred_skills:
        skill_name = pref_skill.get("name", "").lower().strip()
        if skill_name in cv_skills_lower:
            bonus_score += 10 * pref_skill.get("weight", 0.5)

    final_skill_score = min(120, base_skill_score + bonus_score)
    return round(final_skill_score, 2)

def calculate_experience_score(cv_yoe: int, jd_min_yoe: int) -> float:
    if jd_min_yoe == 0:
        return 100.0
        
    if cv_yoe >= jd_min_yoe:
        bonus = min((cv_yoe - jd_min_yoe) * 5, 10) 
        return 100.0 + bonus
    else:
        ratio = cv_yoe / jd_min_yoe
        return round(ratio * 100, 2)

def calculate_nlp_similarity(cv_text: str, jd_text: str) -> float:
    if not cv_text or not jd_text:
        return 0.0
        
    try:
        tfidf_matrix = tfidf_vectorizer.fit_transform([cv_text, jd_text])
        similarity_score = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return round(float(similarity_score) * 100, 2)
    except Exception as e:
        logger.error(f"Lỗi khi tính TF-IDF: {str(e)}")
        return 0.0

def score_cv(cv_data: dict, jd_data: dict) -> dict:
    jd_required_skills = jd_data.get("required_skills", [])
    jd_preferred_skills = jd_data.get("preferred_skills", [])
    jd_min_yoe = jd_data.get("min_yoe", 0)
    jd_search_text = jd_data.get("jd_search_text", "")

    cv_text = cv_data.get("raw_text", "")
    cv_skills = set(cv_data.get("skills", []))
    cv_yoe = cv_data.get("years_of_experience", 0)

    skill_score = calculate_skill_score(cv_skills, jd_required_skills, jd_preferred_skills)
    experience_score = calculate_experience_score(cv_yoe, jd_min_yoe)
    nlp_score = calculate_nlp_similarity(cv_text, jd_search_text)

    WEIGHT_SKILL = 0.45
    WEIGHT_EXP = 0.25
    WEIGHT_NLP = 0.30

    total_score = (skill_score * WEIGHT_SKILL) + (experience_score * WEIGHT_EXP) + (nlp_score * WEIGHT_NLP)

    return {
        "total_score": round(total_score, 2),
        "score_breakdown": {
            "skills_score": skill_score,
            "experience_score": experience_score,
            "nlp_score": nlp_score
        },
        "matched_skills": list(cv_skills.intersection({s.get("name", "").lower() for s in jd_required_skills + jd_preferred_skills})),
        "missing_required_skills": list({s.get("name", "").lower() for s in jd_required_skills}.difference(cv_skills))
    }
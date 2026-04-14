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

from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS_FILE_PATH = os.path.join(BASE_DIR, "data", "skills.csv")

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

    return {
        "email": email.group(0) if email else None,
        "phone": phone
    }

def extract_social_links(text: str) -> dict:
    links = {
        "github": None,
        "linkedin": None,
        "portfolio": []
    }

    url_pattern = r'(?:https?:\/\/)?(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{2,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)'
    
    matches = re.finditer(url_pattern, text.lower())

    for match in matches:
        url = match.group(0).rstrip('.,;)]')

        if '@' in url and not url.startswith('http'):
            continue
            
        if 'topcv.vn' in url or len(url) < 8:
            continue

        if 'github.com' in url or 'gitlab.com' in url:
            if not links['github']:
                links['github'] = url
        elif 'linkedin.com' in url:
            if not links['linkedin']:
                links['linkedin'] = url
        else:
            if url not in links['portfolio']:
                links['portfolio'].append(url)

    return links

def extract_years_of_experience(text: str) -> Tuple[float, Dict[str, float]]:
    text_lower = text.lower()
    
    pattern1 = r"(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:năm|years?)\s*(?:kinh nghiệm|kinh nghiem|of experience|experience|exp)"
    pattern2 = r"(?:kinh nghiệm|kinh nghiem|experience|exp).{0,20}?(\d+(?:\.\d+)?)\s*(?:năm|years?)"
    
    yoe_explicit = 0.0
    for pattern in [pattern1, pattern2]:
        matches = re.findall(pattern, text_lower)
        if matches:
            numbers = [float(m) for m in matches]
            yoe_explicit = max(max(numbers), yoe_explicit)

    lines = text_lower.split('\n')
    date_pattern = r"(?:0?[1-9]|1[0-2])?[/.-]?20\d{2}\s*[-–~]?\s*(?:nay|present|hiện tại|(?:0?[1-9]|1[0-2])?[/.-]?20\d{2})"
    
    total_years_inferred = 0.0
    current_year = datetime.now().year
    edu_keywords = ["đại học", "học viện", "cao đẳng", "thạc sĩ", "tiến sĩ", "university", "college", "school", "gpa"]
    
    skill_experience = {} 
    
    for i, line in enumerate(lines):
        matches = re.finditer(date_pattern, line)
        for match in matches:
            is_education = False
            start_check = max(0, i - 2)
            end_check = min(len(lines), i + 3)
            context_text = " ".join(lines[start_check:end_check])
            
            for edu_kw in edu_keywords:
                if edu_kw in context_text:
                    is_education = True
                    break
                    
            if is_education:
                continue
                
            matched_str = match.group(0)
            years = re.findall(r"20\d{2}", matched_str)
            start_year = end_year = 0
            
            if len(years) == 2:
                start_year = int(years[0])
                end_year = int(years[1])
            elif len(years) == 1 and any(w in matched_str for w in ['nay', 'present', 'hiện tại']):
                start_year = int(years[0])
                end_year = current_year
            else:
                continue
                
            if 1950 <= start_year <= end_year <= current_year:
                dur = end_year - start_year
                if dur == 0:
                    dur = 0.5
                
                total_years_inferred += dur
                
                job_context_text = " ".join(lines[max(0, i - 1) : min(len(lines), i + 6)])
                local_skills = extract_skills(job_context_text)
                
                for skill in local_skills:
                    skill_experience[skill] = skill_experience.get(skill, 0.0) + dur

    final_total_yoe = max(yoe_explicit, total_years_inferred)
                
    return min(round(final_total_yoe, 1), 40.0), skill_experience

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
    yoe, skill_experience = extract_years_of_experience(text) 
    edu_level = extract_education_level(text)
    social_links = extract_social_links(text)

    return {
        **info,
        "skills": skills,
        "skill_count": len(skills),
        "years_of_experience": yoe,
        "skill_experience": skill_experience,
        "education_level": edu_level,
        "github": social_links["github"],
        "linkedin": social_links["linkedin"],
        "portfolio": social_links["portfolio"],
    }

def get_normalized_skill(raw_skill: str) -> str:
    raw_lower = raw_skill.lower().strip()
    for root, variants in SKILL_MAP.items():
        if raw_lower == root or raw_lower in variants:
            return root
    return raw_lower

def calculate_skill_score(cv_skills: set, cv_skill_exp: dict, jd_required: list, jd_preferred: list):
    score = 0.0
    total_weight = sum(s.get('weight', 1.0) for s in jd_required) + sum(s.get('weight', 0.5) for s in jd_preferred)
    
    if total_weight == 0:
        return 100.0, list(cv_skills), []

    matched_skills = []
    missing_required_skills = []

    def evaluate_skill(skill_dict, default_weight):
        raw_name = skill_dict.get('name', '')
        weight = skill_dict.get('weight', default_weight)
        req_years = skill_dict.get('min_years', 0)
        
        norm_name = get_normalized_skill(raw_name)

        if norm_name in cv_skills:
            cv_years = cv_skill_exp.get(norm_name, 0.0)
            
            if req_years > 0:
                if cv_years >= req_years:
                    bonus = min((cv_years - req_years) * 0.1, 0.2) * weight
                    earned = weight + bonus
                else:
                    ratio = cv_years / req_years
                    earned = weight * (0.5 + 0.5 * ratio) 
            else:
                earned = weight
                
            return earned, raw_name, True
            
        return 0.0, raw_name, False

    for req in jd_required:
        earned, raw_name, is_matched = evaluate_skill(req, 1.0)
        if is_matched:
            score += earned
            matched_skills.append(raw_name) 
        else:
            missing_required_skills.append(raw_name)

    for pref in jd_preferred:
        earned, raw_name, is_matched = evaluate_skill(pref, 0.5)
        if is_matched:
            score += earned
            matched_skills.append(raw_name)

    final_score = (score / total_weight) * 100 if total_weight > 0 else 0
    final_score = min(final_score, 110.0) 
    
    return round(final_score, 2), matched_skills, missing_required_skills

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
        local_vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = local_vectorizer.fit_transform([cv_text, jd_text])
        similarity_score = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return round(float(similarity_score) * 100, 2)
    except Exception as e:
        logger.error(f"Lỗi khi tính TF-IDF: {str(e)}")
        return 0.0

def calculate_education_score(cv_edu: str, jd_min_edu: str) -> float:
    if not jd_min_edu or jd_min_edu.lower() == "không yêu cầu":
        return 100.0

    edu_ranks = {
        "không đề cập": 0,
        "chứng chỉ nghề": 1,
        "trung học phổ thông": 1,
        "trung cấp": 2,
        "cao đẳng": 3,
        "cao đẳng (college)": 3,
        "cử nhân": 4,
        "cử nhân/kỹ sư (bachelor)": 4,
        "thạc sĩ": 5,
        "thạc sĩ (master)": 5,
        "tiến sĩ": 6,
        "tiến sĩ (phd)": 6
    }

    cv_rank = edu_ranks.get(cv_edu.lower().strip(), 0)
    jd_rank = edu_ranks.get(jd_min_edu.lower().strip(), 0)

    if jd_rank == 0:
        return 100.0

    if cv_rank >= jd_rank:
        return 100.0
    else:
        return round((cv_rank / jd_rank) * 100, 2)

def score_cv(cv_data: dict, jd_data: dict) -> dict:
    jd_required_skills = jd_data.get("required_skills", [])
    jd_preferred_skills = jd_data.get("preferred_skills", [])
    jd_min_yoe = jd_data.get("min_yoe", 0)
    jd_search_text = jd_data.get("jd_search_text", "")
    
    jd_education = jd_data.get("education", {})
    jd_min_edu = jd_education.get("min_level", "Không yêu cầu")

    cv_text = cv_data.get("raw_text", "")
    cv_skills = set(cv_data.get("skills", []))
    cv_skill_exp = cv_data.get("skill_experience", {})
    cv_yoe = cv_data.get("years_of_experience", 0)
    cv_edu = cv_data.get("education_level", "Không đề cập")

    skill_score, matched_skills, missing_required_skills = calculate_skill_score(cv_skills, cv_skill_exp, jd_required_skills, jd_preferred_skills)
    experience_score = calculate_experience_score(cv_yoe, jd_min_yoe)
    education_score = calculate_education_score(cv_edu, jd_min_edu)
    nlp_score = calculate_nlp_similarity(cv_text, jd_search_text)

    WEIGHT_SKILL = 0.40
    WEIGHT_NLP = 0.30
    WEIGHT_EXP = 0.20
    WEIGHT_EDU = 0.10

    total_score = (
        (skill_score * WEIGHT_SKILL) + 
        (experience_score * WEIGHT_EXP) + 
        (education_score * WEIGHT_EDU) + 
        (nlp_score * WEIGHT_NLP)
    )

    total_score = min(100.0, total_score)

    return {
        "total_score": round(total_score, 2),
        "score_breakdown": {
            "skills_score": skill_score,
            "experience_score": experience_score,
            "education_score": education_score,
            "nlp_score": nlp_score
        },
        "matched_skills": matched_skills,
        "missing_required_skills": missing_required_skills
    }
import os
import io
import re
import csv
from typing import Set, Dict, List, Tuple
import logging
from datetime import datetime

import pdfplumber
import docx

from fastapi import UploadFile, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.services.vector_engine import calculate_cosine_similarity

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS_FOLDER = os.path.join(BASE_DIR, "data")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

def load_skills(file_path: str) -> Dict[str, List[str]]:
    skill_map = {}
    try:
        with open(file_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if not row or len(row) < 3:
                    continue
                main = row[2].strip().lower()
                variants = set([main] + [v.strip().lower() for v in row[3:] if v.strip()])
                skill_map[main] = list(variants)
    except Exception as e:
        logger.error(f"Lỗi tải file {file_path}: {e}")
    return skill_map

def load_all_skills() -> Dict[str, List[str]]:
    merged_skill_map = {}

    for filename in os.listdir(SKILLS_FOLDER):
        if not filename.startswith("skills_") or not filename.endswith(".csv"):
            continue

        file_path = os.path.join(SKILLS_FOLDER, filename)
        skill_map = load_skills(file_path)

        for main, variants in skill_map.items():
            if main not in merged_skill_map:
                merged_skill_map[main] = variants
            else:
                merged_skill_map[main] = list(
                    set(merged_skill_map[main]) | set(variants)
                )

    logger.info(f"Đã tải {len(merged_skill_map)} kỹ năng từ các file CSV.")

    return merged_skill_map


SKILL_MAP = load_all_skills()

def get_smart_skill_pattern(skill: str) -> str:
    escaped = re.escape(skill)
    if not skill[-1].isalnum():
        return rf"(?:\b|(?<=\s)){escaped}(?=\s|$|[.,;)])"
    if not skill[0].isalnum():
        return rf"(?:^|\s|[.,;(]){escaped}\b"
    return rf"\b{escaped}\b"

async def extract_text(file: UploadFile, content: bytes):
    if file.filename.endswith(".pdf"):
        return await run_in_threadpool(extract_text_from_pdf, content)
    elif file.filename.endswith(".docx"):
        return await run_in_threadpool(extract_text_from_docx, content)
    else:
        raise HTTPException(400, "Định dạng file không hỗ trợ (Chỉ nhận PDF/DOCX)")

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
            pattern = get_smart_skill_pattern(v)
            if re.search(pattern, text_lower):
                found.add(main)
                break

    return sorted(list(found))

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

        if url.endswith(('.js', '.ts', '.php', '.py', '.html', '.css', '.cpp')):
            continue

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
        "portfolio": social_links["portfolio"]
    }

def get_normalized_skill(raw_skill: str) -> str:
    raw_lower = raw_skill.lower().strip()
    for root, variants in SKILL_MAP.items():
        if raw_lower == root or raw_lower in variants:
            return root
    return raw_lower

def verify_skill_context(text: str, skills: list) -> dict:
    sentences = re.split(r'(?<=[.!?\n])\s+', text)
    action_verbs = [
        "phát triển", "xây dựng", "thiết kế", "tối ưu", "quản lý", "sử dụng", "tham gia", "đóng góp",
        "develop", "build", "create", "optimize", "manage", "use", "implement", "deploy", "work"
    ]
    
    skill_confidence = {}
    for skill in skills:
        confidence = 0.5
        for sentence in sentences:
            if skill.lower() in sentence.lower():
                words = sentence.split()
                if len(words) > 7 and any(verb in sentence.lower() for verb in action_verbs):
                    confidence = 1.0
                    break
        skill_confidence[skill] = confidence
    return skill_confidence

def calculate_skill_score(cv_skills: set, cv_skill_exp: dict, cv_yoe: float, jd_required: list, jd_preferred: list, skill_confidence: dict):
    score = 0.0
    total_weight = sum(s.get('weight', 1.0) for s in jd_required) + sum(s.get('weight', 0.5) for s in jd_preferred)
    
    skill_details = []
    missing_required_skills = []
    matched_skills_names = []

    if total_weight == 0:
        return 100.0, [], [], []

    def evaluate_skill(skill_dict, default_weight):
        raw_name = skill_dict.get('name', '')
        weight = skill_dict.get('weight', default_weight)
        req_years = skill_dict.get('min_years', 0)
        norm_name = get_normalized_skill(raw_name)

        confidence = skill_confidence.get(norm_name, 0.5)
        cv_years = cv_skill_exp.get(norm_name, 0.0)

        if norm_name in cv_skills:
            if cv_years == 0.0 and cv_yoe > 0:
                cv_years = cv_yoe * 0.5
            
            if req_years > 0:
                if cv_years >= req_years:
                    bonus = min((cv_years - req_years) * 0.1, 0.2) * weight
                    earned = (weight + bonus) * confidence
                else:
                    ratio = cv_years / req_years
                    earned = (weight * (0.5 + 0.5 * ratio)) * confidence
            else:
                earned = weight * confidence
                
            return earned, raw_name, True, confidence, cv_years
            
        return 0.0, raw_name, False, 0.0, 0.0

    for req in jd_required:
        earned, raw_name, is_matched, conf, y_exp = evaluate_skill(req, 1.0)
        skill_details.append({
            "skill": raw_name, "matched": is_matched, "confidence": conf, "years_experience": y_exp
        })
        if is_matched:
            score += earned
            matched_skills_names.append(raw_name)
        else:
            missing_required_skills.append(raw_name)

    for pref in jd_preferred:
        earned, raw_name, is_matched, conf, y_exp = evaluate_skill(pref, 0.5)
        skill_details.append({
            "skill": raw_name, "matched": is_matched, "confidence": conf, "years_experience": y_exp
        })
        if is_matched:
            score += earned
            matched_skills_names.append(raw_name)

    final_score = (score / total_weight) * 100 if total_weight > 0 else 0
    return min(final_score, 110.0), skill_details, missing_required_skills, matched_skills_names

def calculate_experience_score(cv_yoe: float, jd_min_yoe: float) -> float:
    if jd_min_yoe == 0:
        return 100.0
    if cv_yoe >= jd_min_yoe:
        bonus = min((cv_yoe - jd_min_yoe) * 5, 10) 
        return 100.0 + bonus
    else:
        return round((cv_yoe / jd_min_yoe) * 100, 2)

def calculate_education_score(cv_edu: str, jd_min_edu: str) -> float:
    if not jd_min_edu or jd_min_edu.lower() == "không yêu cầu":
        return 100.0
    edu_ranks = {
        "không đề cập": 0, "chứng chỉ nghề": 1, "trung học phổ thông": 1,
        "trung cấp": 2, "cao đẳng": 3, "cao đẳng (college)": 3,
        "cử nhân": 4, "cử nhân/kỹ sư (bachelor)": 4,
        "thạc sĩ": 5, "thạc sĩ (master)": 5, "tiến sĩ": 6, "tiến sĩ (phd)": 6
    }
    cv_rank = edu_ranks.get(cv_edu.lower().strip(), 0)
    jd_rank = edu_ranks.get(jd_min_edu.lower().strip(), 0)

    if jd_rank == 0 or cv_rank >= jd_rank:
        return 100.0
    return round((cv_rank / jd_rank) * 100, 2)

def score_cv(cv_data: dict, jd_data: dict) -> dict:
    jd_required_skills = jd_data.get("required_skills", [])
    jd_preferred_skills = jd_data.get("preferred_skills", [])
    jd_min_yoe = jd_data.get("min_yoe", 0)
    jd_education = jd_data.get("education", {})
    jd_min_edu = jd_education.get("min_level", "Không yêu cầu")

    cv_raw_text = cv_data.get("raw_text", "")
    cv_skills_list = cv_data.get("skills", [])
    
    cv_skills = {get_normalized_skill(skill) for skill in cv_skills_list}

    skill_confidence = verify_skill_context(cv_raw_text, cv_skills_list)

    normalized_skill_exp = {}
    for skill, years in cv_data.get("skill_experience", {}).items():
        norm = get_normalized_skill(skill)
        normalized_skill_exp[norm] = max(normalized_skill_exp.get(norm, 0.0), years)

    cv_skill_exp = normalized_skill_exp
    cv_yoe = cv_data.get("years_of_experience", 0)
    cv_edu = cv_data.get("education_level", "Không đề cập")
    jd_vector = jd_data.get("jd_vector_ref", [])
    cv_vector = cv_data.get("cv_vector", [])

    skill_score, skill_details, missing_required_skills, matched_skills_names = calculate_skill_score(
        cv_skills, cv_skill_exp, cv_yoe, jd_required_skills, jd_preferred_skills, skill_confidence
    )
    experience_score = calculate_experience_score(cv_yoe, jd_min_yoe)
    education_score = calculate_education_score(cv_edu, jd_min_edu)
    nlp_score = calculate_cosine_similarity(cv_vector, jd_vector)

    WEIGHT_SKILL = 0.40
    WEIGHT_NLP = 0.30
    WEIGHT_EXP = 0.20
    WEIGHT_EDU = 0.10

    total_score = (skill_score * WEIGHT_SKILL) + (experience_score * WEIGHT_EXP) + (education_score * WEIGHT_EDU) + (nlp_score * WEIGHT_NLP)
    total_score = min(100.0, total_score)

    # ==========================================
    # CÁC LOGIC PENALTY MỚI (ANTI-STUFFING)
    # ==========================================
    penalty_score = 0.0
    fraud_analysis = cv_data.get("fraud_analysis") or {}
    if fraud_analysis.get("detected", False):
        penalty_score += fraud_analysis.get("penalty", 30.0)

    job_hops = cv_data.get("job_hops", 1)
    gap_months = cv_data.get("gap_months", 0)
    
    if cv_yoe > 0:
        avg_tenure = cv_yoe / max(job_hops, 1)
        if avg_tenure < 0.8:
            penalty_score += 15.0
            
    if gap_months > 12:
        penalty_score += 10.0
        
    total_score = max(0.0, total_score - penalty_score)

    return {
        "total_score": round(total_score, 2),
        "score_breakdown": {
            "skills_score": round(skill_score, 2),
            "experience_score": round(experience_score, 2),
            "education_score": round(education_score, 2),
            "nlp_score": round(nlp_score, 2),
            "penalty_score": round(penalty_score, 2),
            "fraud_analysis": fraud_analysis
        },
        "skill_details": skill_details,
        "missing_required_skills": missing_required_skills,
        "top_contributing_sentences": cv_data.get("top_sentences", []),
        "matched_skills": matched_skills_names 
    }
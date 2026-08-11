import io
import re
from typing import Dict, List, Tuple
import logging
from datetime import datetime

import pdfplumber
import docx

from fastapi import UploadFile, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.services.vector_engine import calculate_cosine_similarity
from app.services.llm_service import extract_cv_metrics_with_llm

from app.repositories.skill_repository import SkillRepository

INDUSTRY_SKILL_MAP = {}

async def initialize_skill_map():
    """Hàm này sẽ được gọi ở lifespan trong main.py khi khởi động server"""
    global INDUSTRY_SKILL_MAP
    INDUSTRY_SKILL_MAP.clear()

    # Lấy toàn bộ skill từ DB (limit=0 để không bị giới hạn) - Dùng thẳng ClassMethod
    skills = await SkillRepository.find_many(limit=0)

    merged_map = {}
    for doc in skills:
        ind = doc.get("industry", "other").lower()
        main = doc.get("canonical_name", "").lower()
        aliases = doc.get("aliases", [])
        
        if ind not in merged_map:
            merged_map[ind] = {}
            
        merged_map[ind][main] = list(set([main] + [a.lower() for a in aliases]))
        
    # Xây dựng bộ từ điển tổng hợp (fallback)
    all_skills = {}
    for ind, skill_dict in merged_map.items():
        for main, variants in skill_dict.items():
            if main not in all_skills:
                all_skills[main] = variants
            else:
                all_skills[main] = list(set(all_skills[main]) | set(variants))
                
    merged_map["all"] = all_skills
    INDUSTRY_SKILL_MAP = merged_map
    logger.info(f"AI Engine: Đã tải {len(all_skills)} kỹ năng vào Cache từ MongoDB.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

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

def extract_skills(text: str, industry: str = "all") -> List[str]:
    text_lower = text.lower()
    found = set()

    target_skill_map = INDUSTRY_SKILL_MAP.get(industry, INDUSTRY_SKILL_MAP.get("all", {}))

    for main, variants in target_skill_map.items():
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

async def analyze_cv_text(text: str) -> Dict:
    info = extract_basic_info(text)
    skills = extract_skills(text)
    
    yoe_regex, skill_experience = extract_years_of_experience(text) 
    edu_level_regex = extract_education_level(text)
    social_links = extract_social_links(text)

    llm_metrics = await extract_cv_metrics_with_llm(text)

    final_yoe = llm_metrics.get("years_of_experience")
    if final_yoe == 0.0 and yoe_regex > 0.0:
        final_yoe = yoe_regex

    final_edu = llm_metrics.get("education_level", "Không đề cập")
    if final_edu == "Không đề cập" and edu_level_regex != "Không đề cập":
        final_edu = edu_level_regex

    return {
        **info,
        "skills": skills,
        "skill_count": len(skills),
        "years_of_experience": final_yoe,
        "skill_experience": skill_experience,
        "education_level": final_edu,
        "job_hops": llm_metrics.get("job_hops", 1),
        "gap_months": llm_metrics.get("gap_months", 0),
        "github": social_links["github"],
        "linkedin": social_links["linkedin"],
        "portfolio": social_links["portfolio"]
    }

def get_normalized_skill(raw_skill: str, industry: str = "all") -> str:
    raw_lower = raw_skill.lower().strip()
    target_skill_map = INDUSTRY_SKILL_MAP.get(industry, INDUSTRY_SKILL_MAP.get("all", {}))
    
    for root, variants in target_skill_map.items():
        if raw_lower == root or raw_lower in variants:
            return root
    return raw_lower

def verify_skill_context(text: str, skills: list, industry: str = "other") -> dict:
    sentences = re.split(r'(?<=[.!?\n])\s+', text)
    
    general_verbs = ["quản lý", "tham gia", "hỗ trợ", "chịu trách nhiệm", "thực hiện", "phụ trách", "manage", "support"]
    
    industry_verbs = {
        "it": ["phát triển", "xây dựng", "tối ưu", "triển khai", "deploy", "build", "code"],
        
        # Nhóm Kinh doanh / Marketing / Bán lẻ
        "sales": ["đàm phán", "chốt", "tư vấn", "mở rộng", "thuyết phục", "đạt doanh số", "ký kết"],
        "marketing": ["lên ý tưởng", "chạy", "tối ưu ads", "viết", "sáng tạo", "định hướng", "phân tích thị trường"],
        "retail_lifestyle": ["trưng bày", "phục vụ", "chăm sóc", "tư vấn khách hàng", "kiểm kê"],
        
        # Nhóm Tài chính / Kế toán / Thuế
        "accounting": ["hạch toán", "lập báo cáo", "kê khai", "đối chiếu", "quyết toán", "kiểm kê"],
        "finance": ["thẩm định", "giải ngân", "huy động vốn", "định giá", "kiểm soát rủi ro"],
        
        # Nhóm Xây dựng / Sản xuất
        "construction": ["thi công", "giám sát", "bóc tách khối lượng", "nghiệm thu", "thiết kế bản vẽ"],
        "manufacturing": ["vận hành", "bảo trì", "kiểm soát chất lượng", "đóng gói", "sản xuất"],
        
        # Nhóm Sáng tạo / Thiết kế / Media
        "design": ["thiết kế", "vẽ", "dựng hình", "phác thảo", "chỉnh sửa", "retouch"],
        "media_publishing": ["biên tập", "sản xuất", "dẫn chương trình", "thu âm", "lồng tiếng"],
        
        # Nhóm Dịch vụ / Nhà hàng / Khách sạn
        "hospitality": ["đón tiếp", "chuẩn bị", "phục vụ", "pha chế", "đặt phòng", "hướng dẫn"],
        "customer_service": ["tiếp nhận", "giải đáp", "xử lý khiếu nại", "trực tổng đài", "trải nghiệm khách hàng"]
    }
    
    valid_verbs = general_verbs + industry_verbs.get(industry, [])
    
    skill_confidence = {}
    for skill in skills:
        confidence = 0.5
        for sentence in sentences:
            if skill.lower() in sentence.lower():
                words = sentence.split()
                if len(words) > 5 and any(verb in sentence.lower() for verb in valid_verbs):
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
    industry = jd_data.get("industry") or "all"
    
    jd_required_skills = jd_data.get("required_skills", [])
    jd_preferred_skills = jd_data.get("preferred_skills", [])
    jd_min_yoe = jd_data.get("min_yoe", 0)
    jd_education = jd_data.get("education", {})
    jd_min_edu = jd_education.get("min_level", "Không yêu cầu")

    cv_raw_text = cv_data.get("raw_text", "")
    cv_skills_list = cv_data.get("skills", [])
    
    cv_skills = {get_normalized_skill(skill, industry) for skill in cv_skills_list}

    skill_confidence = verify_skill_context(cv_raw_text, cv_skills_list, industry=industry)

    normalized_skill_exp = {}
    for skill, years in cv_data.get("skill_experience", {}).items():
        norm = get_normalized_skill(skill, industry)
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

    score_weights = jd_data.get("score_weights") or {}
    WEIGHT_SKILL = score_weights.get("skills_weight", 0.40)
    WEIGHT_NLP = score_weights.get("nlp_weight", 0.30)
    WEIGHT_EXP = score_weights.get("experience_weight", 0.20)
    WEIGHT_EDU = score_weights.get("education_weight", 0.10)

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
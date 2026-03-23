import os
import io
import re
import csv
from typing import List, Dict

import pdfplumber
import docx

from fastapi import UploadFile, HTTPException
from fastapi.concurrency import run_in_threadpool

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

def analyze_cv_text(text: str) -> Dict:
    info = extract_basic_info(text)
    skills = extract_skills(text)
    skills = remove_duplicate_semantic(skills)
    yoe = extract_years_of_experience(text)

    return {
        **info,
        "skills": skills,
        "skill_count": len(skills),
        "years_of_experience": yoe
    }

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
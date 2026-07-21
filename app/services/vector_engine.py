import os
import re
import httpx
import numpy as np
from dotenv import load_dotenv

load_dotenv()
COLAB_API_URL = os.getenv("COLAB_API_URL")

def chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list:
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks

def compress_cv_data(raw_text: str, candidate_info: dict, extracted_skills: list) -> str:
    edu = candidate_info.get("education_level", "Không có thông tin học vấn")
    yoe = candidate_info.get("years_of_experience", 0)
    skills_str = ", ".join(extracted_skills) if extracted_skills else "Không có kỹ năng rõ ràng"
    
    clean_raw = (raw_text or "").replace("\n", " ")[:8000] 
    
    full_cv_context = (
        f"Thông tin tóm tắt: Trình độ {edu}, {yoe} năm kinh nghiệm. Kỹ năng: {skills_str}.\n"
        f"Chi tiết Hồ sơ:\n{clean_raw}"
    )
    return full_cv_context

def compress_jd_data(jd_data: dict) -> str:
    title = jd_data.get("title", "")
    industry = jd_data.get("industry", "Đa ngành")
    level = jd_data.get("job_level", "Nhân viên")
    yoe = jd_data.get("min_yoe", 0)
    
    education = jd_data.get("education") or {}
    edu = education.get("min_level", "Không yêu cầu")
    
    req_skills = [s.get("name") for s in jd_data.get("required_skills", []) if isinstance(s, dict) and s.get("name")]
    pref_skills = [s.get("name") for s in jd_data.get("preferred_skills", []) if isinstance(s, dict) and s.get("name")]
    
    all_skills = req_skills + pref_skills
    skills_str = ", ".join(all_skills) if all_skills else "Không yêu cầu kỹ năng cụ thể"
    
    desc = jd_data.get("description", "")
    reqs = jd_data.get("requirements", "")
    benefits = jd_data.get("benefits", "")
    
    full_jd_context = (
        f"Vị trí tuyển dụng: {title} ngành {industry}, cấp bậc {level}\n"
        f"Yêu cầu tối thiểu: Trình độ {edu}, tối thiểu {yoe} năm kinh nghiệm. Kỹ năng: {skills_str}.\n"
        f"Mô tả công việc:\n{desc}\n"
        f"Yêu cầu chi tiết:\n{reqs}\n"
        f"Quyền lợi:\n{benefits}"
    )
    return full_jd_context

async def get_embedding(text: str) -> list:
    if not COLAB_API_URL:
        print("CẢNH BÁO: Chưa cấu hình COLAB_API_URL trong file .env")
        return []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(COLAB_API_URL, json={"text": text}, timeout=30.0)
            
            if response.status_code == 200:
                return response.json().get("embedding", [])
            else:
                print(f"Lỗi từ Colab API: {response.text}")
                return []
                
    except httpx.RequestError as e:
        print(f"Lỗi kết nối đến Colab Microservice: {e}")
        return []

async def get_cv_embeddings(text: str) -> list:
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    valid_embeddings = []
    
    for chunk in chunks:
        emb = await get_embedding(chunk)
        if emb:
            valid_embeddings.append(emb)
            
    return valid_embeddings

def calculate_cosine_similarity(cv_vectors: list, jd_vector: list) -> float:
    if not cv_vectors or not jd_vector:
        return 0.0
        
    if isinstance(cv_vectors[0], (int, float)):
        cv_vectors = [cv_vectors]
        
    v2 = np.array(jd_vector).flatten()
    norm_v2 = np.linalg.norm(v2)
    
    if norm_v2 == 0:
        return 0.0
    
    max_score = 0.0
    for vec in cv_vectors:
        v1 = np.array(vec).flatten()
        if len(v1) == 0 or len(v1) != len(v2):
            continue
        
        norm_v1 = np.linalg.norm(v1)
        if norm_v1 == 0:
            continue
            
        similarity = np.dot(v1, v2) / (norm_v1 * norm_v2)
        max_score = max(max_score, float(similarity) * 100)
    
    return round(max_score, 2)

def get_top_contributing_sentences(cv_text: str, jd_text: str, top_k: int = 3) -> list:
    if not cv_text or not jd_text:
        return []
        
    clean_cv = re.sub(r'(?i)(©\s*topcv\.vn|topcv|https?://\S+|[\w\.-]+@[\w\.-]+)', '', cv_text)
    clean_cv = re.sub(r'[•●✓✔\uf0b7\uf0d8\u2022\-\*]', '.', clean_cv)
    
    sentences = re.split(r'(?<=[.!?])\s+|\n+', clean_cv)
    jd_words = set(re.findall(r'\w+', jd_text.lower()))
    
    seen = set()
    scored_sentences = []
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 30 or len(sentence) > 300:
            continue
            
        words = re.findall(r'\w+', sentence.lower())
        if len(words) < 8 or len(words) > 50:
            continue
            
        overlap = sum(1 for w in words if w in jd_words)
        
        if overlap >= 3 and sentence not in seen:
            seen.add(sentence)
            scored_sentences.append((overlap, sentence))
       
    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored_sentences[:top_k]]
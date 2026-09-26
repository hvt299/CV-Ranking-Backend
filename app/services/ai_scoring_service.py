import asyncio
from typing import Dict, Any, Tuple
from fastapi import UploadFile

from app.services.nlp_engine import extract_text, analyze_cv_text, score_cv
from app.services.vector_engine import compress_cv_data, get_cv_embeddings, get_top_contributing_sentences
from app.services.document_forensics import detect_hidden_text

class AIScoringService:
    
    @staticmethod
    async def process_uploaded_cv(file: UploadFile, content: bytes, filename: str) -> Tuple[str, Dict[str, Any], Any, list]:
        raw_text = await extract_text(file, content)
        
        def run_fraud_check():
            if filename.lower().endswith((".pdf", ".docx")):
                return detect_hidden_text(content, filename)
            return None
            
        fraud_result = await asyncio.to_thread(run_fraud_check)
        
        cv_data = await analyze_cv_text(raw_text)
        
        compressed_text = compress_cv_data(raw_text, cv_data, cv_data.get("skills", []))
        cv_vector = await get_cv_embeddings(compressed_text)
        
        return raw_text, cv_data, fraud_result, cv_vector

    @staticmethod
    def prepare_and_score_cv(cv_record: dict, jd_data: dict, jd_search_text: str) -> Tuple[Dict[str, Any], list]:
        raw_text = cv_record.get("raw_text", "")
        top_sentences = get_top_contributing_sentences(raw_text, jd_search_text)

        cv_data_for_scoring = {
            "raw_text": raw_text,
            "word_count": len((raw_text or "").split()),
            "skills": cv_record.get("extracted_skills", []),
            "years_of_experience": cv_record.get("candidate_info", {}).get("years_of_experience", 0),
            "skill_experience": cv_record.get("candidate_info", {}).get("skill_experience", {}),
            "education_level": cv_record.get("candidate_info", {}).get("education_level", "Không đề cập"),
            "job_hops": cv_record.get("candidate_info", {}).get("job_hops", 1),       
            "gap_months": cv_record.get("candidate_info", {}).get("gap_months", 0),   
            "cv_vector": cv_record.get("cv_vector_ref", []),
            "fraud_analysis": cv_record.get("candidate_info", {}).get("fraud_analysis", {}),
            "top_sentences": top_sentences
        }

        scoring_result = score_cv(cv_data_for_scoring, jd_data)
        
        return scoring_result, top_sentences
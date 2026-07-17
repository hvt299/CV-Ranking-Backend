import os
import json
import logging
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

async def extract_cv_metrics_with_llm(raw_text: str) -> dict:
    fallback_data = {
        "years_of_experience": 0.0,
        "education_level": "Không đề cập",
        "job_hops": 1,
        "gap_months": 0
    }

    if not GEMINI_API_KEY:
        logger.warning("Chưa cấu hình GEMINI_API_KEY. Bỏ qua LLM Extraction.")
        return fallback_data

    safe_text = (raw_text or "")[:8000]

    prompt = f"""
    Bạn là một chuyên gia Nhân sự (Headhunter) lão luyện. Hãy phân tích đoạn text CV dưới đây và trích xuất thông tin.
    
    Yêu cầu BẮT BUỘC: CHỈ TRẢ VỀ DUY NHẤT 1 CHUỖI JSON chuẩn (không có markdown ```json, không giải thích thêm).
    Định dạng JSON phải tuân thủ nghiêm ngặt:
    {{
        "years_of_experience": <float, tổng số năm làm việc thực tế, tính cả tháng lẻ. Chỉ tính các công việc chuyên môn. VD: 2.5. Nếu sinh viên mới ra trường trả 0.0>,
        "education_level": <string, chọn đúng 1 trong các mốc sau (chọn mốc cao nhất ứng viên có): "Không đề cập", "Chứng chỉ nghề", "Trung học phổ thông", "Trung cấp", "Cao đẳng", "Cử nhân", "Thạc sĩ", "Tiến sĩ">,
        "job_hops": <int, tổng số lượng công ty hoặc tổ chức khác nhau mà ứng viên đã từng làm việc. Mặc định là 1>,
        "gap_months": <int, tổng số tháng trống (không đi làm hoặc đi học) lớn nhất giữa các mốc thời gian làm việc. Mặc định là 0>
    }}

    Nội dung CV cần phân tích:
    {safe_text}
    """

    try:
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = await model.generate_content_async(prompt, generation_config=generation_config)
        
    except Exception as e:
        logger.warning(f"Gemini 2.5 Flash thất bại ({e}). Thử lại với 2.0 Flash...")
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            response = await model.generate_content_async(prompt, generation_config=generation_config)
        except Exception as e2:
            logger.error(f"Cả 2 model Gemini đều thất bại: {e2}")
            return fallback_data

    try:
        raw_output = response.text or "{}"
        
        first_brace = raw_output.find('{')
        last_brace = raw_output.rfind('}')
        
        if first_brace != -1 and last_brace != -1:
            clean_json = raw_output[first_brace:last_brace+1]
            data = json.loads(clean_json)
            
            return {
                "years_of_experience": float(data.get("years_of_experience", 0.0)),
                "education_level": str(data.get("education_level", "Không đề cập")),
                "job_hops": int(data.get("job_hops", 1)),
                "gap_months": int(data.get("gap_months", 0))
            }
        else:
            raise ValueError("Không tìm thấy cấu trúc JSON trong phản hồi của AI")
            
    except Exception as parse_error:
        logger.error(f"Lỗi parse JSON từ LLM: {parse_error}")
        return fallback_data
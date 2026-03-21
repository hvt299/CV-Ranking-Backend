import os
import io
import pdfplumber
import docx
from fastapi import FastAPI, UploadFile, File, HTTPException

app = FastAPI(
    title="CV Ranking System API",
    description="Backend AI phân tích và xếp hạng CV",
    version="1.0.0"
)

def extract_text_from_pdf(file_bytes: bytes) -> str:
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join([para.text for para in doc.paragraphs])

@app.get("/")
def read_root():
    return {"message": "Hello! Backend AI đang chạy rất mượt mà 🚀"}

@app.get("/ping")
def ping():
    return {"status": "Success", "data": "Hệ thống sẵn sàng nhận CV!"}

@app.post("/api/v1/cv/parse-text")
async def parse_cv_text(file: UploadFile = File(...)):
    if not file.filename.endswith(('.pdf', '.docx')):
        raise HTTPException(status_code=400, detail="Hệ thống chỉ hỗ trợ định dạng PDF hoặc DOCX")

    try:
        content = await file.read()
        text = ""

        if file.filename.endswith('.pdf'):
            text = extract_text_from_pdf(content)
        elif file.filename.endswith('.docx'):
            text = extract_text_from_docx(content)

        return {
            "filename": file.filename,
            "status": "success",
            "text_length": len(text),
            "content": text.strip()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi trong quá trình đọc file: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000))
    )
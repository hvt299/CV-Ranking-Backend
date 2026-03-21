import os
from fastapi import FastAPI

app = FastAPI(
    title="CV Ranking System API",
    description="Backend AI phân tích và xếp hạng CV",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {"message": "Hello! Backend AI đang chạy rất mượt mà 🚀"}

@app.get("/ping")
def ping():
    return {"status": "Success", "data": "Hệ thống sẵn sàng nhận CV!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000))
    )
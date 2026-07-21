from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.auth import get_current_user
from app.services.storage_service import upload_file_to_cloudinary

router = APIRouter(prefix="/api/v1/upload", tags=["Upload"])

MAX_FILE_SIZE = 5 * 1024 * 1024

@router.post("")
async def upload_general_file(
    file: UploadFile = File(..., description="File tải lên (PDF, JPG, PNG)"),
    current_user = Depends(get_current_user)
):
    content = await file.read()
    
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Dung lượng file vượt quá giới hạn 5MB")
    
    try:
        file_url = await upload_file_to_cloudinary(content, file.filename)
        
        return {"url": file_url, "message": "Tải file lên thành công"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
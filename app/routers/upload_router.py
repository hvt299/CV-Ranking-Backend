from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.core.security import get_current_user
from app.services.storage_service import upload_file_to_cloudinary
from app.schemas.common_schema import UserRole, CompanyStatus
from datetime import datetime, timezone
from app.repositories.company_repository import CompanyRepository

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

@router.post("/kyc-document")
async def upload_kyc_document(
    file: UploadFile = File(..., description="Ảnh/PDF giấy phép ĐKKD"),
    current_user = Depends(get_current_user)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới được upload hồ sơ doanh nghiệp")
        
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Dung lượng file vượt quá giới hạn 5MB")
        
    try:
        file_url = await upload_file_to_cloudinary(
            content, 
            filename=f"kyc_{current_user.company_id}_{file.filename}", 
            target_folder="kyc_documents"
        )
                
        await CompanyRepository.update(current_user.company_id, {
            "kyc_submitted_at": datetime.now(timezone.utc),
            "status": CompanyStatus.PENDING_VERIFICATION.value
        })
        
        return {
            "url": file_url, 
            "submitted_at": datetime.now(timezone.utc),
            "message": "Tải tài liệu định danh lên thành công. Hệ thống đang chờ Admin duyệt."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
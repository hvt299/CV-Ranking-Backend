from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body
import os

from app.core.security import CurrentUser, require_admin
from app.schemas.common_schema import UserRole, CompanyStatus, AuditAction
from app.schemas.company_schema import CompanyVerifyAction
from app.repositories.user_repository import UserRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.audit_repository import AuditRepository

from pydantic import BaseModel, Field, EmailStr
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])
BOOTSTRAP_SECRET = os.getenv("ADMIN_BOOTSTRAP_SECRET", "")
class BootstrapRequest(BaseModel):
    secret: str = Field(..., description="Mã bảo mật lấy từ biến môi trường")
    email: EmailStr = Field(..., description="Email của tài khoản cần thăng cấp Admin")

class UpdateRoleRequest(BaseModel):
    role: UserRole = Field(..., description="Phân quyền mới (admin, hr_owner, hr_member, applicant)")

@router.post("/bootstrap")
async def bootstrap_admin(payload: BootstrapRequest):
    if not BOOTSTRAP_SECRET:
        raise HTTPException(status_code=403, detail="Bootstrap đã bị tắt")
        
    if payload.secret != BOOTSTRAP_SECRET:
        raise HTTPException(status_code=403, detail="Secret không đúng")
        
    modified_count = await UserRepository.update_custom(
        {"email": payload.email}, 
        {"$set": {"role": UserRole.ADMIN.value}}
    )
    if modified_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
        
    return {"status": "success", "message": f"{payload.email} đã được set làm Admin"}

@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users():
    projection = {
        "hashed_password": 0, 
        "reset_password_token": 0, 
        "reset_password_expires": 0
    }
    users = await UserRepository.find_all({}, projection=projection, limit=500)
    
    result = []
    for u in users:
        u["id"] = str(u["_id"])
        del u["_id"]
        result.append(u)
        
    return result

@router.patch("/users/{user_id}/role", dependencies=[Depends(require_admin)])
async def update_user_role(user_id: str, payload: UpdateRoleRequest):
    modified_count = await UserRepository.update(user_id, {"role": payload.role.value})
    
    if modified_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        
    return {"status": "success", "message": f"Đã cập nhật role thành '{payload.role.value}'"}

@router.get("/companies", dependencies=[Depends(require_admin)])
async def list_companies(status: str = None):
    query = {}
    if status:
        query["status"] = status
        
    companies = await CompanyRepository.find_all(query, limit=500)
    
    result = []
    for c in companies:
        c["id"] = str(c["_id"])
        del c["_id"]
        result.append(c)
    return result

@router.patch("/companies/{company_id}/verify", dependencies=[Depends(require_admin)])
async def verify_company(
    company_id: str, 
    action: CompanyVerifyAction,
    current_admin: CurrentUser = Depends(require_admin)
):    
    new_status = CompanyStatus.VERIFIED.value if action.approve else CompanyStatus.REJECTED.value
    
    update_data = {
        "status": new_status,
        "verified_by_admin_id": current_admin.id,
        "verified_at": datetime.now(timezone.utc)
    }
    
    if not action.approve:
        update_data["rejection_reason"] = action.rejection_reason
        
    modified_count = await CompanyRepository.update(company_id, update_data)
    
    if modified_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty")

    audit_action = AuditAction.COMPANY_VERIFIED if action.approve else AuditAction.COMPANY_REJECTED
    note = f"Duyệt thành công" if action.approve else f"Từ chối: {action.rejection_reason}"
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=audit_action,
        target_type="company",
        target_id=company_id,
        note=note
    )
        
    return {"status": "success", "message": "Đã xử lý trạng thái công ty"}

@router.get("/audit-logs", dependencies=[Depends(require_admin)])
async def get_audit_logs():
    logs = await AuditRepository.find_all({}, limit=200)
    
    result = []
    for lg in logs:
        lg["id"] = str(lg["_id"])
        del lg["_id"]
        result.append(lg)
    return result

@router.patch("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def admin_update_company(company_id: str, update_data: dict = Body(...)):
    allowed_fields = ["name", "tax_code", "industry", "size", "website", "address", "license_file_url"]
    clean_data = {k: v for k, v in update_data.items() if k in allowed_fields}
    
    if not clean_data:
        return {"status": "success"}
        
    modified_count = await CompanyRepository.update(company_id, clean_data)
    if modified_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty")
        
    return {"status": "success", "message": "Cập nhật thành công"}
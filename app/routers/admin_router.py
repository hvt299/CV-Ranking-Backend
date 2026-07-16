from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body
from bson import ObjectId
import os
from typing import List

from app.auth import CurrentUser, require_admin
from app.database.config import get_db, Collections
from app.database.models import UserRole, CompanyVerifyAction, CompanyStatus, AuditAction
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
        
    db = get_db()
    result = await db[Collections.USERS].update_one(
        {"email": payload.email}, 
        {"$set": {"role": UserRole.ADMIN.value}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
        
    return {"status": "success", "message": f"{payload.email} đã được set làm Admin"}

@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users():
    db = get_db()
    projection = {
        "hashed_password": 0, 
        "reset_password_token": 0, 
        "reset_password_expires": 0
    }
    cursor = db[Collections.USERS].find({}, projection)
    users = await cursor.to_list(length=500)
    
    result = []
    for u in users:
        u["id"] = str(u["_id"])
        del u["_id"]
        result.append(u)
        
    return result

@router.patch("/users/{user_id}/role", dependencies=[Depends(require_admin)])
async def update_user_role(user_id: str, payload: UpdateRoleRequest): 
    db = get_db()
    result = await db[Collections.USERS].update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": payload.role.value}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        
    return {"status": "success", "message": f"Đã cập nhật role thành '{payload.role.value}'"}

@router.get("/companies", dependencies=[Depends(require_admin)])
async def list_companies(status: str = None):
    db = get_db()
    query = {}
    if status:
        query["status"] = status
        
    cursor = db[Collections.COMPANIES].find(query).sort("created_at", -1)
    companies = await cursor.to_list(length=500)
    
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
    db = get_db()
    
    new_status = CompanyStatus.VERIFIED.value if action.approve else CompanyStatus.REJECTED.value
    
    update_data = {
        "status": new_status,
        "verified_by_admin_id": current_admin.id,
        "verified_at": datetime.now(timezone.utc)
    }
    
    if not action.approve:
        update_data["rejection_reason"] = action.rejection_reason
        
    result = await db[Collections.COMPANIES].update_one(
        {"_id": ObjectId(company_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
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
    db = get_db()
    cursor = db[Collections.AUDIT_LOGS].find({}).sort("created_at", -1).limit(200)
    logs = await cursor.to_list(length=200)
    
    result = []
    for lg in logs:
        lg["id"] = str(lg["_id"])
        del lg["_id"]
        result.append(lg)
    return result

@router.patch("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def admin_update_company(company_id: str, update_data: dict = Body(...)):
    db = get_db()
    
    allowed_fields = ["name", "tax_code", "industry", "size", "website", "address", "license_file_url"]
    clean_data = {k: v for k, v in update_data.items() if k in allowed_fields}
    
    if not clean_data:
        return {"status": "success"}
        
    result = await db[Collections.COMPANIES].update_one(
        {"_id": ObjectId(company_id)},
        {"$set": clean_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty")
        
    return {"status": "success", "message": "Cập nhật thành công"}
import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from datetime import datetime, timedelta, timezone
from typing import List
from bson import ObjectId
import jwt

from app.database.config import get_db, Collections
from app.auth import CurrentUser, require_hr, require_hr_or_admin, JWT_SECRET, ALGORITHM
from app.database.models import CompanyStatus, UserRole
from app.services.email_service import send_hr_invite_email

router = APIRouter(prefix="/api/v1/companies", tags=["Company & HR Management"])

@router.get("/lookup-tax/{tax_code}")
async def lookup_tax_code(tax_code: str):
    url = f"https://api.vietqr.io/v2/business/{tax_code}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            data = response.json()
            
            if data.get("code") == "00" and data.get("data"):
                return {
                    "tax_code": data["data"]["id"],
                    "company_name": data["data"]["name"],
                    "address": data["data"]["address"],
                    "status": data["data"]["status"]
                }
            elif data.get("code") == "52":
                raise HTTPException(status_code=404, detail="Mã số thuế không chính xác hoặc không tồn tại")
            else:
                error_desc = data.get("desc", "Không tìm thấy thông tin từ Mã số thuế này")
                raise HTTPException(status_code=404, detail=error_desc)
                
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail="Lỗi kết nối đến cổng tra cứu doanh nghiệp")
    
@router.get("/members", dependencies=[Depends(require_hr)])
async def get_company_members(current_user: CurrentUser = Depends(require_hr)):
    db = get_db()
    cursor = db[Collections.USERS].find(
        {"company_id": current_user.company_id},
        {"hashed_password": 0, "reset_password_token": 0, "reset_password_expires": 0}
    )
    members = await cursor.to_list(length=100)
    
    result = []
    for m in members:
        m["id"] = str(m["_id"])
        del m["_id"]
        result.append(m)
    return result

@router.get("/settings", dependencies=[Depends(require_hr)])
async def get_company_settings(current_user: CurrentUser = Depends(require_hr)):
    db = get_db()
    company = await db[Collections.COMPANIES].find_one({"_id": ObjectId(current_user.company_id)})
    if not company:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu công ty")
    
    company["id"] = str(company["_id"])
    del company["_id"]
    return company

@router.patch("/settings", dependencies=[Depends(require_hr)])
async def update_company_settings(
    payload: dict = Body(...), 
    current_user: CurrentUser = Depends(require_hr)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới được phép cập nhật thông tin công ty")
        
    db = get_db()
    update_data = {
        "updated_at": datetime.now(timezone.utc)
    }
    
    allowed_fields = ["tax_code", "industry", "size", "website", "address", "license_file_url", "name"]
    for field in allowed_fields:
        if field in payload:
            update_data[field] = payload[field]
            
    if "tax_code" in payload or "license_file_url" in payload:
        update_data["status"] = CompanyStatus.PENDING_VERIFICATION.value
        
    await db[Collections.COMPANIES].update_one(
        {"_id": ObjectId(current_user.company_id)},
        {"$set": update_data}
    )
    return {"status": "success", "message": "Đã cập nhật thông tin công ty"}

@router.post("/invite", dependencies=[Depends(require_hr)])
async def invite_hr_member(
    background_tasks: BackgroundTasks,
    email: str = Body(..., embed=True), 
    current_user: CurrentUser = Depends(require_hr)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới có quyền mời thành viên")
        
    db = get_db()
    
    company = await db[Collections.COMPANIES].find_one({"_id": ObjectId(current_user.company_id)})
    user = await db[Collections.USERS].find_one({"_id": ObjectId(current_user.id)})
    
    existing_user = await db[Collections.USERS].find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email này đã có tài khoản trên hệ thống")
        
    invite_token = jwt.encode(
        {
            "email": email, 
            "company_id": current_user.company_id, 
            "role": UserRole.HR_MEMBER.value,
            "exp": datetime.now(timezone.utc) + timedelta(days=7)
        },
        JWT_SECRET, algorithm=ALGORITHM
    )
    
    send_hr_invite_email(
        background_tasks, 
        to=email, 
        inviter_name=user.get("full_name", "Quản lý"), 
        company_name=company.get("name", "Công ty"), 
        token=invite_token
    )
    
    return {"status": "success", "message": f"Đã gửi thư mời thành công đến {email}"}
from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from app.auth import get_current_user
from app.database.config import get_db
import os

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

VALID_ROLES = ("hr", "applicant", "admin")
BOOTSTRAP_SECRET = os.getenv("ADMIN_BOOTSTRAP_SECRET", "")

async def require_admin(current_user: str = Depends(get_current_user)):
    db = get_db()
    user = await db["hr_users"].find_one({"email": current_user})
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Chỉ Admin mới có quyền thực hiện thao tác này")
    return current_user

@router.post("/bootstrap")
async def bootstrap_admin(body: dict):
    """Dùng 1 lần để tạo admin đầu tiên. Cần ADMIN_BOOTSTRAP_SECRET trong .env"""
    if not BOOTSTRAP_SECRET:
        raise HTTPException(status_code=403, detail="Bootstrap đã bị tắt")
    if body.get("secret") != BOOTSTRAP_SECRET:
        raise HTTPException(status_code=403, detail="Secret không đúng")
    email = body.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Thiếu email")
    db = get_db()
    result = await db["hr_users"].update_one({"email": email}, {"$set": {"role": "admin"}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    return {"status": "success", "message": f"{email} đã được set làm Admin"}

@router.get("/users")
async def list_users(_: str = Depends(require_admin)):
    db = get_db()
    cursor = db["hr_users"].find({}, {"hashed_password": 0, "raw_text": 0})
    users = await cursor.to_list(length=500)
    for u in users:
        u["id"] = str(u["_id"])
        del u["_id"]
    return users

@router.patch("/users/{user_id}/role")
async def update_user_role(user_id: str, body: dict, _: str = Depends(require_admin)):
    new_role = body.get("role")
    if new_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role không hợp lệ. Chọn: {VALID_ROLES}")
    db = get_db()
    result = await db["hr_users"].update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return {"status": "success", "message": f"Đã cập nhật role thành '{new_role}'"}

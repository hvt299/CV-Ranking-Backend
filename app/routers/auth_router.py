from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Body, BackgroundTasks
from datetime import datetime, timezone, timedelta
import secrets
import hashlib
from fastapi.responses import JSONResponse
import jwt
from app.database.config import get_db
from app.database.models import HRUserCreate, HRUserLogin, Token
from app.auth import get_current_user, get_password_hash, verify_password, create_access_token, JWT_SECRET, ALGORITHM
from app.services.email_service import send_verification_email, send_reset_password_email
import urllib.parse
from bson import ObjectId
import os
from pydantic import BaseModel, Field
import httpx
from fastapi.security import OAuth2PasswordRequestForm

class ProfileUpdate(BaseModel):
    full_name: str
    phone: str = None
    address: str = None
    github: str = None
    linkedin: str = None
    bio: str = None
    avatar: str = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

@router.post("/register", status_code=201)
async def register_hr(background_tasks: BackgroundTasks, user: HRUserCreate = Body(...)):
    db = get_db()
    existing_user = await db["hr_users"].find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email này đã được đăng ký!")
        
    hashed_pw = get_password_hash(user.password)
    encoded_name = urllib.parse.quote(user.full_name)
    auto_avatar = f"https://ui-avatars.com/api/?name={encoded_name}&background=random&color=fff&size=200"
    
    new_user = {
        "email": user.email,
        "full_name": user.full_name,
        "hashed_password": hashed_pw,
        "avatar": auto_avatar,
        "original_avatar": auto_avatar,
        "role": user.role,
        "is_verified": False,
        "created_at": datetime.now(timezone.utc)
    }
    
    insert_result = await db["hr_users"].insert_one(new_user)
    
    verify_token = jwt.encode(
        {"sub": str(insert_result.inserted_id), "exp": datetime.now(timezone.utc) + timedelta(days=1)}, 
        JWT_SECRET, algorithm=ALGORITHM
    )
    
    send_verification_email(background_tasks, user.email, user.full_name, verify_token)
    
    return {"status": "success", "message": "Đăng ký thành công! Vui lòng kiểm tra email để kích hoạt tài khoản."}

@router.get("/verify")
async def verify_email(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        db = get_db()
        
        result = await db["hr_users"].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_verified": True}}
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="Tài khoản không tồn tại hoặc đã được xác thực.")
            
        return {"message": "Xác thực thành công! Tài khoản của bạn đã được kích hoạt."}
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Link xác thực không hợp lệ hoặc đã hết hạn.")

@router.post("/login", response_model=Token)
async def login_for_access_token(user_credentials: HRUserLogin = Body(...)):
    db = get_db()
    
    user = await db["hr_users"].find_one({"email": user_credentials.email})
    
    if not user or not verify_password(user_credentials.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không chính xác")
        
    if not user.get("is_verified", False):
        raise HTTPException(status_code=401, detail="Vui lòng kiểm tra email để kích hoạt tài khoản trước khi đăng nhập!")
    
    access_token = create_access_token(data={
        "sub": user["email"],
        "role": user.get("role", "applicant")
    })
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/forgot-password")
async def forgot_password(background_tasks: BackgroundTasks, email: str = Body(..., embed=True)):
    db = get_db()
    user = await db["hr_users"].find_one({"email": email})
    
    msg = "Nếu email tồn tại trên hệ thống, link khôi phục đã được gửi."
    if not user:
        return {"message": msg}
        
    reset_token = secrets.token_hex(32)
    hashed_token = hashlib.sha256(reset_token.encode()).hexdigest()
    
    await db["hr_users"].update_one(
        {"_id": user["_id"]},
        {"$set": {
            "reset_password_token": hashed_token,
            "reset_password_expires": datetime.now(timezone.utc) + timedelta(minutes=15)
        }}
    )
    
    send_reset_password_email(background_tasks, user["email"], user["full_name"], reset_token)
    return {"message": msg}

@router.post("/reset-password")
async def reset_password(token: str = Body(...), new_password: str = Body(...)):
    db = get_db()
    hashed_token = hashlib.sha256(token.encode()).hexdigest()
    
    user = await db["hr_users"].find_one({
        "reset_password_token": hashed_token,
        "reset_password_expires": {"$gt": datetime.now(timezone.utc)}
    })
    
    if not user:
        raise HTTPException(status_code=400, detail="Link khôi phục không hợp lệ hoặc đã hết hạn!")
        
    hashed_pw = get_password_hash(new_password)
    await db["hr_users"].update_one(
        {"_id": user["_id"]},
        {
            "$set": {"hashed_password": hashed_pw},
            "$unset": {"reset_password_token": "", "reset_password_expires": ""}
        }
    )
    
    return {"message": "Mật khẩu đã được đặt lại thành công! Bạn có thể đăng nhập."}

class GoogleAuthRequest(BaseModel):
    access_token: str
    role: Optional[str] = None

@router.post("/google")
async def google_login(request: GoogleAuthRequest = Body(...)):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={request.access_token}"
            )
            if response.status_code != 200:
                raise ValueError("Token không hợp lệ")
            idinfo = response.json()
        
        email = idinfo['email']
        full_name = idinfo.get('name', 'Người dùng Google')
        picture = idinfo.get('picture', '')
        
        db = get_db()
        user = await db["hr_users"].find_one({"email": email})
        
        if not user:
            if not request.role:
                return JSONResponse(
                    status_code=202, 
                    content={
                        "action": "require_role", 
                        "message": "Vui lòng chọn vai trò để hoàn tất",
                        "email": email
                    }
                )
            
            random_pw = secrets.token_urlsafe(32)
            hashed_pw = get_password_hash(random_pw)
            encoded_name = urllib.parse.quote(full_name)
            fallback_avatar = f"https://ui-avatars.com/api/?name={encoded_name}&background=random&color=fff&size=200"
            final_avatar = picture if picture else fallback_avatar
            
            new_user = {
                "email": email,
                "full_name": full_name,
                "hashed_password": hashed_pw,
                "avatar": final_avatar,
                "original_avatar": final_avatar,
                "role": request.role,
                "is_verified": True, 
                "created_at": datetime.now(timezone.utc)
            }
            await db["hr_users"].insert_one(new_user)
            
        else:
            update_fields = {}
            if not user.get("is_verified", False):
                update_fields["is_verified"] = True
            
            current_avatar = user.get("avatar", "")
            if picture and "ui-avatars.com" in current_avatar:
                update_fields["avatar"] = picture
                update_fields["original_avatar"] = picture
                
            if update_fields:
                await db["hr_users"].update_one({"email": email}, {"$set": update_fields})
                
        access_token = create_access_token(data={
            "sub": email,
            "role": user.get("role") if user else request.role
        })
        return {"access_token": access_token, "token_type": "bearer"}
        
    except ValueError:
        raise HTTPException(status_code=401, detail="Token từ Google không hợp lệ hoặc đã hết hạn")
    
@router.get("/profile")
async def get_profile(email: str = Depends(get_current_user)):
    """Lấy thông tin profile đầy đủ của user"""
    db = get_db()
    user = await db["hr_users"].find_one({"email": email})
    
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin người dùng")
        
    return {
        "email": user["email"],
        "full_name": user.get("full_name", ""),
        "phone": user.get("phone", ""),
        "address": user.get("address", ""),
        "github": user.get("github", ""),
        "linkedin": user.get("linkedin", ""),
        "bio": user.get("bio", ""),
        "avatar": user.get("avatar", ""),
        "role": user.get("role", "hr")
    }

@router.patch("/profile")
async def update_profile(profile_data: ProfileUpdate, email: str = Depends(get_current_user)):
    db = get_db()
    
    update_data = {
        "full_name": profile_data.full_name,
        "phone": profile_data.phone,
        "address": profile_data.address,
        "github": profile_data.github,
        "linkedin": profile_data.linkedin,
        "bio": profile_data.bio,
        "avatar": profile_data.avatar,
        "updated_at": datetime.now(timezone.utc)
    }
    
    update_data = {k: v for k, v in update_data.items() if v is not None}
    
    result = await db["hr_users"].update_one(
        {"email": email},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        
    return {"status": "success", "message": "Cập nhật thông tin thành công"}

@router.patch("/change-password")
async def change_password(password_data: PasswordChange, email: str = Depends(get_current_user)):
    db = get_db()
    
    user = await db["hr_users"].find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    
    if not verify_password(password_data.current_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")
    
    new_hashed_password = get_password_hash(password_data.new_password)
    
    result = await db["hr_users"].update_one(
        {"email": email},
        {"$set": {
            "hashed_password": new_hashed_password,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        
    return {"status": "success", "message": "Đổi mật khẩu thành công"}

@router.get("/me")
async def get_current_user_profile(email: str = Depends(get_current_user)):
    db = get_db()
    user = await db["hr_users"].find_one({"email": email})
    
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin người dùng")
    
    role = user.get("role", "applicant")
    
    if "role" not in user:
        await db["hr_users"].update_one(
            {"email": email},
            {"$set": {"role": "applicant"}}
        )
        
    return {
        "email": user["email"],
        "full_name": user.get("full_name", "User"),
        "avatar": user.get("avatar", ""),
        "role": role
    }

@router.post("/docs-login", response_model=Token, include_in_schema=False)
async def swagger_login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = get_db()
    
    user = await db["hr_users"].find_one({"email": form_data.username})
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không chính xác")
        
    if not user.get("is_verified", False):
        raise HTTPException(status_code=401, detail="Vui lòng kiểm tra email để kích hoạt tài khoản!")
    
    access_token = create_access_token(data={
        "sub": user["email"],
        "role": user.get("role", "applicant")
    })
    return {"access_token": access_token, "token_type": "bearer"}
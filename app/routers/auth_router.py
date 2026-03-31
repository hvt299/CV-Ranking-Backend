from fastapi import APIRouter, Depends, HTTPException, status, Body, BackgroundTasks
from datetime import datetime, timezone, timedelta
import secrets
import hashlib
import jwt
from app.database.config import get_db
from app.database.models import HRUserCreate, HRUserLogin, Token
from app.auth import get_current_user, get_password_hash, verify_password, create_access_token, JWT_SECRET, ALGORITHM
from app.services.email_service import send_verification_email, send_reset_password_email
import urllib.parse
from bson import ObjectId
import os
from pydantic import BaseModel
import httpx

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
    
    access_token = create_access_token(data={"sub": user["email"]})
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

@router.post("/google", response_model=Token)
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
                await db["hr_users"].update_one(
                    {"email": email}, 
                    {"$set": update_fields}
                )
            
        access_token = create_access_token(data={"sub": email})
        return {"access_token": access_token, "token_type": "bearer"}
        
    except ValueError:
        raise HTTPException(status_code=401, detail="Token từ Google không hợp lệ hoặc đã hết hạn")
    
@router.get("/me")
async def get_current_user_profile(email: str = Depends(get_current_user)):
    db = get_db()
    user = await db["hr_users"].find_one({"email": email})
    
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin người dùng")
        
    return {
        "email": user["email"],
        "full_name": user.get("full_name", "HR Manager"),
        "avatar": user.get("avatar", "")
    }
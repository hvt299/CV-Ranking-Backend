from fastapi import APIRouter, Depends, HTTPException, status, Body
from datetime import datetime, timezone
from app.database.config import get_db
from app.database.models import HRUserCreate, HRUserLogin, Token
from app.auth import get_password_hash, verify_password, create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

@router.post("/register", status_code=201)
async def register_hr(user: HRUserCreate = Body(...)):
    db = get_db()
    existing_user = await db["hr_users"].find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email này đã được đăng ký!")
        
    hashed_pw = get_password_hash(user.password)
    new_user = {
        "email": user.email,
        "hashed_password": hashed_pw,
        "created_at": datetime.now(timezone.utc)
    }
    await db["hr_users"].insert_one(new_user)
    return {"status": "success", "message": "Tạo tài khoản HR thành công"}

@router.post("/login", response_model=Token)
async def login_for_access_token(user_credentials: HRUserLogin = Body(...)):
    db = get_db()
    
    user = await db["hr_users"].find_one({"email": user_credentials.email})
    
    if not user or not verify_password(user_credentials.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác",
        )
    
    access_token = create_access_token(data={"sub": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}

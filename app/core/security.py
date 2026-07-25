import hashlib
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.schemas.common_schema import UserRole
from app.repositories.user_repository import UserRepository

JWT_SECRET = os.getenv("JWT_SECRET", "CVRanking@JWT")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", 1440))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/docs-login")

class CurrentUser(BaseModel):
    id: str
    email: EmailStr
    role: UserRole
    company_id: Optional[str] = None
    department_id: Optional[str] = None

def verify_password(plain_password: str, hashed_password: str):
    pre_hashed_password = hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.verify(pre_hashed_password, hashed_password)

def get_password_hash(password: str):
    pre_hashed_password = hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed_password)

def build_token_payload(user: dict) -> dict:
    return {
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user.get("role", UserRole.APPLICANT.value),
        "company_id": user.get("company_id"),
    }

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire.timestamp()})

    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực thông tin (Token không hợp lệ, đã hết hạn hoặc tài khoản bị khóa)",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = await UserRepository.get_by_id(user_id)
    
    if not user or user.get("deleted_at") is not None:
        raise credentials_exception
        
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản của bạn đã bị khóa."
        )

    return CurrentUser(
        id=str(user["_id"]),
        email=user["email"],
        role=UserRole(user.get("role", UserRole.APPLICANT.value)),
        company_id=user.get("company_id"),
        department_id=user.get("department_id")
    )

async def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Truy cập bị từ chối: Yêu cầu đặc quyền Quản trị viên (Admin)."
        )
    return current_user

async def require_hr(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role not in [UserRole.HR_OWNER, UserRole.HR_MEMBER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Truy cập bị từ chối: Yêu cầu đặc quyền Nhân sự (HR)."
        )
    return current_user

async def require_hr_or_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role not in [UserRole.HR_OWNER, UserRole.HR_MEMBER, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Truy cập bị từ chối: Yêu cầu đặc quyền Nhân sự (HR) hoặc Admin."
        )
    return current_user

async def get_scope_filter(current_user: CurrentUser = Depends(get_current_user)) -> Dict[str, Any]:
    if current_user.role == UserRole.ADMIN:
        return {}
        
    elif current_user.role == UserRole.HR_OWNER:
        if not current_user.company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tài khoản HR Owner chưa được gắn với công ty nào."
            )
        return {"company_id": current_user.company_id}
        
    elif current_user.role == UserRole.HR_MEMBER:
        if not current_user.company_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tài khoản HR Member chưa được gắn với công ty nào."
            )
        scope = {"company_id": current_user.company_id}
        
        if getattr(current_user, "department_id", None):
            scope["department_id"] = current_user.department_id
            
        return scope
        
    elif current_user.role == UserRole.APPLICANT:
        return {"applicant_user_id": current_user.id}
        
    return {"_id": None}

get_current_user_with_role = get_current_user
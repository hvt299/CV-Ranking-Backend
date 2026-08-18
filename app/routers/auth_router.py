from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Request, Response
from datetime import datetime, timezone, timedelta
from app.middleware.rate_limit import limiter
import secrets
import hashlib
from fastapi.responses import JSONResponse
import jwt

from app.schemas.common_schema import UserRole, CompanyStatus, JobStatus, utc_now, AuditAction, ApplicationSource
from app.schemas.user_schema import UserCreate
from app.schemas.auth_schema import UserLogin, Token
from app.schemas.company_schema import CompanyCreate
from app.schemas.shared_schema import LocationDetail
from app.repositories.user_repository import UserRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.job_repository import JobRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.applicant_profile_repository import ApplicantProfileRepository
from app.repositories.cv_repository import CVRepository
from app.repositories.application_repository import ApplicationRepository
from app.services.audit_service import log_action

from app.core.security import (
    CurrentUser,
    get_current_user,
    get_password_hash,
    verify_password,
    create_access_token,
    build_token_payload,
    JWT_SECRET,
    ALGORITHM,
)
from app.services.email_service import send_verification_email, send_reset_password_email
import urllib.parse
from bson import ObjectId
import os
from pydantic import BaseModel, Field, field_validator
import httpx
from fastapi.security import OAuth2PasswordRequestForm
import re
import time

# ---------------------------------------------------------------------
# DTO đặc thù cho router này (không phải entity lưu DB nên KHÔNG đặt
# trong models.py — quy ước: models.py chỉ chứa model ánh xạ collection).
# ---------------------------------------------------------------------

class RegisterRequest(UserCreate):
    company_name: Optional[str] = Field(
        default=None,
        description="Bắt buộc nếu role=hr_owner — server dùng để tạo company mới.",
    )
    tax_code: Optional[str] = Field(
        default=None,
        description="Mã số thuế, bắt buộc nếu role=hr_owner"
    )
    industry: Optional[str] = Field(default=None)
    size: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)
    website: Optional[str] = Field(default=None)
    invite_token: Optional[str] = Field(default=None, description="Token từ email mời")

class ExternalCVLinkDTO(BaseModel):
    provider: str
    url: str
    is_primary: bool = False

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    job_title_internal: Optional[str] = None
    extension_phone: Optional[str] = None
    current_location: Optional[LocationDetail] = None
    linkedin: Optional[str] = None
    portfolio: Optional[list] = None
    industry_specific_data: Optional[dict] = None
    external_cv_links: Optional[list[ExternalCVLinkDTO]] = None
    is_searchable: Optional[bool] = None
    
    headline: Optional[str] = None
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    
    headline: Optional[str] = None
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    def validate_password(cls, v):
        return validate_strong_password(v)

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    def validate_password(cls, v):
        return validate_strong_password(v)

class SocialAuthRequest(BaseModel):
    access_token: Optional[str] = Field(
        default=None, description="Dùng cho Google — access_token thật lấy từ @react-oauth/google."
    )
    code: Optional[str] = Field(
        default=None, description="Dùng cho LinkedIn — authorization code, backend sẽ tự exchange lấy access_token."
    )
    redirect_uri: Optional[str] = Field(
        default=None, description="Bắt buộc kèm theo 'code' của LinkedIn — phải khớp redirect_uri lúc xin code."
    )
    role: Optional[UserRole] = None
    company_name: Optional[str] = Field(
        default=None, description="Bắt buộc nếu role=hr_owner và là user mới qua Google/LinkedIn."
    )
    tax_code: Optional[str] = Field(default=None)
    industry: Optional[str] = Field(default=None)
    size: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)
    website: Optional[str] = Field(default=None)
    invite_token: Optional[str] = Field(default=None, description="Token từ email mời")

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

SELF_REGISTERABLE_ROLES = (UserRole.APPLICANT, UserRole.HR_OWNER)

def validate_strong_password(v: str) -> str:
    pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#+\-_=])[A-Za-z\d@$!%*?&#+\-_=]{8,}$"
    if not re.match(pattern, v):
        raise ValueError("Mật khẩu phải từ 8 ký tự, gồm ít nhất 1 chữ hoa, 1 chữ thường, 1 số và 1 ký tự đặc biệt.")
    return v

def _make_avatar_url(full_name: str) -> str:
    encoded_name = urllib.parse.quote(full_name)
    return f"https://ui-avatars.com/api/?name={encoded_name}&background=random&color=fff&size=200"

async def _create_company(req_data: BaseModel) -> str:
    company_doc = CompanyCreate(
        name=req_data.company_name, 
        tax_code=req_data.tax_code,
        industry=getattr(req_data, 'industry', None),
        size=getattr(req_data, 'size', None),
        address=getattr(req_data, 'address', None),
        website=getattr(req_data, 'website', None)
    ).model_dump()
    
    company_doc["status"] = CompanyStatus.PENDING_VERIFICATION.value
    company_doc["created_at"] = datetime.now(timezone.utc)
    
    return await CompanyRepository.create(company_doc)

# =====================================================================
# ĐĂNG KÝ / XÁC THỰC EMAIL
# =====================================================================

@router.post("/register", status_code=201)
@limiter.limit("10/day")
async def register_user(request: Request, response: Response, background_tasks: BackgroundTasks, payload: RegisterRequest = Body(...)):
    if payload.invite_token:
        try:
            token_data = jwt.decode(payload.invite_token, JWT_SECRET, algorithms=[ALGORITHM])
            if token_data.get("email") != payload.email:
                raise HTTPException(status_code=400, detail="Email đăng ký không khớp với email được mời!")
            
            existing_user = await UserRepository.get_by_email(payload.email)
            if existing_user:
                raise HTTPException(status_code=400, detail="Email này đã được đăng ký trên hệ thống!")
                
            hashed_pw = get_password_hash(payload.password)
            auto_avatar = _make_avatar_url(payload.full_name)
            
            new_user = {
                "email": payload.email,
                "full_name": payload.full_name,
                "hashed_password": hashed_pw,
                "avatar_url": auto_avatar,
                "original_avatar_url": auto_avatar,
                "role": token_data.get("role", UserRole.HR_MEMBER.value),
                "company_id": token_data.get("company_id"),
                "is_verified": True,
                "created_at": datetime.now(timezone.utc),
            }
            user_id = await UserRepository.create(new_user)
            
            if token_data.get("role") == UserRole.APPLICANT.value:
                await ApplicantProfileRepository.create({
                    "user_id": str(user_id),
                    "created_at": datetime.now(timezone.utc),
                    "deleted_at": None
                })
                
            return {"status": "success", "message": "Gia nhập công ty thành công! Bạn có thể đăng nhập ngay."}
        except jwt.PyJWTError:
            raise HTTPException(status_code=400, detail="Link mời không hợp lệ hoặc đã hết hạn.")

    if payload.role not in SELF_REGISTERABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Chỉ có thể tự đăng ký với vai trò 'applicant' hoặc 'hr_owner'. "
                   "Vai trò 'hr_member' cần được mời bởi hr_owner của công ty.",
        )

    existing_user = await UserRepository.get_by_email(payload.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email này đã được đăng ký!")

    company_id = None
    if payload.role == UserRole.HR_OWNER:
        if not payload.company_name or not payload.tax_code:
            raise HTTPException(
                status_code=400,
                detail="company_name và tax_code là bắt buộc khi đăng ký với vai trò hr_owner.",
            )
        company_id = await _create_company(payload)

    hashed_pw = get_password_hash(payload.password)
    auto_avatar = _make_avatar_url(payload.full_name)

    new_user = {
        "email": payload.email,
        "full_name": payload.full_name,
        "hashed_password": hashed_pw,
        "avatar_url": auto_avatar,
        "original_avatar_url": auto_avatar,
        "role": payload.role.value,
        "company_id": company_id,
        "is_verified": False,
        "created_at": datetime.now(timezone.utc),
    }

    user_id = await UserRepository.create(new_user)
    
    if payload.role == UserRole.APPLICANT:
        await ApplicantProfileRepository.create({
            "user_id": str(user_id),
            "created_at": datetime.now(timezone.utc),
            "deleted_at": None
        })

    verify_token = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        JWT_SECRET, algorithm=ALGORITHM
    )

    send_verification_email(background_tasks, payload.email, payload.full_name, verify_token)

    return {"status": "success", "message": "Đăng ký thành công! Vui lòng kiểm tra email để kích hoạt tài khoản."}

@router.get("/verify")
async def verify_email(token: str, background_tasks: BackgroundTasks):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        
        modified_count = await UserRepository.update(user_id, {"is_verified": True})
        if modified_count == 0:
            raise HTTPException(status_code=400, detail="Tài khoản không tồn tại hoặc đã được xác thực.")

        user = await UserRepository.get_by_id(user_id)
        if user and user.get("role") == UserRole.APPLICANT.value:
            background_tasks.add_task(merge_ghost_profiles, user_id, user.get("email"))

        return {"message": "Xác thực thành công! Tài khoản của bạn đã được kích hoạt."}
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Link xác thực không hợp lệ hoặc đã hết hạn.")

# =====================================================================
# ĐĂNG NHẬP
# =====================================================================

@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login_for_access_token(request: Request, response: Response, user_credentials: UserLogin = Body(...)):
    user = await UserRepository.get_by_email(user_credentials.email)

    if not user or not verify_password(user_credentials.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không chính xác")

    if not user.get("is_verified", False):
        raise HTTPException(status_code=401, detail="Vui lòng kiểm tra email để kích hoạt tài khoản trước khi đăng nhập!")

    access_token = create_access_token(build_token_payload(user))
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/forgot-password")
async def forgot_password(background_tasks: BackgroundTasks, email: str = Body(..., embed=True)):
    user = await UserRepository.get_by_email(email)

    msg = "Nếu email tồn tại trên hệ thống, link khôi phục đã được gửi."
    if not user:
        return {"message": msg}

    reset_token = secrets.token_hex(32)
    hashed_token = hashlib.sha256(reset_token.encode()).hexdigest()

    await UserRepository.update(str(user["_id"]), {
        "reset_password_token": hashed_token,
        "reset_password_expires": datetime.now(timezone.utc) + timedelta(minutes=15)
    })

    send_reset_password_email(background_tasks, user["email"], user["full_name"], reset_token)
    return {"message": msg}

@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    hashed_token = hashlib.sha256(payload.token.encode()).hexdigest()
    
    user = await UserRepository.find_one({"reset_password_token": hashed_token, "reset_password_expires": {"$gt": datetime.now(timezone.utc)}})
    
    if not user:
        raise HTTPException(status_code=400, detail="Link khôi phục không hợp lệ hoặc đã hết hạn!")

    hashed_pw = get_password_hash(payload.new_password)
    await UserRepository.update_custom(
        {"_id": user["_id"]},
        {"$set": {"hashed_password": hashed_pw}, "$unset": {"reset_password_token": "", "reset_password_expires": ""}}
    )

    return {"message": "Mật khẩu đã được đặt lại thành công! Bạn có thể đăng nhập."}

# =====================================================================
# GOOGLE OAUTH
# =====================================================================

@router.post("/google")
@limiter.limit("10/minute")
async def google_login(request: Request, response: Response, background_tasks: BackgroundTasks, social_request: SocialAuthRequest = Body(...)):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={social_request.access_token}"
            )
            if response.status_code != 200:
                raise ValueError("Token không hợp lệ")
            idinfo = response.json()

        email = idinfo['email']
        full_name = idinfo.get('name', 'Người dùng Google')
        picture = idinfo.get('picture', '')

        user = await UserRepository.get_by_email(email)

        if not user:
            company_id = None
            assigned_role = social_request.role

            if social_request.invite_token:
                try:
                    token_data = jwt.decode(social_request.invite_token, JWT_SECRET, algorithms=[ALGORITHM])
                    if token_data.get("email") != email:
                        raise HTTPException(status_code=400, detail="Email từ Google không khớp với email được mời!")
                    assigned_role = token_data.get("role", UserRole.HR_MEMBER.value)
                    company_id = token_data.get("company_id")
                except jwt.PyJWTError:
                    raise HTTPException(status_code=400, detail="Link mời không hợp lệ hoặc đã hết hạn.")
            else:
                if not assigned_role:
                    return JSONResponse(
                        status_code=202,
                        content={
                            "action": "require_role",
                            "message": "Vui lòng chọn vai trò để hoàn tất",
                            "email": email
                        }
                    )

                if assigned_role not in SELF_REGISTERABLE_ROLES:
                    raise HTTPException(
                        status_code=400,
                        detail="Chỉ có thể đăng ký với vai trò 'applicant' hoặc 'hr_owner' qua Google.",
                    )

                if assigned_role == UserRole.HR_OWNER:
                    if not social_request.company_name or not social_request.tax_code:
                        raise HTTPException(
                            status_code=400,
                            detail="company_name và tax_code là bắt buộc khi đăng ký với vai trò hr_owner.",
                        )
                    company_id = await _create_company(social_request)

            random_pw = secrets.token_urlsafe(32)
            hashed_pw = get_password_hash(random_pw)
            final_avatar = picture if picture else _make_avatar_url(full_name)
            
            role_val = assigned_role.value if hasattr(assigned_role, 'value') else assigned_role

            new_user = {
                "email": email,
                "full_name": full_name,
                "hashed_password": hashed_pw,
                "avatar_url": final_avatar,
                "original_avatar_url": final_avatar,
                "role": role_val,
                "company_id": company_id,
                "is_verified": True,
                "created_at": datetime.now(timezone.utc)
            }
            user_id = await UserRepository.create(new_user)
            
            if role_val == UserRole.APPLICANT.value or role_val == UserRole.APPLICANT:
                await ApplicantProfileRepository.create({
                    "user_id": str(user_id),
                    "created_at": datetime.now(timezone.utc),
                    "deleted_at": None
                })
                
            user = await UserRepository.get_by_id(user_id)

        else:
            update_fields = {}
            
            if social_request.invite_token:
                try:
                    token_data = jwt.decode(social_request.invite_token, JWT_SECRET, algorithms=[ALGORITHM])
                    if token_data.get("email") == email:
                        update_fields["role"] = token_data.get("role", UserRole.HR_MEMBER.value)
                        update_fields["company_id"] = token_data.get("company_id")
                except jwt.PyJWTError:
                    pass

            if not user.get("is_verified", False):
                update_fields["is_verified"] = True

            current_avatar = user.get("avatar_url", "")
            if picture and "ui-avatars.com" in current_avatar:
                update_fields["avatar_url"] = picture
                update_fields["original_avatar_url"] = picture

            if update_fields:
                update_fields["updated_at"] = datetime.now(timezone.utc)
                await UserRepository.update(str(user["_id"]), update_fields)
                user.update(update_fields)

        if user.get("role") == UserRole.APPLICANT.value or user.get("role") == UserRole.APPLICANT:
             background_tasks.add_task(merge_ghost_profiles, str(user["_id"]), user.get("email"))

        access_token_jwt = create_access_token(build_token_payload(user))
        return {"access_token": access_token_jwt, "token_type": "bearer"}

    except ValueError:
        raise HTTPException(status_code=401, detail="Token từ Google không hợp lệ hoặc đã hết hạn")

# =====================================================================
# LINKEDIN OAUTH
# =====================================================================

LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")


async def _exchange_linkedin_code(code: str, redirect_uri: str) -> str:
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": LINKEDIN_CLIENT_ID,
                "client_secret": LINKEDIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_res.status_code != 200:
        raise ValueError(f"Không thể đổi mã LinkedIn lấy access_token: {token_res.text}")

    token_data = token_res.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("Phản hồi từ LinkedIn không chứa access_token")

    return access_token

@router.post("/linkedin")
@limiter.limit("10/minute")
async def linkedin_login(request: Request, response: Response, background_tasks: BackgroundTasks, social_request: SocialAuthRequest = Body(...)):
    try:
        if not social_request.code or not social_request.redirect_uri:
            raise HTTPException(
                status_code=400,
                detail="Thiếu 'code' hoặc 'redirect_uri' để xác thực LinkedIn.",
            )

        access_token = await _exchange_linkedin_code(
            social_request.code, social_request.redirect_uri
        )

        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if res.status_code != 200:
                raise ValueError("Token LinkedIn không hợp lệ")
            idinfo = res.json()

        email = idinfo.get('email')
        full_name = idinfo.get('name', 'Người dùng LinkedIn')
        picture = idinfo.get('picture', '')

        user = await UserRepository.get_by_email(email)

        if not user:
            company_id = None
            assigned_role = social_request.role

            if social_request.invite_token:
                try:
                    token_data = jwt.decode(social_request.invite_token, JWT_SECRET, algorithms=[ALGORITHM])
                    if token_data.get("email") != email:
                        raise HTTPException(status_code=400, detail="Email từ LinkedIn không khớp với email được mời!")
                    assigned_role = token_data.get("role", UserRole.HR_MEMBER.value)
                    company_id = token_data.get("company_id")
                except jwt.PyJWTError:
                    raise HTTPException(status_code=400, detail="Link mời không hợp lệ hoặc đã hết hạn.")
            else:
                if not assigned_role:
                    return JSONResponse(
                        status_code=202,
                        content={
                            "action": "require_role",
                            "message": "Vui lòng chọn vai trò để hoàn tất",
                            "email": email
                        }
                    )

                if assigned_role not in SELF_REGISTERABLE_ROLES:
                    raise HTTPException(
                        status_code=400,
                        detail="Chỉ có thể đăng ký với vai trò 'applicant' hoặc 'hr_owner' qua LinkedIn.",
                    )

                if assigned_role == UserRole.HR_OWNER:
                    if not social_request.company_name or not social_request.tax_code:
                        raise HTTPException(
                            status_code=400,
                            detail="company_name và tax_code là bắt buộc khi đăng ký với vai trò hr_owner.",
                        )
                    company_id = await _create_company(social_request)

            random_pw = secrets.token_urlsafe(32)
            hashed_pw = get_password_hash(random_pw)
            final_avatar = picture if picture else _make_avatar_url(full_name)
            
            role_val = assigned_role.value if hasattr(assigned_role, 'value') else assigned_role

            new_user = {
                "email": email,
                "full_name": full_name,
                "hashed_password": hashed_pw,
                "avatar_url": final_avatar,
                "original_avatar_url": final_avatar,
                "role": role_val,
                "company_id": company_id,
                "is_verified": True,
                "created_at": datetime.now(timezone.utc)
            }
            user_id = await UserRepository.create(new_user)
            
            if role_val == UserRole.APPLICANT.value or role_val == UserRole.APPLICANT:
                await ApplicantProfileRepository.create({
                    "user_id": str(user_id),
                    "created_at": datetime.now(timezone.utc),
                    "deleted_at": None
                })
                
            user = await UserRepository.get_by_id(user_id)

        else:
            update_fields = {}
            if social_request.invite_token:
                try:
                    token_data = jwt.decode(social_request.invite_token, JWT_SECRET, algorithms=[ALGORITHM])
                    if token_data.get("email") == email:
                        update_fields["role"] = token_data.get("role", UserRole.HR_MEMBER.value)
                        update_fields["company_id"] = token_data.get("company_id")
                except jwt.PyJWTError:
                    pass

            if not user.get("is_verified", False):
                update_fields["is_verified"] = True

            current_avatar = user.get("avatar_url", "")
            if picture and "ui-avatars.com" in current_avatar:
                update_fields["avatar_url"] = picture
                update_fields["original_avatar_url"] = picture

            if update_fields:
                update_fields["updated_at"] = datetime.now(timezone.utc)
                await UserRepository.update(str(user["_id"]), update_fields)
                user.update(update_fields)

        if user.get("role") == UserRole.APPLICANT.value or user.get("role") == UserRole.APPLICANT:
             background_tasks.add_task(merge_ghost_profiles, str(user["_id"]), user.get("email"))

        access_token_jwt = create_access_token(build_token_payload(user))
        return {"access_token": access_token_jwt, "token_type": "bearer"}

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e) or "Token từ LinkedIn không hợp lệ hoặc đã hết hạn")
    
# =====================================================================
# PROFILE
# =====================================================================

@router.get("/profile")
async def get_profile(current_user: CurrentUser = Depends(get_current_user)):
    user = await UserRepository.get_by_id(current_user.id)

    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin người dùng")

    profile = {}
    if user.get("role") == UserRole.APPLICANT.value:
        profile = await ApplicantProfileRepository.get_by_user_id(current_user.id) or {}

    return {
        "id": current_user.id,
        "email": user["email"],
        "full_name": user.get("full_name", ""),
        "phone": user.get("phone", ""),
        "bio": user.get("bio", ""),
        "job_title_internal": user.get("job_title_internal", ""),
        "extension_phone": user.get("extension_phone", ""),
        "current_location": profile.get("current_location", {}),
        "github": profile.get("github", ""),
        "linkedin": profile.get("linkedin", ""),
        "headline": profile.get("headline", ""),
        "expected_salary_min": profile.get("expected_salary_min"),
        "expected_salary_max": profile.get("expected_salary_max"),
        "avatar_url": user.get("avatar_url", ""),
        "role": user.get("role"),
        "company_id": user.get("company_id"),
    }

@router.patch("/profile")
async def update_profile(profile_data: ProfileUpdate, current_user: CurrentUser = Depends(get_current_user)):
    user = await UserRepository.get_by_id(current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    user_update = {}
    for field in ("full_name", "phone", "bio", "job_title_internal", "extension_phone"):
        value = getattr(profile_data, field, None)
        if value is not None:
            user_update[field] = value

    if profile_data.avatar is not None:
        user_update["avatar_url"] = profile_data.avatar

    if user_update:
        user_update["updated_at"] = datetime.now(timezone.utc)
        await UserRepository.update(current_user.id, user_update)

    if user.get("role") == UserRole.APPLICANT.value:
        profile_update = {}
        
        applicant_fields = (
            "linkedin", "portfolio", 
            "industry_specific_data", "headline", 
            "expected_salary_min", "expected_salary_max", 
            "is_searchable"
        )
        
        for field in applicant_fields:
            value = getattr(profile_data, field, None)
            if value is not None:
                profile_update[field] = value
                
        if profile_data.external_cv_links is not None:
            profile_update["external_cv_links"] = [link.model_dump() for link in profile_data.external_cv_links]
                
        if profile_data.current_location is not None:
            profile_update["current_location"] = profile_data.current_location.model_dump(exclude_unset=True)

        if profile_update:
            profile_update["updated_at"] = datetime.now(timezone.utc)
            existing_profile = await ApplicantProfileRepository.get_by_user_id(current_user.id)
            
            if existing_profile:
                await ApplicantProfileRepository.update(str(existing_profile["_id"]), profile_update)
            else:
                profile_update["user_id"] = current_user.id
                profile_update["created_at"] = datetime.now(timezone.utc)
                profile_update["deleted_at"] = None
                await ApplicantProfileRepository.create(profile_update)

    return {"status": "success", "message": "Cập nhật thông tin thành công"}

@router.patch("/change-password")
async def change_password(password_data: PasswordChange, current_user: CurrentUser = Depends(get_current_user)):
    user = await UserRepository.get_by_id(current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    if not verify_password(password_data.current_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

    new_hashed_password = get_password_hash(password_data.new_password)

    await UserRepository.update(current_user.id, {
        "hashed_password": new_hashed_password,
        "updated_at": datetime.now(timezone.utc)
    })

    return {"status": "success", "message": "Đổi mật khẩu thành công"}

@router.get("/me")
async def get_current_user_profile(current_user: CurrentUser = Depends(get_current_user)):
    user = await UserRepository.get_by_id(current_user.id)

    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin người dùng")

    return {
        "id": current_user.id,
        "email": user["email"],
        "full_name": user.get("full_name", "User"),
        "avatar_url": user.get("avatar_url", ""),
        "role": user.get("role"),
        "company_id": user.get("company_id"),
    }

@router.post("/docs-login", response_model=Token, include_in_schema=False)
async def swagger_login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await UserRepository.get_by_email(form_data.username)

    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không chính xác")

    if not user.get("is_verified", False):
        raise HTTPException(status_code=401, detail="Vui lòng kiểm tra email để kích hoạt tài khoản!")

    access_token = create_access_token(build_token_payload(user))
    return {"access_token": access_token, "token_type": "bearer"}

@router.delete("/me/anonymize", status_code=200, tags=["Profile"])
async def anonymize_account(current_user: CurrentUser = Depends(get_current_user)):
    user = await UserRepository.get_by_id(current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    # ==========================================
    # EDGE CASE: XỬ LÝ NHƯỢNG QUYỀN HR_OWNER
    # ==========================================
    if user.get("role") == UserRole.HR_OWNER.value and user.get("company_id"):
        company = await CompanyRepository.get_by_id(user["company_id"])
        
        if company and company.get("owner_user_id") == current_user.id:
            hr_count = await UserRepository.count_documents({
                "company_id": user["company_id"],
                "role": {"$in": [UserRole.HR_OWNER.value, UserRole.HR_MEMBER.value]}
            })
            
            if hr_count > 1:
                raise HTTPException(
                    status_code=400, 
                    detail="Công ty đang có thành viên khác. Bạn phải chuyển quyền Owner trước khi xóa tài khoản."
                )
            else:
                await CompanyRepository.update(
                    user["company_id"], 
                    {
                        "status": CompanyStatus.SUSPENDED.value, 
                        "deleted_at": utc_now()
                    }
                )
                await JobRepository.update_many(
                    {"company_id": user["company_id"], "status": JobStatus.OPEN.value},
                    {"status": JobStatus.CLOSED.value}
                )

    # ==========================================
    # KỸ THUẬT ANONYMIZATION
    # ==========================================
    timestamp = int(time.time())
    anonymized_email = f"deleted_{timestamp}_{current_user.id}@anonymized.local"
    
    random_pw = get_password_hash(secrets.token_urlsafe(32)) 
    
    update_data = {
        "email": anonymized_email,
        "hashed_password": random_pw,
        "full_name": "Người dùng đã xóa",
        "avatar_url": "",
        "original_avatar_url": "",
        "is_active": False,
        "deleted_at": utc_now(),
    }
    
    unset_data = {
        "phone": "",
        "bio": "",
        "github": "",
        "linkedin": "",
        "job_title_internal": "",
        "extension_phone": ""
    }

    await UserRepository.update_custom(
        {"_id": ObjectId(current_user.id)},
        {"$set": update_data, "$unset": unset_data}
    )
    
    if user.get("role") == UserRole.APPLICANT.value:
        await ApplicantProfileRepository.update_custom(
            {"user_id": current_user.id},
            {"$set": {"deleted_at": utc_now()}, "$unset": {"phone": "", "address": "", "bio": "", "linkedin": "", "industry_specific_data": ""}}
        )
    
    await RefreshTokenRepository.delete_many({"user_id": current_user.id})

    await log_action(
        actor_id=current_user.id,
        actor_role=user.get("role"),
        action=AuditAction.USER_ANONYMIZED,
        target_type="user",
        target_id=current_user.id,
        note="Người dùng chủ động xóa và ẩn danh tài khoản vĩnh viễn"
    )

    return {"status": "success", "message": "Tài khoản của bạn đã được xóa và ẩn danh vĩnh viễn."}

async def merge_ghost_profiles(user_id: str, email: str):
    try:
        ghost_cvs = await CVRepository.find_all({
            "candidate_info.email": email,
            "owner_user_id": {"$ne": user_id}
        }, limit=None)

        if not ghost_cvs:
            return

        for cv in ghost_cvs:
            old_owner_id = cv.get("owner_user_id")
            cv_id = str(cv["_id"])
            
            await CVRepository.update(cv_id, {"owner_user_id": user_id})

            ghost_apps = await ApplicationRepository.find_all({
                "cv_id": cv_id,
                "source": ApplicationSource.HR_SOURCED.value
            }, limit=None)

            for app in ghost_apps:
                await ApplicationRepository.update(str(app["_id"]), {"applicant_user_id": user_id})

        print(f"[Ghost Merge] Đã hòa mạng {len(ghost_cvs)} CV cho user {email}")
    except Exception as e:
        print(f"[Ghost Merge Error] Lỗi khi hòa mạng tài khoản cho {email}: {str(e)}")
from typing import Optional
import re
from fastapi import APIRouter, Depends, Body, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.middleware.rate_limit import limiter
from app.schemas.common_schema import UserRole
from app.schemas.user_schema import UserCreate
from app.schemas.auth_schema import UserLogin, Token
from app.schemas.shared_schema import LocationDetail
from app.core.security import CurrentUser, get_current_user
from app.services.domain.auth_service import AuthService

# ---------------------------------------------------------------------
# Helper & DTOs
# ---------------------------------------------------------------------
def validate_strong_password(v: str) -> str:
    pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#+\-_=])[A-Za-z\d@$!%*?&#+\-_=]{8,}$"
    if not re.match(pattern, v):
        raise ValueError("Mật khẩu phải từ 8 ký tự, gồm ít nhất 1 chữ hoa, 1 chữ thường, 1 số và 1 ký tự đặc biệt.")
    return v

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

# =====================================================================
# ĐĂNG KÝ / XÁC THỰC EMAIL
# =====================================================================

@router.post("/register", status_code=201)
@limiter.limit("10/day")
async def register_user(request: Request, response: Response, background_tasks: BackgroundTasks, payload: RegisterRequest = Body(...)):
    return await AuthService.register(payload, background_tasks)

@router.get("/verify")
@limiter.limit("20/minute")
async def verify_email(request: Request, response: Response, token: str, background_tasks: BackgroundTasks):
    return await AuthService.verify(token, background_tasks)

# =====================================================================
# ĐĂNG NHẬP & QUÊN MẬT KHẨU
# =====================================================================

@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login_for_access_token(request: Request, response: Response, user_credentials: UserLogin = Body(...)):
    return await AuthService.login(user_credentials)

@router.post("/forgot-password")
@limiter.limit("5/day")
async def forgot_password(request: Request, response: Response, background_tasks: BackgroundTasks, email: str = Body(..., embed=True)):
    return await AuthService.forgot_password(email, background_tasks)

@router.post("/reset-password")
@limiter.limit("5/day")
async def reset_password(request: Request, response: Response, payload: ResetPasswordRequest):
    return await AuthService.reset_password(payload)

# =====================================================================
# SOCIAL OAUTH
# =====================================================================

@router.post("/google")
@limiter.limit("10/minute")
async def google_login(request: Request, response: Response, background_tasks: BackgroundTasks, social_request: SocialAuthRequest = Body(...)):
    result = await AuthService.google_login(social_request, background_tasks)
    if result.get("action") == "require_role":
        return JSONResponse(status_code=202, content=result)
    return result

@router.post("/linkedin")
@limiter.limit("10/minute")
async def linkedin_login(request: Request, response: Response, background_tasks: BackgroundTasks, social_request: SocialAuthRequest = Body(...)):
    result = await AuthService.linkedin_login(social_request, background_tasks)
    if result.get("action") == "require_role":
        return JSONResponse(status_code=202, content=result)
    return result

# =====================================================================
# PROFILE MANAGEMENT
# =====================================================================

@router.get("/profile")
async def get_profile(current_user: CurrentUser = Depends(get_current_user)):
    return await AuthService.get_profile(current_user.id)

@router.patch("/profile")
async def update_profile(profile_data: ProfileUpdate, current_user: CurrentUser = Depends(get_current_user)):
    return await AuthService.update_profile(current_user.id, profile_data)

@router.patch("/change-password")
async def change_password(password_data: PasswordChange, current_user: CurrentUser = Depends(get_current_user)):
    return await AuthService.change_password(current_user.id, password_data)

@router.get("/me")
async def get_current_user_profile(current_user: CurrentUser = Depends(get_current_user)):
    profile_data = await AuthService.get_profile(current_user.id)
    return {
        "id": profile_data["id"],
        "email": profile_data["email"],
        "full_name": profile_data["full_name"],
        "avatar_url": profile_data["avatar_url"],
        "role": profile_data["role"],
        "company_id": profile_data["company_id"],
    }

@router.delete("/me/anonymize", status_code=200, tags=["Profile"])
async def anonymize_account(current_user: CurrentUser = Depends(get_current_user)):
    return await AuthService.anonymize(current_user)
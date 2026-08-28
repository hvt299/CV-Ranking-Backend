import secrets
import hashlib
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
import httpx
import jwt
import os
from bson import ObjectId
from fastapi import HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from app.schemas.common_schema import UserRole, CompanyStatus, JobStatus, utc_now, AuditAction, ApplicationSource
from app.repositories.user_repository import UserRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.job_repository import JobRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.applicant_profile_repository import ApplicantProfileRepository
from app.repositories.cv_repository import CVRepository
from app.repositories.application_repository import ApplicationRepository
from app.services.audit_service import log_action
from app.services.email_service import send_verification_email, send_reset_password_email
from app.core.security import get_password_hash, verify_password, create_access_token, build_token_payload, JWT_SECRET, ALGORITHM

SELF_REGISTERABLE_ROLES = (UserRole.APPLICANT, UserRole.HR_OWNER)
LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")

class AuthService:
    @staticmethod
    def _make_avatar_url(full_name: str) -> str:
        encoded_name = urllib.parse.quote(full_name)
        return f"https://ui-avatars.com/api/?name={encoded_name}&background=random&color=fff&size=200"

    @staticmethod
    async def _create_company(req_data) -> str:
        company_doc = {
            "name": req_data.company_name,
            "tax_code": req_data.tax_code,
            "industry": getattr(req_data, 'industry', None),
            "size": getattr(req_data, 'size', None),
            "address": getattr(req_data, 'address', None),
            "website": getattr(req_data, 'website', None),
            "status": CompanyStatus.PENDING_VERIFICATION.value,
            "created_at": datetime.now(timezone.utc)
        }
        return await CompanyRepository.create(company_doc)

    @staticmethod
    async def register(payload, background_tasks: BackgroundTasks):
        if payload.invite_token:
            try:
                token_data = jwt.decode(payload.invite_token, JWT_SECRET, algorithms=[ALGORITHM])
                if token_data.get("email") != payload.email:
                    raise HTTPException(status_code=400, detail="Email đăng ký không khớp email mời!")
                if await UserRepository.get_by_email(payload.email):
                    raise HTTPException(status_code=400, detail="Email đã tồn tại!")
                
                user_id = await UserRepository.create({
                    "email": payload.email,
                    "full_name": payload.full_name,
                    "hashed_password": get_password_hash(payload.password),
                    "avatar_url": AuthService._make_avatar_url(payload.full_name),
                    "original_avatar_url": AuthService._make_avatar_url(payload.full_name),
                    "role": token_data.get("role", UserRole.HR_MEMBER.value),
                    "company_id": token_data.get("company_id"),
                    "is_verified": True,
                    "created_at": datetime.now(timezone.utc),
                })
                
                if token_data.get("role") == UserRole.APPLICANT.value:
                    await ApplicantProfileRepository.create({"user_id": str(user_id), "created_at": datetime.now(timezone.utc)})
                return {"status": "success", "message": "Gia nhập thành công!"}
            except jwt.PyJWTError:
                raise HTTPException(status_code=400, detail="Link mời không hợp lệ.")

        if payload.role not in SELF_REGISTERABLE_ROLES:
            raise HTTPException(status_code=400, detail="Quyền đăng ký không hợp lệ.")
        if await UserRepository.get_by_email(payload.email):
            raise HTTPException(status_code=400, detail="Email này đã được đăng ký!")

        company_id = None
        if payload.role == UserRole.HR_OWNER:
            if not payload.company_name or not payload.tax_code:
                raise HTTPException(status_code=400, detail="Thiếu company_name/tax_code")
            company_id = await AuthService._create_company(payload)

        user_id = await UserRepository.create({
            "email": payload.email,
            "full_name": payload.full_name,
            "hashed_password": get_password_hash(payload.password),
            "avatar_url": AuthService._make_avatar_url(payload.full_name),
            "role": payload.role.value,
            "company_id": company_id,
            "is_verified": False,
            "created_at": datetime.now(timezone.utc),
        })

        if payload.role == UserRole.APPLICANT:
            await ApplicantProfileRepository.create({"user_id": str(user_id), "created_at": datetime.now(timezone.utc)})

        verify_token = jwt.encode({"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(days=1)}, JWT_SECRET, algorithm=ALGORITHM)
        send_verification_email(background_tasks, payload.email, payload.full_name, verify_token)
        return {"status": "success", "message": "Đăng ký thành công! Vui lòng kiểm tra email."}

    @staticmethod
    async def login(credentials):
        user = await UserRepository.get_by_email(credentials.email)
        if not user or not verify_password(credentials.password, user["hashed_password"]):
            raise HTTPException(status_code=401, detail="Email hoặc mật khẩu sai")
        if not user.get("is_verified", False):
            raise HTTPException(status_code=401, detail="Chưa kích hoạt email!")
        return {"access_token": create_access_token(build_token_payload(user)), "token_type": "bearer"}

    @staticmethod
    async def anonymize(current_user):
        user = await UserRepository.get_by_id(current_user.id)
        if user.get("role") == UserRole.HR_OWNER.value and user.get("company_id"):
            hr_count = await UserRepository.count_documents({"company_id": user["company_id"], "role": {"$in": [UserRole.HR_OWNER.value, UserRole.HR_MEMBER.value]}})
            if hr_count > 1:
                raise HTTPException(status_code=400, detail="Phải chuyển quyền Owner trước khi xóa.")
            await CompanyRepository.update(user["company_id"], {"status": CompanyStatus.SUSPENDED.value, "deleted_at": utc_now()})
            await JobRepository.update_many({"company_id": user["company_id"], "status": JobStatus.OPEN.value}, {"status": JobStatus.CLOSED.value})

        anonymized_email = f"deleted_{int(time.time())}_{current_user.id}@anonymized.local"
        await UserRepository.update_custom(
            {"_id": ObjectId(current_user.id)},
            {"$set": {"email": anonymized_email, "hashed_password": get_password_hash(secrets.token_urlsafe(32)), "full_name": "Người dùng đã xóa", "is_active": False, "deleted_at": utc_now()}, 
             "$unset": {"phone": "", "bio": "", "github": "", "linkedin": "", "job_title_internal": ""}}
        )
        if user.get("role") == UserRole.APPLICANT.value:
            await ApplicantProfileRepository.update_custom({"user_id": current_user.id}, {"$set": {"deleted_at": utc_now()}, "$unset": {"phone": "", "address": ""}})
        await RefreshTokenRepository.delete_many({"user_id": current_user.id})
        await log_action(actor_id=current_user.id, actor_role=user.get("role"), action=AuditAction.USER_ANONYMIZED, target_type="user", target_id=current_user.id, note="Xóa ẩn danh")
        return {"status": "success", "message": "Xóa và ẩn danh thành công."}

    @staticmethod
    async def verify(token: str, background_tasks: BackgroundTasks):
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            
            modified_count = await UserRepository.update(user_id, {"is_verified": True})
            if modified_count == 0:
                raise HTTPException(status_code=400, detail="Tài khoản không tồn tại hoặc đã được xác thực.")

            user = await UserRepository.get_by_id(user_id)
            if user and user.get("role") == UserRole.APPLICANT.value:
                background_tasks.add_task(AuthService.merge_ghost_profiles, user_id, user.get("email"))

            return {"message": "Xác thực thành công! Tài khoản của bạn đã được kích hoạt."}
        except jwt.PyJWTError:
            raise HTTPException(status_code=400, detail="Link xác thực không hợp lệ hoặc đã hết hạn.")

    @staticmethod
    async def forgot_password(email: str, background_tasks: BackgroundTasks):
        user = await UserRepository.get_by_email(email)
        msg = "Nếu email tồn tại trên hệ thống, link khôi phục đã được gửi."
        if not user:
            return {"message": msg}

        reset_token = secrets.token_hex(32)
        hashed_token = hashlib.sha256(reset_token.encode()).hexdigest()

        await UserRepository.update(str(user.get("id")), {
            "reset_password_token": hashed_token,
            "reset_password_expires": datetime.now(timezone.utc) + timedelta(minutes=15)
        })

        send_reset_password_email(background_tasks, user["email"], user["full_name"], reset_token)
        return {"message": msg}

    @staticmethod
    async def reset_password(payload):
        hashed_token = hashlib.sha256(payload.token.encode()).hexdigest()
        user = await UserRepository.find_one({
            "reset_password_token": hashed_token, 
            "reset_password_expires": {"$gt": datetime.now(timezone.utc)}
        })
        
        if not user:
            raise HTTPException(status_code=400, detail="Link khôi phục không hợp lệ hoặc đã hết hạn!")

        hashed_pw = get_password_hash(payload.new_password)
        await UserRepository.update_custom(
            {"_id": ObjectId(user.get("id"))},
            {"$set": {"hashed_password": hashed_pw}, "$unset": {"reset_password_token": "", "reset_password_expires": ""}}
        )
        return {"message": "Mật khẩu đã được đặt lại thành công! Bạn có thể đăng nhập."}

    @staticmethod
    async def _process_social_login(email: str, full_name: str, picture: str, social_request, background_tasks: BackgroundTasks):
        user = await UserRepository.get_by_email(email)

        if not user:
            company_id = None
            assigned_role = social_request.role

            if social_request.invite_token:
                try:
                    token_data = jwt.decode(social_request.invite_token, JWT_SECRET, algorithms=[ALGORITHM])
                    if token_data.get("email") != email:
                        raise HTTPException(status_code=400, detail="Email tài khoản xã hội không khớp với email được mời!")
                    assigned_role = token_data.get("role", UserRole.HR_MEMBER.value)
                    company_id = token_data.get("company_id")
                except jwt.PyJWTError:
                    raise HTTPException(status_code=400, detail="Link mời không hợp lệ hoặc đã hết hạn.")
            else:
                if not assigned_role:
                    return {
                        "action": "require_role", 
                        "message": "Vui lòng chọn vai trò để hoàn tất", 
                        "email": email
                    }

                if assigned_role not in SELF_REGISTERABLE_ROLES:
                    raise HTTPException(status_code=400, detail="Quyền đăng ký không hợp lệ qua mạng xã hội.")

                if assigned_role == UserRole.HR_OWNER:
                    if not social_request.company_name or not social_request.tax_code:
                        raise HTTPException(status_code=400, detail="company_name và tax_code là bắt buộc.")
                    company_id = await AuthService._create_company(social_request)

            hashed_pw = get_password_hash(secrets.token_urlsafe(32))
            final_avatar = picture if picture else AuthService._make_avatar_url(full_name)
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
                await ApplicantProfileRepository.create({"user_id": str(user_id), "created_at": datetime.now(timezone.utc), "deleted_at": None})
                
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
                await UserRepository.update(str(user.get("id")), update_fields)
                user.update(update_fields)

        if user.get("role") == UserRole.APPLICANT.value or user.get("role") == UserRole.APPLICANT:
             background_tasks.add_task(AuthService.merge_ghost_profiles, str(user.get("id")), user.get("email"))

        return {"access_token": create_access_token(build_token_payload(user)), "token_type": "bearer"}

    @staticmethod
    async def google_login(social_request, background_tasks: BackgroundTasks):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={social_request.access_token}")
                if response.status_code != 200:
                    raise ValueError("Token không hợp lệ")
                idinfo = response.json()
            return await AuthService._process_social_login(idinfo['email'], idinfo.get('name', 'Người dùng Google'), idinfo.get('picture', ''), social_request, background_tasks)
        except ValueError:
            raise HTTPException(status_code=401, detail="Token từ Google không hợp lệ hoặc đã hết hạn")

    @staticmethod
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
        
        access_token = token_res.json().get("access_token")
        if not access_token:
            raise ValueError("Phản hồi từ LinkedIn không chứa access_token")
        return access_token

    @staticmethod
    async def linkedin_login(social_request, background_tasks: BackgroundTasks):
        try:
            if not social_request.code or not social_request.redirect_uri:
                raise HTTPException(status_code=400, detail="Thiếu 'code' hoặc 'redirect_uri' để xác thực LinkedIn.")
            
            access_token = await AuthService._exchange_linkedin_code(social_request.code, social_request.redirect_uri)
            
            async with httpx.AsyncClient() as client:
                res = await client.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"})
                if res.status_code != 200:
                    raise ValueError("Token LinkedIn không hợp lệ")
                idinfo = res.json()
                
            return await AuthService._process_social_login(idinfo.get('email'), idinfo.get('name', 'Người dùng LinkedIn'), idinfo.get('picture', ''), social_request, background_tasks)
        except ValueError as e:
            raise HTTPException(status_code=401, detail=str(e) or "Token từ LinkedIn không hợp lệ hoặc đã hết hạn")

    @staticmethod
    async def get_profile(user_id: str):
        user = await UserRepository.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy thông tin người dùng")

        profile = {}
        if user.get("role") == UserRole.APPLICANT.value:
            profile = await ApplicantProfileRepository.get_by_user_id(user_id) or {}

        return {
            "id": user_id,
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

    @staticmethod
    async def update_profile(user_id: str, profile_data):
        user = await UserRepository.get_by_id(user_id)
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
            await UserRepository.update(user_id, user_update)

        if user.get("role") == UserRole.APPLICANT.value:
            profile_update = {}
            for field in ("linkedin", "portfolio", "industry_specific_data", "headline", "expected_salary_min", "expected_salary_max", "is_searchable"):
                value = getattr(profile_data, field, None)
                if value is not None:
                    profile_update[field] = value
                    
            if profile_data.external_cv_links is not None:
                profile_update["external_cv_links"] = [link.model_dump() for link in profile_data.external_cv_links]
            if profile_data.current_location is not None:
                profile_update["current_location"] = profile_data.current_location.model_dump(exclude_unset=True)

            if profile_update:
                profile_update["updated_at"] = datetime.now(timezone.utc)
                existing_profile = await ApplicantProfileRepository.get_by_user_id(user_id)
                if existing_profile:
                    await ApplicantProfileRepository.update(str(existing_profile.get("id")), profile_update)
                else:
                    profile_update.update({"user_id": user_id, "created_at": datetime.now(timezone.utc), "deleted_at": None})
                    await ApplicantProfileRepository.create(profile_update)

        return {"status": "success", "message": "Cập nhật thông tin thành công"}

    @staticmethod
    async def change_password(user_id: str, password_data):
        user = await UserRepository.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

        if not verify_password(password_data.current_password, user["hashed_password"]):
            raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

        await UserRepository.update(user_id, {
            "hashed_password": get_password_hash(password_data.new_password),
            "updated_at": datetime.now(timezone.utc)
        })
        return {"status": "success", "message": "Đổi mật khẩu thành công"}

    @staticmethod
    async def merge_ghost_profiles(user_id: str, email: str):
        try:
            ghost_cvs = await CVRepository.find_all({"candidate_info.email": email, "owner_user_id": {"$ne": user_id}}, limit=None)
            if not ghost_cvs:
                return

            for cv in ghost_cvs:
                cv_id = str(cv.get("id"))
                await CVRepository.update(cv_id, {"owner_user_id": user_id})

                ghost_apps = await ApplicationRepository.find_all({"cv_id": cv_id, "source": ApplicationSource.HR_SOURCED.value}, limit=None)
                for app in ghost_apps:
                    await ApplicationRepository.update(str(app.get("id")), {"applicant_user_id": user_id})

            print(f"[Ghost Merge] Đã hòa mạng {len(ghost_cvs)} CV cho user {email}")
        except Exception as e:
            print(f"[Ghost Merge Error] Lỗi khi hòa mạng tài khoản cho {email}: {str(e)}")
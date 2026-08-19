from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Optional
import os
import math

from app.core.security import CurrentUser, require_admin
from app.schemas.common_schema import UserRole, CompanyStatus, AuditAction, NotificationType, NotificationActorType, NotificationActionType, NotificationReadStatus
from app.schemas.company_schema import CompanyVerifyAction
from app.schemas.subscription_plan_schema import SubscriptionPlanCreate, SubscriptionPlanUpdate
from app.repositories.user_repository import UserRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.services.analytics_service import AnalyticsService
from app.services.audit_service import log_action

from pydantic import BaseModel, Field, EmailStr


router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])
BOOTSTRAP_SECRET = os.getenv("ADMIN_BOOTSTRAP_SECRET", "")
class BootstrapRequest(BaseModel):
    secret: str = Field(..., description="Mã bảo mật lấy từ biến môi trường")
    email: EmailStr = Field(..., description="Email của tài khoản cần thăng cấp Admin")

class UpdateRoleRequest(BaseModel):
    role: UserRole = Field(..., description="Phân quyền mới (admin, hr_owner, hr_member, applicant)")

class UpdateUserStatusRequest(BaseModel):
    is_active: bool = Field(..., description="Trạng thái khóa/mở khóa tài khoản")

class TogglePlanStatusRequest(BaseModel):
    is_active: bool = Field(..., description="Trạng thái Ẩn/Hiện gói cước")

@router.post("/bootstrap")
async def bootstrap_admin(payload: BootstrapRequest):
    if not BOOTSTRAP_SECRET:
        raise HTTPException(status_code=403, detail="Bootstrap đã bị tắt")
        
    if payload.secret != BOOTSTRAP_SECRET:
        raise HTTPException(status_code=403, detail="Secret không đúng")
        
    modified_count = await UserRepository.update_custom(
        {"email": payload.email}, 
        {"$set": {"role": UserRole.ADMIN.value}}
    )
    if modified_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
        
    return {"status": "success", "message": f"{payload.email} đã được set làm Admin"}

@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users():
    projection = {
        "hashed_password": 0, 
        "reset_password_token": 0, 
        "reset_password_expires": 0
    }
    users = await UserRepository.find_many({}, projection=projection, limit=500)
    
    result = []
    for u in users:
        u["id"] = str(u["_id"])
        del u["_id"]
        result.append(u)
        
    return result

@router.patch("/users/{user_id}/role")
async def update_user_role(user_id: str, payload: UpdateRoleRequest, current_admin: CurrentUser = Depends(require_admin)):
    user = await UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        
    before_role = user.get("role")
    await UserRepository.update(user_id, {"role": payload.role.value})
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.USER_ROLE_UPDATED,
        target_type="user",
        target_id=user_id,
        note=f"Admin thay đổi quyền từ {before_role} sang {payload.role.value}",
        before_state={"role": before_role},
        after_state={"role": payload.role.value}
    )
        
    return {"status": "success", "message": f"Đã cập nhật role thành '{payload.role.value}'"}

@router.patch("/users/{user_id}/status")
async def update_user_status(user_id: str, payload: UpdateUserStatusRequest, current_admin: CurrentUser = Depends(require_admin)):
    user = await UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
        
    before_status = user.get("is_active", True)
    await UserRepository.update(user_id, {"is_active": payload.is_active})
    
    action_msg = "Mở khóa" if payload.is_active else "Khóa đình chỉ"
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.USER_STATUS_UPDATED,
        target_type="user",
        target_id=user_id,
        note=f"Admin thao tác: {action_msg} tài khoản",
        before_state={"is_active": before_status},
        after_state={"is_active": payload.is_active}
    )
        
    return {"status": "success", "message": f"Đã {action_msg} tài khoản thành công"}

@router.get("/companies", dependencies=[Depends(require_admin)])
async def list_companies(status: str = None):
    query = {}
    if status:
        query["status"] = status
        
    companies = await CompanyRepository.find_many(query, limit=500)
    
    result = []
    for c in companies:
        c["id"] = str(c["_id"])
        del c["_id"]
        result.append(c)
    return result

@router.patch("/companies/{company_id}/verify")
async def verify_company(
    company_id: str, 
    action: CompanyVerifyAction,
    current_admin: CurrentUser = Depends(require_admin)
):    
    existing_company = await CompanyRepository.get_by_id(company_id)
    if not existing_company:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty")

    new_status = CompanyStatus.VERIFIED.value if action.approve else CompanyStatus.REJECTED.value

    update_data = {
        "status": new_status,
        "verified_by_admin_id": current_admin.id,
        "verified_at": datetime.now(timezone.utc)
    }

    if action.approve:
        update_data["kyc_approved_at"] = datetime.now(timezone.utc)
    else:
        update_data["rejection_reason"] = action.rejection_reason

    await CompanyRepository.update(company_id, update_data)

    before_state = {k: v for k, v in existing_company.items() if k != "_id"}
    after_state = {**before_state, **update_data}

    audit_action = AuditAction.COMPANY_VERIFIED if action.approve else AuditAction.COMPANY_REJECTED
    note = f"Duyệt thành công" if action.approve else f"Từ chối: {action.rejection_reason}"

    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=audit_action,
        target_type="company",
        target_id=company_id,
        note=note,
        before_state=before_state,
        after_state=after_state
    )

    owner_id = existing_company.get("owner_user_id")
    if owner_id:        
        notif_action = NotificationActionType.KYC_APPROVED.value if action.approve else NotificationActionType.KYC_REJECTED.value
        notif_type = NotificationType.SUCCESS.value if action.approve else NotificationType.ERROR.value
        notif_title = "Xác thực doanh nghiệp thành công" if action.approve else "Xác thực doanh nghiệp thất bại"
        notif_msg = f"Công ty {existing_company.get('name')} đã được duyệt." if action.approve else f"Từ chối duyệt: {action.rejection_reason}"
        
        await NotificationRepository.create({
            "recipient_user_id": str(owner_id),
            "recipient_type": NotificationActorType.HR_USER.value,
            "sender_id": current_admin.id,
            "sender_type": NotificationActorType.ADMIN.value,
            "action_type": notif_action,
            "title": notif_title,
            "message": notif_msg,
            "type": notif_type,
            "entity_ref": {"type": "company", "id": company_id},
            "payload": {"status": new_status, "reason": action.rejection_reason},
            "status": NotificationReadStatus.UNREAD.value,
            "created_at": datetime.now(timezone.utc)
        })

    return {"status": "success", "message": "Đã xử lý trạng thái công ty"}

@router.get("/audit-logs", dependencies=[Depends(require_admin)])
async def get_audit_logs(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=100, description="Số lượng record mỗi trang"),
    action: Optional[str] = Query(None, description="Lọc theo loại hành động"),
    actor_id: Optional[str] = Query(None, description="Lọc theo ID người thực hiện"),
    start_date: Optional[datetime] = Query(None, description="Từ ngày"),
    end_date: Optional[datetime] = Query(None, description="Đến ngày")
):
    query = {}
    if action:
        query["action"] = action
    if actor_id:
        query["actor_id"] = actor_id
        
    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date
        query["created_at"] = date_query
        
    logs, total_items = await AuditRepository.get_paginated_logs(query, page, page_size)
    
    result = []
    for lg in logs:
        lg["id"] = str(lg["_id"])
        del lg["_id"]
        result.append(lg)
        
    total_pages = math.ceil(total_items / page_size) if total_items > 0 else 1
        
    return {
        "status": "success",
        "data": {
            "items": result,
            "pagination": {
                "total_items": total_items,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size
            }
        }
    }

@router.patch("/companies/{company_id}")
async def admin_update_company(
    company_id: str,
    update_data: dict = Body(...),
    current_admin: CurrentUser = Depends(require_admin)
):
    allowed_fields = ["name", "tax_code", "industry", "size", "website", "address", "license_file_url", "status"]
    clean_data = {k: v for k, v in update_data.items() if k in allowed_fields}

    if not clean_data:
        return {"status": "success"}

    existing_company = await CompanyRepository.get_by_id(company_id)
    if not existing_company:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty")

    await CompanyRepository.update(company_id, clean_data)

    before_state = {k: v for k, v in existing_company.items() if k != "_id"}
    after_state = {**before_state, **clean_data}

    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.COMPANY_UPDATED if hasattr(AuditAction, 'COMPANY_UPDATED') else "company_updated",
        target_type="company",
        target_id=company_id,
        note="Admin cập nhật thông tin công ty",
        before_state=before_state,
        after_state=after_state
    )

    return {"status": "success", "message": "Cập nhật thành công"}

@router.get("/dashboard/metrics", dependencies=[Depends(require_admin)])
async def get_admin_dashboard():
    data = await AnalyticsService.get_admin_dashboard_metrics()
    return {"status": "success", "data": data}

@router.get("/analytics", dependencies=[Depends(require_admin)])
async def get_admin_analytics():
    data = await AnalyticsService.get_admin_system_analytics()
    return {"status": "success", "data": data}

@router.post("/subscriptions/plans", dependencies=[Depends(require_admin)])
async def create_subscription_plan(
    payload: SubscriptionPlanCreate, 
    current_admin: CurrentUser = Depends(require_admin)
):
    existing_plan = await SubscriptionPlanRepository.find_one({"plan_code": payload.plan_code})
    if existing_plan:
        raise HTTPException(status_code=400, detail=f"Mã định danh gói cước '{payload.plan_code}' đã tồn tại. Vui lòng chọn mã khác.")
        
    record = payload.model_dump()
    record["created_at"] = datetime.now(timezone.utc)
    record["updated_at"] = datetime.now(timezone.utc)
    
    _id = await SubscriptionPlanRepository.create(record)
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.PLAN_CREATED,
        target_type="subscription_plan",
        target_id=str(_id),
        note=f"Admin tạo gói cước mới: {payload.name}"
    )
    
    return {"status": "success", "message": "Tạo gói cước thành công", "id": str(_id)}

@router.patch("/subscriptions/plans/{plan_id}", dependencies=[Depends(require_admin)])
async def update_subscription_plan(
    plan_id: str, 
    payload: SubscriptionPlanUpdate, 
    current_admin: CurrentUser = Depends(require_admin)
):
    plan = await SubscriptionPlanRepository.get_by_id(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói cước")
        
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return {"status": "success", "message": "Không có dữ liệu mới để cập nhật"}
        
    update_data["updated_at"] = datetime.now(timezone.utc)
    await SubscriptionPlanRepository.update(plan_id, update_data)
    
    before_state = {k: v for k, v in plan.items() if k != "_id"}
    after_state = {**before_state, **update_data}
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.PLAN_UPDATED,
        target_type="subscription_plan",
        target_id=plan_id,
        note=f"Admin cập nhật thông tin gói cước",
        before_state=before_state,
        after_state=after_state
    )
    
    return {"status": "success", "message": "Cập nhật gói cước thành công"}

@router.patch("/subscriptions/plans/{plan_id}/status", dependencies=[Depends(require_admin)])
async def toggle_subscription_plan_status(
    plan_id: str, 
    payload: TogglePlanStatusRequest, 
    current_admin: CurrentUser = Depends(require_admin)
):
    plan = await SubscriptionPlanRepository.get_by_id(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói cước")
        
    before_status = plan.get("is_active", True)
    if before_status == payload.is_active:
        return {"status": "success", "message": "Trạng thái không thay đổi"}
        
    await SubscriptionPlanRepository.update(plan_id, {"is_active": payload.is_active, "updated_at": datetime.now(timezone.utc)})
    
    action_msg = "Mở bán (Hiện)" if payload.is_active else "Ngừng bán (Ẩn)"
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.PLAN_STATUS_TOGGLED,
        target_type="subscription_plan",
        target_id=plan_id,
        note=f"Admin {action_msg} gói cước",
        before_state={"is_active": before_status},
        after_state={"is_active": payload.is_active}
    )
    
    return {"status": "success", "message": f"Đã {action_msg} gói cước thành công"}
from datetime import datetime, timezone
import re

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Optional
import os
import math
import unidecode

from app.core.security import CurrentUser, require_admin
from app.schemas.common_schema import UserRole, CompanyStatus, AuditAction, NotificationType, NotificationActorType, NotificationActionType, NotificationReadStatus
from app.schemas.company_schema import CompanyVerifyAction
from app.schemas.subscription_plan_schema import SubscriptionPlanCreate, SubscriptionPlanUpdate
from app.schemas.skill_schema import SkillCreate, SkillUpdate
from app.schemas.administrative_unit_schema import AdministrativeUnitCreate
from app.schemas.common_schema import ReportStatus, JobStatus
from app.schemas.report_schema import ReportResolve
from app.schemas.support_ticket_schema import SupportTicketResolve
from app.schemas.common_schema import TicketStatus
from app.repositories.support_ticket_repository import SupportTicketRepository
from app.repositories.user_repository import UserRepository
from app.repositories.job_repository import JobRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.skill_repository import SkillRepository
from app.repositories.administrative_unit_repository import AdministrativeUnitRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.blog_repository import BlogRepository
from app.schemas.blog_schema import BlogCreate, BlogUpdate
from fastapi import BackgroundTasks
from app.services.analytics_service import AnalyticsService
from app.services.audit_service import log_action
from app.services.nlp_engine import refresh_system_settings, initialize_skill_map
from app.services.email_service import send_ticket_reply_email
from app.database.config import db_instance

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
    raise HTTPException(
        status_code=410, 
        detail="API Bootstrap đã bị vô hiệu hóa vĩnh viễn trên môi trường Production để đảm bảo an toàn hệ thống."
    )

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

class SystemSettingsUpdate(BaseModel):
    industry_weights: Optional[dict] = None
    action_costs: Optional[dict] = None

@router.get("/system/settings", dependencies=[Depends(require_admin)])
async def get_system_settings():
    doc = await SystemSettingsRepository.find_one({"setting_type": "global_config"})
    if doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        return {"status": "success", "data": doc}
    return {"status": "success", "data": {}}

@router.put("/system/settings", dependencies=[Depends(require_admin)])
async def update_system_settings(
    payload: SystemSettingsUpdate,
    current_admin: CurrentUser = Depends(require_admin)
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return {"status": "success", "message": "Không có dữ liệu cập nhật"}
        
    await SystemSettingsRepository.update_custom(
        {"setting_type": "global_config"},
        {"$set": update_data},
        upsert=True
    )
    
    if db_instance.redis:
        await db_instance.redis.delete("system_settings")
        
    await refresh_system_settings()
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.SYSTEM_SETTINGS_UPDATED,
        target_type="system_settings",
        target_id="global_config",
        note="Admin cập nhật cấu hình động (Trọng số / Giá Credit)"
    )
    
    return {"status": "success", "message": "Cập nhật cấu hình hệ thống thành công. Cache đã được làm mới."}

@router.post("/system/skills", dependencies=[Depends(require_admin)])
async def create_skill(
    payload: SkillCreate,
    current_admin: CurrentUser = Depends(require_admin)
):
    record = payload.model_dump()
    _id = await SkillRepository.create(record)
    
    await initialize_skill_map() 
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.SKILL_CREATED,
        target_type="skill",
        target_id=str(_id),
        note=f"Admin thêm Kỹ năng mới: {payload.canonical_name}"
    )
    return {"status": "success", "message": "Tạo kỹ năng thành công", "id": str(_id)}

@router.patch("/system/skills/{skill_id}", dependencies=[Depends(require_admin)])
async def update_skill(
    skill_id: str,
    payload: SkillUpdate,
    current_admin: CurrentUser = Depends(require_admin)
):
    existing = await SkillRepository.get_by_id(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Không tìm thấy kỹ năng")
        
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return {"status": "success", "message": "Không có dữ liệu cập nhật"}
        
    await SkillRepository.update(skill_id, update_data)
    
    await initialize_skill_map() 
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.SKILL_UPDATED,
        target_type="skill",
        target_id=skill_id,
        note=f"Admin cập nhật Kỹ năng"
    )
    return {"status": "success", "message": "Cập nhật kỹ năng thành công"}

@router.delete("/system/skills/{skill_id}", dependencies=[Depends(require_admin)])
async def delete_skill(
    skill_id: str,
    current_admin: CurrentUser = Depends(require_admin)
):
    deleted = await SkillRepository.delete(skill_id, hard_delete=True)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy kỹ năng")
        
    await initialize_skill_map() 
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.SKILL_DELETED,
        target_type="skill",
        target_id=skill_id,
        note=f"Admin xóa cứng Kỹ năng"
    )
    return {"status": "success", "message": "Đã xóa kỹ năng"}

class AdministrativeUnitUpdate(BaseModel):
    name: Optional[str] = None
    parent_code: Optional[str] = None
    version: Optional[str] = None

@router.post("/system/locations", dependencies=[Depends(require_admin)])
async def create_location(
    payload: AdministrativeUnitCreate,
    current_admin: CurrentUser = Depends(require_admin)
):
    record = payload.model_dump()
    _id = await AdministrativeUnitRepository.create(record)
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.LOCATION_CREATED,
        target_type="administrative_unit",
        target_id=str(_id),
        note=f"Admin thêm Địa điểm mới: {payload.name}"
    )
    return {"status": "success", "message": "Thêm địa điểm thành công", "id": str(_id)}

@router.patch("/system/locations/{location_id}", dependencies=[Depends(require_admin)])
async def update_location(
    location_id: str,
    payload: AdministrativeUnitUpdate,
    current_admin: CurrentUser = Depends(require_admin)
):
    existing = await AdministrativeUnitRepository.get_by_id(location_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Không tìm thấy địa điểm")
        
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return {"status": "success", "message": "Không có dữ liệu cập nhật"}
        
    await AdministrativeUnitRepository.update(location_id, update_data)
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.LOCATION_UPDATED,
        target_type="administrative_unit",
        target_id=location_id,
        note=f"Admin cập nhật Địa điểm"
    )
    return {"status": "success", "message": "Cập nhật địa điểm thành công"}

@router.delete("/system/locations/{location_id}", dependencies=[Depends(require_admin)])
async def delete_location(
    location_id: str,
    current_admin: CurrentUser = Depends(require_admin)
):
    deleted = await AdministrativeUnitRepository.delete(location_id, hard_delete=True)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy địa điểm")
        
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.LOCATION_DELETED,
        target_type="administrative_unit",
        target_id=location_id,
        note=f"Admin xóa cứng Địa điểm"
    )
    return {"status": "success", "message": "Đã xóa địa điểm"}

@router.get("/reports", dependencies=[Depends(require_admin)])
async def get_reports(
    status: Optional[ReportStatus] = None,
    target_type: Optional[str] = None
):
    query = {}
    if status:
        query["status"] = status.value
    if target_type:
        query["target_type"] = target_type
        
    reports = await ReportRepository.find_many(query, sort=[("created_at", -1)], limit=200)
    for r in reports:
        r["id"] = str(r["_id"])
        del r["_id"]
    return {"status": "success", "data": reports}

@router.patch("/reports/{report_id}/resolve", dependencies=[Depends(require_admin)])
async def resolve_report(
    report_id: str,
    payload: ReportResolve,
    action: str = Query(..., description="Duyệt (resolve) hoặc Từ chối (reject)"),
    current_admin: CurrentUser = Depends(require_admin)
):
    report = await ReportRepository.get_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Không tìm thấy báo cáo")
        
    new_status = ReportStatus.RESOLVED.value if action == "resolve" else ReportStatus.REJECTED.value
    audit_action = AuditAction.REPORT_RESOLVED if action == "resolve" else AuditAction.REPORT_REJECTED
    
    update_data = {
        "status": new_status,
        "admin_notes": payload.admin_notes,
        "action_taken": payload.action_taken,
        "resolved_by_admin_id": current_admin.id,
        "resolved_at": datetime.now(timezone.utc)
    }
    
    await ReportRepository.update(report_id, update_data)
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=audit_action,
        target_type="report",
        target_id=report_id,
        note=f"Admin xử lý báo cáo: {payload.action_taken}"
    )
    return {"status": "success", "message": f"Đã xử lý báo cáo thành {new_status}"}

@router.patch("/moderation/jobs/{job_id}/suspend", dependencies=[Depends(require_admin)])
async def suspend_job(
    job_id: str,
    reason: str = Body(..., embed=True),
    current_admin: CurrentUser = Depends(require_admin)
):
    job = await JobRepository.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy việc làm")
        
    await JobRepository.update(job_id, {"status": JobStatus.CLOSED.value, "is_suspended": True})
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.JOB_SUSPENDED,
        target_type="job",
        target_id=job_id,
        note=f"Admin KHÓA việc làm vi phạm. Lý do: {reason}"
    )
    return {"status": "success", "message": "Đã khóa chiến dịch tuyển dụng vi phạm"}

@router.get("/support-tickets", dependencies=[Depends(require_admin)])
async def get_support_tickets(
    status: Optional[TicketStatus] = None,
    category: Optional[str] = None
):
    query = {}
    if status:
        query["status"] = status.value
    if category:
        query["category"] = category
        
    tickets = await SupportTicketRepository.find_many(query, sort=[("created_at", -1)], limit=200)
    for t in tickets:
        t["id"] = str(t["_id"])
        del t["_id"]
    return {"status": "success", "data": tickets}

@router.patch("/support-tickets/{ticket_id}/resolve", dependencies=[Depends(require_admin)])
async def resolve_support_ticket(
    ticket_id: str,
    payload: SupportTicketResolve,
    background_tasks: BackgroundTasks,
    current_admin: CurrentUser = Depends(require_admin)
):
    ticket = await SupportTicketRepository.get_by_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Không tìm thấy Ticket")
        
    update_data = {
        "status": payload.status.value,
        "admin_notes": payload.admin_notes,
        "updated_at": datetime.now(timezone.utc)
    }
    
    if payload.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
        update_data["resolved_by_admin_id"] = current_admin.id
        update_data["resolved_at"] = datetime.now(timezone.utc)
        
    await SupportTicketRepository.update(ticket_id, update_data)
    
    if payload.reply_message and ticket.get("email"):
        update_data["reply_message"] = payload.reply_message
        send_ticket_reply_email(
            background_tasks=background_tasks,
            to=ticket.get("email"),
            name=ticket.get("full_name", "Khách hàng"),
            ticket_subject=ticket.get("subject", "Không có tiêu đề"),
            ticket_id=ticket_id,
            reply_message=payload.reply_message
        )
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.TICKET_STATUS_UPDATED,
        target_type="support_ticket",
        target_id=ticket_id,
        note=f"Admin cập nhật trạng thái Ticket thành {payload.status.value}"
    )
    return {"status": "success", "message": f"Đã cập nhật Ticket thành {payload.status.value}"}

def generate_slug(text: str) -> str:
    unaccented = unidecode.unidecode(text).lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', unaccented)
    slug = re.sub(r'[\s-]+', '-', slug).strip('-')
    return slug

def calculate_reading_time(html_content: str) -> int:
    clean_text = re.sub(r'<[^>]+>', ' ', html_content)
    words = len(clean_text.split())
    minutes = math.ceil(words / 200)
    return max(1, minutes)

@router.post("/blogs", dependencies=[Depends(require_admin)])
async def create_blog_post(
    payload: BlogCreate,
    current_admin: CurrentUser = Depends(require_admin)
):
    base_slug = generate_slug(payload.title)
    slug = base_slug
    counter = 1
    
    while await BlogRepository.find_one({"slug": slug}):
        slug = f"{base_slug}-{counter}"
        counter += 1
        
    reading_time = calculate_reading_time(payload.content_html)
    
    record = payload.model_dump()
    record.update({
        "slug": slug,
        "reading_time_minutes": reading_time,
        "view_count": 0,
        "created_by_admin_id": current_admin.id,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })
    
    _id = await BlogRepository.create(record)
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.BLOG_CREATED,
        target_type="blog_post",
        target_id=str(_id),
        note=f"Admin đăng bài viết: {payload.title}"
    )
    return {"status": "success", "message": "Đăng bài viết thành công", "id": str(_id)}

@router.patch("/blogs/{blog_id}", dependencies=[Depends(require_admin)])
async def update_blog_post(
    blog_id: str,
    payload: BlogUpdate,
    current_admin: CurrentUser = Depends(require_admin)
):
    existing = await BlogRepository.get_by_id(blog_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài viết")
        
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return {"status": "success", "message": "Không có dữ liệu cập nhật"}
        
    if "title" in update_data and update_data["title"] != existing.get("title"):
        base_slug = generate_slug(update_data["title"])
        slug = base_slug
        counter = 1
        while await BlogRepository.find_one({"slug": slug, "_id": {"$ne": ObjectId(blog_id)}}):
            slug = f"{base_slug}-{counter}"
            counter += 1
        update_data["slug"] = slug
        
    if "content_html" in update_data:
        update_data["reading_time_minutes"] = calculate_reading_time(update_data["content_html"])
        
    update_data["updated_at"] = datetime.now(timezone.utc)
    await BlogRepository.update(blog_id, update_data)
    
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.BLOG_UPDATED,
        target_type="blog_post",
        target_id=blog_id,
        note="Admin cập nhật bài viết"
    )
    return {"status": "success", "message": "Cập nhật bài viết thành công"}

@router.delete("/blogs/{blog_id}", dependencies=[Depends(require_admin)])
async def delete_blog_post(
    blog_id: str,
    current_admin: CurrentUser = Depends(require_admin)
):
    deleted = await BlogRepository.delete(blog_id, hard_delete=True)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài viết")
        
    await log_action(
        actor_id=current_admin.id,
        actor_role=current_admin.role,
        action=AuditAction.BLOG_DELETED,
        target_type="blog_post",
        target_id=blog_id,
        note="Admin xóa bài viết"
    )
    return {"status": "success", "message": "Đã xóa bài viết"}
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body, Query, BackgroundTasks
from pydantic import BaseModel, Field, EmailStr

from app.core.security import CurrentUser, require_admin
from app.schemas.common_schema import UserRole, ReportStatus, TicketStatus
from app.schemas.company_schema import CompanyVerifyAction
from app.schemas.subscription_plan_schema import SubscriptionPlanCreate, SubscriptionPlanUpdate
from app.schemas.skill_schema import SkillCreate, SkillUpdate
from app.schemas.administrative_unit_schema import AdministrativeUnitCreate
from app.schemas.report_schema import ReportResolve
from app.schemas.support_ticket_schema import SupportTicketResolve
from app.schemas.blog_schema import BlogCreate, BlogUpdate

from app.services.analytics_service import AnalyticsService
from app.services.domain.admin_service import AdminService

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

# ---------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------
class BootstrapRequest(BaseModel):
    secret: str = Field(..., description="Mã bảo mật lấy từ biến môi trường")
    email: EmailStr = Field(..., description="Email của tài khoản cần thăng cấp Admin")

class UpdateRoleRequest(BaseModel):
    role: UserRole = Field(..., description="Phân quyền mới")

class UpdateUserStatusRequest(BaseModel):
    is_active: bool = Field(..., description="Trạng thái khóa/mở khóa tài khoản")

class TogglePlanStatusRequest(BaseModel):
    is_active: bool = Field(..., description="Trạng thái Ẩn/Hiện gói cước")

class SystemSettingsUpdate(BaseModel):
    industry_weights: Optional[dict] = None
    action_costs: Optional[dict] = None
    payment_config: Optional[dict] = None

class AdministrativeUnitUpdate(BaseModel):
    name: Optional[str] = None
    parent_code: Optional[str] = None
    version: Optional[str] = None

# ==========================================
# SYSTEM BOOTSTRAP
# ==========================================
@router.post("/bootstrap")
async def bootstrap_admin(payload: BootstrapRequest):
    raise HTTPException(
        status_code=410, 
        detail="API Bootstrap đã bị vô hiệu hóa vĩnh viễn trên môi trường Production để đảm bảo an toàn hệ thống."
    )

# ==========================================
# USER MANAGEMENT
# ==========================================
@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users():
    return await AdminService.list_users()

@router.patch("/users/{user_id}/role")
async def update_user_role(user_id: str, payload: UpdateRoleRequest, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.update_user_role(user_id, payload, current_admin)

@router.patch("/users/{user_id}/status")
async def update_user_status(user_id: str, payload: UpdateUserStatusRequest, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.update_user_status(user_id, payload, current_admin)

# ==========================================
# COMPANY MANAGEMENT & KYC
# ==========================================
@router.get("/companies", dependencies=[Depends(require_admin)])
async def list_companies(status: Optional[str] = None):
    companies = await AdminService.list_companies(status)
    for comp in companies:
        if "current_plan_id" in comp and comp["current_plan_id"] is not None:
            comp["current_plan_id"] = str(comp["current_plan_id"])
    return companies

@router.patch("/companies/{company_id}/verify")
async def verify_company(
    company_id: str, 
    action: CompanyVerifyAction,
    current_admin: CurrentUser = Depends(require_admin)
):
    return await AdminService.verify_company(company_id, action, current_admin)

@router.patch("/companies/{company_id}")
async def admin_update_company(
    company_id: str,
    update_data: dict = Body(...),
    current_admin: CurrentUser = Depends(require_admin)
):
    return await AdminService.admin_update_company(company_id, update_data, current_admin)

# ==========================================
# AUDIT LOGS
# ==========================================
@router.get("/audit-logs", dependencies=[Depends(require_admin)])
async def get_audit_logs(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=100, description="Số lượng record mỗi trang"),
    action: Optional[str] = Query(None, description="Lọc theo loại hành động"),
    actor_id: Optional[str] = Query(None, description="Lọc theo ID người thực hiện"),
    start_date: Optional[datetime] = Query(None, description="Từ ngày"),
    end_date: Optional[datetime] = Query(None, description="Đến ngày")
):
    return await AdminService.get_audit_logs(page, page_size, action, actor_id, start_date, end_date)

# ==========================================
# ANALYTICS & METRICS
# ==========================================
@router.get("/dashboard/metrics", dependencies=[Depends(require_admin)])
async def get_admin_dashboard():
    data = await AnalyticsService.get_admin_dashboard_metrics()
    return {"status": "success", "data": data}

@router.get("/analytics", dependencies=[Depends(require_admin)])
async def get_admin_analytics():
    data = await AnalyticsService.get_admin_system_analytics()
    return {"status": "success", "data": data}

# ==========================================
# SUBSCRIPTION PLANS
# ==========================================
@router.post("/subscriptions/plans", dependencies=[Depends(require_admin)])
async def create_subscription_plan(payload: SubscriptionPlanCreate, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.create_subscription_plan(payload, current_admin)

@router.patch("/subscriptions/plans/{plan_id}", dependencies=[Depends(require_admin)])
async def update_subscription_plan(plan_id: str, payload: SubscriptionPlanUpdate, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.update_subscription_plan(plan_id, payload, current_admin)

@router.patch("/subscriptions/plans/{plan_id}/status", dependencies=[Depends(require_admin)])
async def toggle_subscription_plan_status(plan_id: str, payload: TogglePlanStatusRequest, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.toggle_subscription_plan_status(plan_id, payload, current_admin)

# ==========================================
# SYSTEM SETTINGS & MASTER DATA
# ==========================================
@router.get("/system/settings", dependencies=[Depends(require_admin)])
async def get_system_settings():
    return await AdminService.get_system_settings()

@router.put("/system/settings", dependencies=[Depends(require_admin)])
async def update_system_settings(payload: SystemSettingsUpdate, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.update_system_settings(payload, current_admin)

@router.post("/system/skills", dependencies=[Depends(require_admin)])
async def create_skill(payload: SkillCreate, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.create_skill(payload, current_admin)

@router.patch("/system/skills/{skill_id}", dependencies=[Depends(require_admin)])
async def update_skill(skill_id: str, payload: SkillUpdate, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.update_skill(skill_id, payload, current_admin)

@router.delete("/system/skills/{skill_id}", dependencies=[Depends(require_admin)])
async def delete_skill(skill_id: str, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.delete_skill(skill_id, current_admin)

@router.post("/system/locations", dependencies=[Depends(require_admin)])
async def create_location(payload: AdministrativeUnitCreate, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.create_location(payload, current_admin)

@router.patch("/system/locations/{location_id}", dependencies=[Depends(require_admin)])
async def update_location(location_id: str, payload: AdministrativeUnitUpdate, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.update_location(location_id, payload, current_admin)

@router.delete("/system/locations/{location_id}", dependencies=[Depends(require_admin)])
async def delete_location(location_id: str, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.delete_location(location_id, current_admin)

# ==========================================
# MODERATION & REPORTS
# ==========================================
@router.get("/reports", dependencies=[Depends(require_admin)])
async def get_reports(status: Optional[ReportStatus] = None, target_type: Optional[str] = None):
    return await AdminService.get_reports(status.value if status else None, target_type)

@router.patch("/reports/{report_id}/resolve", dependencies=[Depends(require_admin)])
async def resolve_report(report_id: str, payload: ReportResolve, action: str = Query(..., description="Duyệt (resolve) hoặc Từ chối (reject)"), current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.resolve_report(report_id, payload, action, current_admin)

@router.patch("/moderation/jobs/{job_id}/suspend", dependencies=[Depends(require_admin)])
async def suspend_job(job_id: str, reason: str = Body(..., embed=True), current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.suspend_job(job_id, reason, current_admin)

# ==========================================
# SUPPORT TICKETS
# ==========================================
@router.get("/support-tickets", dependencies=[Depends(require_admin)])
async def get_support_tickets(status: Optional[TicketStatus] = None, category: Optional[str] = None):
    return await AdminService.get_support_tickets(status.value if status else None, category)

@router.patch("/support-tickets/{ticket_id}/resolve", dependencies=[Depends(require_admin)])
async def resolve_support_ticket(ticket_id: str, payload: SupportTicketResolve, background_tasks: BackgroundTasks, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.resolve_support_ticket(ticket_id, payload, background_tasks, current_admin)

# ==========================================
# BLOG & CONTENT
# ==========================================
@router.post("/blogs", dependencies=[Depends(require_admin)])
async def create_blog_post(payload: BlogCreate, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.create_blog_post(payload, current_admin)

@router.patch("/blogs/{blog_id}", dependencies=[Depends(require_admin)])
async def update_blog_post(blog_id: str, payload: BlogUpdate, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.update_blog_post(blog_id, payload, current_admin)

@router.delete("/blogs/{blog_id}", dependencies=[Depends(require_admin)])
async def delete_blog_post(blog_id: str, current_admin: CurrentUser = Depends(require_admin)):
    return await AdminService.delete_blog_post(blog_id, current_admin)
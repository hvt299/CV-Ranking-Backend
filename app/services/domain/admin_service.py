from datetime import datetime, timezone
import re
import math
import unidecode
from bson import ObjectId
from fastapi import HTTPException, BackgroundTasks

from app.schemas.common_schema import (
    CompanyStatus, AuditAction, NotificationType, NotificationActorType, 
    NotificationActionType, NotificationReadStatus, ReportStatus, 
    JobStatus, TicketStatus
)
from app.repositories.user_repository import UserRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.job_repository import JobRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.repositories.skill_repository import SkillRepository
from app.repositories.administrative_unit_repository import AdministrativeUnitRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.support_ticket_repository import SupportTicketRepository
from app.repositories.blog_repository import BlogRepository

from app.services.audit_service import log_action
from app.services.nlp_engine import refresh_system_settings, initialize_skill_map
from app.services.email_service import send_ticket_reply_email
from app.database.config import db_instance


class AdminService:
    
    # ==========================================
    # USER MANAGEMENT
    # ==========================================
    @staticmethod
    async def list_users():
        projection = {
            "hashed_password": 0, 
            "reset_password_token": 0, 
            "reset_password_expires": 0
        }
        users = await UserRepository.find_many({}, projection=projection, limit=500)
        return users

    @staticmethod
    async def update_user_role(user_id: str, payload, current_admin):
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

    @staticmethod
    async def update_user_status(user_id: str, payload, current_admin):
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

    # ==========================================
    # COMPANY MANAGEMENT & KYC
    # ==========================================
    @staticmethod
    async def list_companies(status: str = None):
        query = {}
        if status:
            query["status"] = status
            
        companies = await CompanyRepository.find_many(query, limit=500)
        return companies

    @staticmethod
    async def verify_company(company_id: str, action, current_admin):
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

    @staticmethod
    async def admin_update_company(company_id: str, update_data: dict, current_admin):
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

    # ==========================================
    # AUDIT LOGS
    # ==========================================
    @staticmethod
    async def get_audit_logs(page: int, page_size: int, action: str = None, actor_id: str = None, start_date=None, end_date=None):
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
            lg["id"] = lg.get("id") or str(lg.pop("_id", ""))
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

    # ==========================================
    # SUBSCRIPTION PLANS
    # ==========================================
    @staticmethod
    async def create_subscription_plan(payload, current_admin):
        existing_plan = await SubscriptionPlanRepository.find_one({"plan_code": payload.plan_code})
        if existing_plan:
            raise HTTPException(status_code=400, detail=f"Mã định danh '{payload.plan_code}' đã tồn tại.")
            
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

    @staticmethod
    async def update_subscription_plan(plan_id: str, payload, current_admin):
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

    @staticmethod
    async def toggle_subscription_plan_status(plan_id: str, payload, current_admin):
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

    # ==========================================
    # SYSTEM SETTINGS & MASTER DATA
    # ==========================================
    @staticmethod
    async def get_system_settings():
        doc = await SystemSettingsRepository.find_one({"setting_type": "global_config"})
        if doc:
            doc["id"] = str(doc.get("id"))
            return {"status": "success", "data": doc}
        return {"status": "success", "data": {}}

    @staticmethod
    async def update_system_settings(payload, current_admin):
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
        return {"status": "success", "message": "Cập nhật cấu hình hệ thống thành công. Cache đã làm mới."}

    @staticmethod
    async def create_skill(payload, current_admin):
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

    @staticmethod
    async def update_skill(skill_id: str, payload, current_admin):
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

    @staticmethod
    async def delete_skill(skill_id: str, current_admin):
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

    @staticmethod
    async def create_location(payload, current_admin):
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

    @staticmethod
    async def update_location(location_id: str, payload, current_admin):
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

    @staticmethod
    async def delete_location(location_id: str, current_admin):
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

    # ==========================================
    # MODERATION & REPORTS
    # ==========================================
    @staticmethod
    async def get_reports(status: str = None, target_type: str = None):
        query = {}
        if status:
            query["status"] = status
        if target_type:
            query["target_type"] = target_type
            
        reports = await ReportRepository.find_many(query, sort=[("created_at", -1)], limit=200)
        return {"status": "success", "data": reports}

    @staticmethod
    async def resolve_report(report_id: str, payload, action: str, current_admin):
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

    @staticmethod
    async def suspend_job(job_id: str, reason: str, current_admin):
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

    # ==========================================
    # SUPPORT TICKETS
    # ==========================================
    @staticmethod
    async def get_support_tickets(status: str = None, category: str = None):
        query = {}
        if status:
            query["status"] = status
        if category:
            query["category"] = category
            
        tickets = await SupportTicketRepository.find_many(query, sort=[("created_at", -1)], limit=200)
        return {"status": "success", "data": tickets}

    @staticmethod
    async def resolve_support_ticket(ticket_id: str, payload, background_tasks: BackgroundTasks, current_admin):
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

    # ==========================================
    # BLOG & CONTENT
    # ==========================================
    @staticmethod
    def _generate_slug(text: str) -> str:
        unaccented = unidecode.unidecode(text).lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', unaccented)
        slug = re.sub(r'[\s-]+', '-', slug).strip('-')
        return slug

    @staticmethod
    def _calculate_reading_time(html_content: str) -> int:
        clean_text = re.sub(r'<[^>]+>', ' ', html_content)
        words = len(clean_text.split())
        minutes = math.ceil(words / 200)
        return max(1, minutes)

    @staticmethod
    async def create_blog_post(payload, current_admin):
        base_slug = AdminService._generate_slug(payload.title)
        slug = base_slug
        counter = 1
        
        while await BlogRepository.find_one({"slug": slug}):
            slug = f"{base_slug}-{counter}"
            counter += 1
            
        reading_time = AdminService._calculate_reading_time(payload.content_html)
        
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

    @staticmethod
    async def update_blog_post(blog_id: str, payload, current_admin):
        existing = await BlogRepository.get_by_id(blog_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Không tìm thấy bài viết")
            
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return {"status": "success", "message": "Không có dữ liệu cập nhật"}
            
        if "title" in update_data and update_data["title"] != existing.get("title"):
            base_slug = AdminService._generate_slug(update_data["title"])
            slug = base_slug
            counter = 1
            while await BlogRepository.find_one({"slug": slug, "_id": {"$ne": ObjectId(blog_id)}}):
                slug = f"{base_slug}-{counter}"
                counter += 1
            update_data["slug"] = slug
            
        if "content_html" in update_data:
            update_data["reading_time_minutes"] = AdminService._calculate_reading_time(update_data["content_html"])
            
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

    @staticmethod
    async def delete_blog_post(blog_id: str, current_admin):
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
from fastapi import Depends, HTTPException
from datetime import datetime, timezone

from app.core.security import require_hr, CurrentUser
from app.repositories.company_repository import CompanyRepository
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.job_repository import JobRepository
from app.repositories.cv_repository import CVRepository

async def _get_company_plan_limits(company_id: str) -> dict:
    """Helper: Lấy giới hạn gói cước hiện tại của công ty"""
    if not company_id:
        raise HTTPException(status_code=403, detail="Tài khoản chưa được liên kết với công ty nào.")

    company = await CompanyRepository.get_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu công ty.")

    # Kiểm tra hạn sử dụng (expires_at)
    expires_at = company.get("subscription_expires_at")
    if expires_at:
        # Xử lý datetime để so sánh
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(
                status_code=403, 
                detail="Gói cước của công ty đã hết hạn. Vui lòng gia hạn để tiếp tục sử dụng."
            )

    plan_id = company.get("current_plan_id")
    if not plan_id:
        # Nếu chưa có plan_id, áp dụng giới hạn của gói FREE mặc định
        return {"max_jobs_per_month": 3, "max_cv_parses_per_month": 50}

    plan = await SubscriptionPlanRepository.get_by_id(plan_id)
    if not plan:
        return {"max_jobs_per_month": 3, "max_cv_parses_per_month": 50}

    return {
        "max_jobs_per_month": plan.get("max_jobs_per_month", 3),
        "max_cv_parses_per_month": plan.get("max_cv_parses_per_month", 50)
    }

async def verify_job_quota(current_user: CurrentUser = Depends(require_hr)) -> CurrentUser:
    """Middleware: Chặn tạo Job nếu vượt quá giới hạn tháng"""
    limits = await _get_company_plan_limits(current_user.company_id)
    
    # Tính số lượng Job đã tạo trong tháng hiện tại
    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    
    job_count = await JobRepository.count_documents({
        "company_id": current_user.company_id,
        "created_at": {"$gte": start_of_month}
    })

    if job_count >= limits["max_jobs_per_month"]:
        raise HTTPException(
            status_code=403, 
            detail=f"Công ty đã đạt giới hạn tạo {limits['max_jobs_per_month']} chiến dịch trong tháng này. Vui lòng nâng cấp gói cước."
        )
        
    return current_user

async def verify_cv_quota(current_user: CurrentUser = Depends(require_hr)) -> CurrentUser:
    """Middleware: Chặn Upload/Parse CV AI nếu vượt quá giới hạn tháng"""
    limits = await _get_company_plan_limits(current_user.company_id)
    
    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    
    cv_count = await CVRepository.count_documents({
        "company_id": current_user.company_id,
        "created_at": {"$gte": start_of_month}
    })

    if cv_count >= limits["max_cv_parses_per_month"]:
        raise HTTPException(
            status_code=403, 
            detail=f"Công ty đã đạt giới hạn phân tích {limits['max_cv_parses_per_month']} CV bằng AI trong tháng này. Vui lòng nâng cấp gói cước."
        )
        
    return current_user
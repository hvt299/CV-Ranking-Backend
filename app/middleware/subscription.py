from fastapi import Depends, HTTPException
from datetime import datetime, timezone
from bson import ObjectId

from app.core.security import require_hr, CurrentUser
from app.repositories.company_repository import CompanyRepository
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.quota_transaction_repository import QuotaTransactionRepository

async def get_company_plan_features(company_id: str) -> dict:
    company = await CompanyRepository.get_by_id(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu công ty.")
        
    plan_id = company.get("current_plan_id")
    period_end = company.get("current_period_end")
    
    if period_end:
        if isinstance(period_end, str):
            period_end = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) > period_end:
            await CompanyRepository.update_custom(
                {"_id": ObjectId(company_id)},
                {
                    "$set": {
                        "current_plan_id": None, 
                        "credits_remaining": 0, 
                        "current_period_start": None,
                        "current_period_end": None
                    }
                }
            )
            
            if company.get("credits_remaining", 0) > 0:
                await QuotaTransactionRepository.create({
                    "company_id": company_id,
                    "user_id": "system",
                    "action_type": "EXPIRED_CREDIT_RECOVERY",
                    "credit_cost": company.get("credits_remaining"),
                    "balance_after": 0,
                    "created_at": datetime.now(timezone.utc)
                })
                
            plan_id = None

    if not plan_id:
        return {
            "max_active_jobs": 3, 
            "monthly_ai_credits": 0,
            "max_cv_parses_per_month": 50,
            "can_use_reverse_matching": False, 
            "can_set_hot_job": False,
            "can_export_analytics": False
        }
        
    plan = await SubscriptionPlanRepository.get_by_id(plan_id)
    return plan.get("features", {}) if plan else {}


def require_tier(feature_key: str):
    async def dependency(current_user: CurrentUser = Depends(require_hr)):
        features = await get_company_plan_features(current_user.company_id)
        if not features.get(feature_key, False):
            raise HTTPException(
                status_code=403, 
                detail=f"Gói cước hiện tại không hỗ trợ tính năng này. Vui lòng nâng cấp (Upsell)."
            )
        return current_user
    return dependency


def require_credits(action_type: str):
    async def dependency(current_user: CurrentUser = Depends(require_hr)):
        from app.services.nlp_engine import GLOBAL_SYSTEM_SETTINGS
        
        # Bắt buộc đọc từ DB/Memory
        actual_cost = GLOBAL_SYSTEM_SETTINGS.get("action_costs", {}).get(action_type)
        if actual_cost is None:
            raise HTTPException(
                status_code=503, 
                detail=f"Hệ thống đang thiếu cấu hình bảng giá cho '{action_type}'. Chưa thể thực hiện lúc này."
            )

        success = await CompanyRepository.deduct_ai_credits(current_user.company_id, actual_cost)
        if not success:
            raise HTTPException(
                status_code=402, 
                detail=f"Tài khoản không đủ Credit AI (cần {actual_cost} credits cho {action_type}). Vui lòng nạp thêm."
            )
            
        company = await CompanyRepository.get_by_id(current_user.company_id)
        await QuotaTransactionRepository.create({
            "company_id": current_user.company_id,
            "user_id": current_user.id,
            "action_type": action_type,
            "credit_cost": actual_cost,
            "balance_after": company.get("credits_remaining", 0),
            "created_at": datetime.now(timezone.utc)
        })
        
        return current_user
    return dependency
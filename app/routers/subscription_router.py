from fastapi import APIRouter, Depends, HTTPException, Request
from app.middleware.rate_limit import limiter
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import re
import os

from app.core.security import get_current_user, CurrentUser, require_hr
from app.schemas.common_schema import UserRole
from app.schemas.subscription_plan_schema import TargetAudience
from app.repositories.subscription_plan_repository import SubscriptionPlanRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.applicant_profile_repository import ApplicantProfileRepository
from app.repositories.quota_transaction_repository import QuotaTransactionRepository

router = APIRouter(prefix="/api/v1/subscriptions", tags=["Billing & Subscriptions"])

@router.get("/plans")
async def get_active_plans(target: TargetAudience):
    plans = await SubscriptionPlanRepository.find_many({
        "target_audience": target.value,
        "is_active": True
    }, sort=[("current_price", 1)])
    
    result = []
    for p in plans:
        p["id"] = str(p["_id"])
        del p["_id"]
        result.append(p)
    return {"status": "success", "data": result}

@router.get("/my-plan")
async def get_my_plan(current_user: CurrentUser = Depends(get_current_user)):
    plan_info = None
    if current_user.role in [UserRole.HR_OWNER.value, UserRole.HR_MEMBER.value]:
        company = await CompanyRepository.get_by_id(current_user.company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Không tìm thấy công ty")
            
        plan_id = company.get("current_plan_id")
        plan_data = await SubscriptionPlanRepository.get_by_id(plan_id) if plan_id else None
        
        plan_info = {
            "entity_type": "company",
            "entity_id": current_user.company_id,
            "current_plan": plan_data.get("name") if plan_data else "Gói Miễn phí (Free)",
            "current_plan_code": plan_data.get("plan_code") if plan_data else "free",
            "credits_remaining": company.get("credits_remaining", 0),
            "period_start": company.get("current_period_start"),
            "period_end": company.get("current_period_end")
        }
        
    elif current_user.role == UserRole.APPLICANT.value:
        profile = await ApplicantProfileRepository.get_by_user_id(current_user.id)
        if not profile:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ ứng viên")
            
        plan_id = profile.get("current_plan_id")
        plan_data = await SubscriptionPlanRepository.get_by_id(plan_id) if plan_id else None

        plan_info = {
            "entity_type": "applicant",
            "entity_id": current_user.id,
            "current_plan": plan_data.get("name") if plan_data else "Gói Miễn phí (Free)",
            "current_plan_code": plan_data.get("plan_code") if plan_data else "free",
            "credits_remaining": profile.get("credits_remaining", 0),
            "period_start": profile.get("current_period_start"),
            "period_end": profile.get("current_period_end")
        }

    return {"status": "success", "data": plan_info}

@router.post("/checkout/{plan_code}")
@limiter.limit("20/day")
async def create_checkout_session(request: Request, plan_code: str, current_user: CurrentUser = Depends(require_hr)):
    plan = await SubscriptionPlanRepository.find_one({"plan_code": plan_code, "is_active": True})
    if not plan:
        raise HTTPException(status_code=404, detail="Gói cước không tồn tại hoặc đã ngừng bán")
        
    company = await CompanyRepository.get_by_id(current_user.company_id)
    current_plan_id = company.get("current_plan_id")
    
    if current_plan_id:
        current_plan = await SubscriptionPlanRepository.get_by_id(current_plan_id)
        if current_plan and current_plan.get("current_price", 0) > plan.get("current_price", 0):
            raise HTTPException(
                status_code=400, 
                detail="Hệ thống không hỗ trợ giáng cấp (Downgrade) giữa chu kỳ. Vui lòng đợi gói hiện tại hết hạn."
            )

    transfer_content = f"UPGRADE {current_user.company_id} {plan_code}".upper()
    amount = plan.get("current_price", 0)
    
    return {
        "status": "success",
        "data": {
            "amount": amount,
            "transfer_content": transfer_content,
            "bank_account": "123456789",
            "bank_name": "Vietcombank",
            "account_name": "CTY TNHH CV RANKING",
            "qr_url": f"https://img.vietqr.io/image/vcb-123456789-compact.png?amount={amount}&addInfo={transfer_content}&accountName=CV%20RANKING"
        }
    }

@router.post("/webhook/sepay")
async def sepay_webhook(request: Request):
    sepay_token = os.getenv("SEPAY_WEBHOOK_TOKEN", "")
    auth_header = request.headers.get("Authorization", "")
    
    if sepay_token and auth_header != f"Bearer {sepay_token}" and auth_header != f"Apikey {sepay_token}":
        raise HTTPException(status_code=401, detail="Xác thực Webhook thất bại. Request không hợp lệ.")

    payload = await request.json()
    
    if payload.get("transferType") != "in":
        return {"status": "ignored", "message": "Chỉ xử lý tiền vào"}
        
    amount_paid = payload.get("transferAmount", 0)
    content = payload.get("transactionContent", "").upper()

    match = re.search(r"UPGRADE\s+([A-F0-9]{24})\s+([A-Z0-9_]+)", content)
    if not match:
        return {"status": "ignored", "message": "Cú pháp chuyển khoản không hợp lệ"}
        
    company_id = match.group(1).lower()
    plan_code = match.group(2).lower()
    
    plan = await SubscriptionPlanRepository.find_one({"plan_code": plan_code})
    if not plan:
        return {"status": "ignored", "message": "Mã gói cước không tồn tại"}
        
    if amount_paid < plan.get("current_price", 0):
        return {"status": "ignored", "message": "Số tiền chuyển không đủ mua gói"}

    company = await CompanyRepository.get_by_id(company_id)
    if not company:
        return {"status": "ignored", "message": "Không tìm thấy công ty"}

    now = datetime.now(timezone.utc)
    new_period_start = now
    new_period_end = now + timedelta(days=plan.get("billing_cycle_days", 30))
    
    features = plan.get("features", {})
    granted_credits = features.get("monthly_ai_credits", 0)

    await CompanyRepository.update_custom(
        {"_id": ObjectId(company_id)},
        {
            "$set": {
                "current_plan_id": str(plan["_id"]),
                "current_period_start": new_period_start,
                "current_period_end": new_period_end
            },
            "$inc": {
                "credits_remaining": granted_credits
            }
        }
    )
    
    balance_after = company.get("credits_remaining", 0) + granted_credits
    await QuotaTransactionRepository.create({
        "company_id": company_id,
        "user_id": "sepay_system",
        "action_type": f"UPGRADE_{plan_code.upper()}",
        "credit_cost": -granted_credits,
        "balance_after": balance_after,
        "amount_paid": amount_paid,
        "transaction_reference": payload.get("referenceNumber"),
        "created_at": now
    })

    return {"status": "success", "message": f"Kích hoạt thành công gói {plan_code} cho công ty {company_id}"}
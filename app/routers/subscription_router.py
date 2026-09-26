from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.middleware.rate_limit import limiter
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import re
import os
import urllib.parse
from app.services.nlp_engine import GLOBAL_SYSTEM_SETTINGS

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
    return {"status": "success", "data": plans}

@router.get("/my-plan")
async def get_my_plan(current_user: CurrentUser = Depends(get_current_user)):
    if current_user.role == UserRole.ADMIN.value:
        return {"status": "success", "data": {
            "entity_type": "admin",
            "entity_id": current_user.id,
            "current_plan": "Quản trị viên (Unlimited)",
            "current_plan_code": "admin_vip",
            "credits_remaining": 9999999,
            "period_start": None,
            "period_end": None
        }}

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
            "current_plan": plan_data.get("name") if plan_data else "HR Cơ bản",
            "current_plan_code": plan_data.get("plan_code") if plan_data else "hr_free",
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
            "current_plan": plan_data.get("name") if plan_data else "Ứng viên Cơ bản",
            "current_plan_code": plan_data.get("plan_code") if plan_data else "app_free",
            "credits_remaining": profile.get("credits_remaining", 0),
            "period_start": profile.get("current_period_start"),
            "period_end": profile.get("current_period_end")
        }

    return {"status": "success", "data": plan_info}

@router.get("/transactions")
async def get_transactions(current_user: CurrentUser = Depends(get_current_user)):
    query = {}
    if current_user.role in [UserRole.HR_OWNER.value, UserRole.HR_MEMBER.value]:
        query["company_id"] = current_user.company_id
    else:
        query["user_id"] = current_user.id
        
    transactions = await QuotaTransactionRepository.find_many(query, sort=[("created_at", -1)], limit=100)
    
    for tx in transactions:
        tx["id"] = tx.get("id") or str(tx.pop("_id", ""))
        
    return {"status": "success", "data": transactions}

@router.post("/checkout/{plan_code}")
@limiter.limit("20/day")
# Bỏ require_hr để Applicant cũng được phép gọi API này tạo mã QR
async def create_checkout_session(request: Request, response: Response, plan_code: str, current_user: CurrentUser = Depends(get_current_user)):
    plan = await SubscriptionPlanRepository.find_one({"plan_code": plan_code, "is_active": True})
    if not plan:
        raise HTTPException(status_code=404, detail="Gói cước không tồn tại hoặc đã ngừng bán")
    
    # Validation cơ bản
    target_audience = plan.get("target_audience")
    if target_audience == "hr" and current_user.role not in [UserRole.HR_OWNER.value, UserRole.HR_MEMBER.value]:
        raise HTTPException(status_code=403, detail="Gói cước này chỉ dành cho Doanh nghiệp")
    if target_audience == "applicant" and current_user.role != UserRole.APPLICANT.value:
        raise HTTPException(status_code=403, detail="Gói cước này chỉ dành cho Ứng viên")
        
    # Logic kiểm tra Hạ cấp (Downgrade) dựa trên tier_level
    current_plan_id = None
    current_period_end = None
    
    if target_audience == "hr":
        entity = await CompanyRepository.get_by_id(current_user.company_id)
    else:
        entity = await ApplicantProfileRepository.get_by_user_id(current_user.id)
        
    if entity:
        current_plan_id = entity.get("current_plan_id")
        current_period_end = entity.get("current_period_end")
        
    if current_plan_id and current_period_end:
        if isinstance(current_period_end, str):
            current_period_end = datetime.fromisoformat(current_period_end.replace("Z", "+00:00"))
        if current_period_end.tzinfo is None:
            current_period_end = current_period_end.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) < current_period_end:
            current_plan = await SubscriptionPlanRepository.get_by_id(current_plan_id)
            if current_plan:
                old_tier = current_plan.get("tier_level", 0)
                new_tier = plan.get("tier_level", 0)
                
                if new_tier < old_tier:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Không thể hạ cấp (Downgrade) do gói hiện tại vẫn còn hạn sử dụng. Vui lòng chờ gói cũ hết hạn để mua gói này."
                    )

    payment_config = GLOBAL_SYSTEM_SETTINGS.get("payment_config", {})
    bank_id = payment_config.get("bank_id", "MB")
    account_no = payment_config.get("account_no", "0123456789")
    account_name = payment_config.get("account_name", "CONG TY ATS")
    template = payment_config.get("template", "compact2")
    
    # ID Đích: HR dùng Company ID, Applicant dùng User ID
    target_id = current_user.company_id if target_audience == "hr" else current_user.id
    transfer_content = f"UPGRADE {target_id} {plan_code}".upper()
    amount = plan.get("current_price", 0)
    
    encoded_content = urllib.parse.quote(transfer_content)
    encoded_name = urllib.parse.quote(account_name)
    # Gắn biến template vào đường dẫn
    qr_url = f"https://img.vietqr.io/image/{bank_id}-{account_no}-{template}.png?amount={amount}&addInfo={encoded_content}&accountName={encoded_name}"
    
    return {
        "status": "success",
        "data": {
            "amount": amount,
            "transfer_content": transfer_content,
            "bank_account": account_no,
            "bank_name": bank_id,
            "account_name": account_name,
            "qr_url": qr_url
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

    target_id = match.group(1).lower()
    target_audience = plan.get("target_audience")
    
    now = datetime.now(timezone.utc)
    cycle_days = plan.get("billing_cycle_days", 30)
    new_period_end = None if cycle_days == 0 else (now + timedelta(days=cycle_days))
    features = plan.get("features", {})

    if target_audience == "hr":
        company = await CompanyRepository.get_by_id(target_id)
        if not company: return {"status": "ignored", "message": "Không tìm thấy công ty"}
        
        granted_credits = features.get("monthly_ai_credits", 0)
        await CompanyRepository.update_custom(
            {"_id": ObjectId(target_id)},
            {
                "$set": {"current_plan_id": str(plan.get("id")), "current_period_start": now, "current_period_end": new_period_end},
                "$inc": {"credits_remaining": granted_credits}
            }
        )
        balance_after = company.get("credits_remaining", 0) + granted_credits
        await QuotaTransactionRepository.create({
            "company_id": target_id,
            "user_id": "sepay_system",
            "action_type": f"UPGRADE_{plan_code.upper()}",
            "credit_cost": -granted_credits,
            "balance_after": balance_after,
            "created_at": now
        })
        
    elif target_audience == "applicant":
        profile = await ApplicantProfileRepository.get_by_user_id(target_id)
        if not profile: return {"status": "ignored", "message": "Không tìm thấy hồ sơ ứng viên"}
        
        granted_credits = features.get("ai_credits", 0)
        await ApplicantProfileRepository.update_custom(
            {"_id": ObjectId(profile.get("id"))},
            {
                "$set": {"current_plan_id": str(plan.get("id")), "current_period_start": now, "current_period_end": new_period_end},
                "$inc": {"credits_remaining": granted_credits}
            }
        )
        balance_after = profile.get("credits_remaining", 0) + granted_credits
        await QuotaTransactionRepository.create({
            "company_id": None,
            "user_id": target_id,
            "action_type": f"UPGRADE_{plan_code.upper()}",
            "credit_cost": -granted_credits,
            "balance_after": balance_after,
            "created_at": now
        })

    return {"status": "success", "message": f"Kích hoạt thành công gói {plan_code}"}
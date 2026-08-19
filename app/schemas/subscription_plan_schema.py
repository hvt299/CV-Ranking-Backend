from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from enum import Enum
from datetime import datetime
from app.schemas.common_schema import CurrencyEnum, QuotaActionType, DiscountType

class TargetAudience(str, Enum):
    HR = "hr"
    APPLICANT = "applicant"

class HRFeatures(BaseModel):
    max_active_jobs: int = Field(default=3, description="Số lượng Job tối đa mở cùng lúc")
    monthly_ai_credits: int = Field(default=50, description="Credit AI để săn ứng viên/sinh câu hỏi")
    max_cv_parses_per_month: int = Field(default=50, description="Giới hạn parse CV do HR tự upload")
    can_use_reverse_matching: bool = Field(default=False, description="Tính năng Săn ứng viên")
    can_set_hot_job: bool = Field(default=False)
    can_export_analytics: bool = Field(default=False)

class ApplicantFeatures(BaseModel):
    max_cv_uploads: int = Field(default=3, description="Số lượng CV tối đa lưu trong Library")
    max_job_applies_per_day: int = Field(default=10, description="Chống rải thảm (Spam Apply)")
    max_self_scores_per_day: int = Field(default=3, description="Chống lạm dụng AI Self-Score")
    ai_credits: int = Field(default=10, description="Dùng cho tính năng Premium như: AI Viết lại CV")

class SubscriptionPlanCreate(BaseModel):
    plan_code: str = Field(..., description="VD: hr_free, hr_pro, app_free, app_premium")
    name: str = Field(...)
    description: Optional[str] = Field(default=None, description="Mô tả ngắn, VD: Dành cho doanh nghiệp SMEs")
    badge: Optional[str] = Field(default=None, description="Nhãn dán góc, VD: Phổ biến nhất")
    display_order: int = Field(default=0, description="Thứ tự hiển thị trên UI")
    target_audience: TargetAudience = Field(...)
    
    original_price: int = Field(default=0, ge=0)
    current_price: int = Field(default=0, ge=0, description="Giá thực thu (sau giảm giá)")
    currency: CurrencyEnum = Field(default=CurrencyEnum.VND)
    billing_cycle_days: int = Field(default=30, description="Số ngày của chu kỳ (30, 365)")
    
    features: Dict = Field(default_factory=dict, description="Dùng cho Backend Logic")
    display_features: List[str] = Field(default_factory=list, description="Danh sách text render dấu tick trên UI")
    is_active: bool = Field(default=True)

class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    badge: Optional[str] = None
    display_order: Optional[int] = None
    original_price: Optional[int] = Field(None, ge=0)
    current_price: Optional[int] = Field(None, ge=0)
    features: Optional[Dict] = None
    display_features: Optional[List[str]] = None
    is_active: Optional[bool] = None

class PromotionCreate(BaseModel):
    code: str = Field(..., description="Mã giảm giá, VD: TET2026")
    discount_type: DiscountType
    discount_value: int = Field(..., description="Giá trị giảm (VD: 50% hoặc 500000 VNĐ)")
    max_uses: Optional[int] = Field(default=None, description="Giới hạn số lượt dùng")
    used_count: int = Field(default=0)
    applicable_plan_ids: List[str] = Field(default_factory=list, description="Danh sách ID gói cước được áp dụng")
    expires_at: Optional[datetime] = None
    is_active: bool = Field(default=True)

class PromotionUpdate(BaseModel):
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[int] = None
    max_uses: Optional[int] = None
    applicable_plan_ids: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None

class QuotaTransaction(BaseModel):
    company_id: str
    user_id: str
    action_type: QuotaActionType = Field(..., description="Chuẩn hóa bằng Enum")
    credit_cost: int = Field(..., description="Số credit bị trừ")
    balance_after: int = Field(..., description="Số dư còn lại")
    created_at: datetime = Field(default_factory=datetime.utcnow)
from pydantic import BaseModel, Field
from typing import Optional, Dict

class SubscriptionPlanCreate(BaseModel):
    plan_code: str = Field(..., description="Slug định danh (VD: free, pro, enterprise)")
    name: str = Field(..., description="Tên gói hiển thị (VD: Gói Doanh nghiệp)")
    price: int = Field(default=0, ge=0)
    currency: str = Field(default="VND")
    billing_cycle: str = Field(default="monthly", description="monthly | yearly")
    features: Dict = Field(default_factory=dict, description="Cấu hình giới hạn")
    is_active: bool = Field(default=True)

class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = Field(default=None, ge=0)
    features: Optional[Dict] = None
    is_active: Optional[bool] = None
from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime
from app.schemas.common_schema import utc_now

class SubscriptionPlanDB(BaseModel):
    id: str
    plan_code: str = Field(..., description="Slug định danh (VD: free, pro, enterprise)")
    name: str = Field(..., description="Tên gói hiển thị (VD: Gói Doanh nghiệp)")
    price: int = Field(default=0, description="Giá tiền")
    currency: str = Field(default="VND")
    billing_cycle: str = Field(default="monthly", description="monthly | yearly")
    
    features: Dict = Field(
        default_factory=dict, 
        description="VD: {'ai_credits': 100, 'max_active_jobs': 5}"
    )
    is_active: bool = Field(default=True, description="Ẩn/Hiện trên trang Bảng giá")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
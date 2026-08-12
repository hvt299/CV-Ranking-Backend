from pydantic import BaseModel, Field
from typing import Optional

class KYCDocument(BaseModel):
    document_type: str = Field(..., description="Loại giấy tờ (VD: Giấy phép KD, CCCD)")
    file_url: str = Field(..., description="URL file trên Cloudinary")

class LocationDetail(BaseModel):
    country: str = Field(default="Việt Nam")
    
    version: str = Field(
        default="new",
        description="Phiên bản dữ liệu địa giới hành chính ('old' hoặc 'new')"
    )
    
    province_code: Optional[str] = None
    province_name: Optional[str] = None
    ward_code: Optional[str] = None
    ward_name: Optional[str] = None
    district_code: Optional[str] = None   
    district_name: Optional[str] = None
    street_address: Optional[str] = None  
    full_address_snapshot: Optional[str] = None
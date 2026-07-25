from pydantic import BaseModel, Field
from typing import Optional

class KYCDocument(BaseModel):
    document_type: str = Field(..., description="Loại giấy tờ (VD: Giấy phép KD, CCCD)")
    file_url: str = Field(..., description="URL file trên Cloudinary")

class LocationDetail(BaseModel):
    country: str = Field(default="Việt Nam")
    
    administrative_region_version: str = Field(
        default="post_2025",
        description="Phiên bản dữ liệu (VD: 'pre_2025' cho 3 cấp cũ, 'post_2025' cho 2 cấp mới)"
    )
    
    province_code: Optional[str] = None
    province_name: Optional[str] = None
    ward_code: Optional[str] = None
    ward_name: Optional[str] = None
    district_code: Optional[str] = None   
    district_name: Optional[str] = None
    street_address: Optional[str] = None  
    full_address_snapshot: Optional[str] = None
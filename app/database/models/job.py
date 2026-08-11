from pydantic import Field
from typing import Optional, List
from datetime import datetime
from app.schemas.common_schema import utc_now, JobStatus
from app.schemas.job_schema import JobCreateEnterprise

class JobDB(JobCreateEnterprise):
    id: str
    slug: str = Field(..., description="SEO URL (VD: /careers/senior-backend-dev-abc123)")
    status: JobStatus = Field(default=JobStatus.DRAFT)
    created_by_user_id: str
    
    is_hot_until: Optional[datetime] = Field(default=None, description="Hạn hết hot")
    
    jd_search_text: Optional[str] = None
    jd_vector_ref: Optional[List[float]] = None
    
    view_count: int = Field(default=0)
    num_applications: int = Field(default=0)
    
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
from pydantic import Field
from typing import Optional, List
from datetime import datetime
from app.schemas.common_schema import utc_now, JobStatus
from app.schemas.job_schema import JobCreateEnterprise

class JobDB(JobCreateEnterprise):
    id: str
    status: JobStatus = Field(default=JobStatus.DRAFT)
    created_by_user_id: str
    jd_search_text: Optional[str] = None
    jd_vector_ref: Optional[List[float]] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
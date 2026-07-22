from pydantic import Field
from typing import Optional, List, Any
from datetime import datetime
from app.schemas.cv_schema import CVDocumentCreate
from app.schemas.common_schema import utc_now

class CVDocumentDB(CVDocumentCreate):
    id: str
    owner_user_id: str = Field(
        ...,
        description="Luôn bắt buộc — CV Library thuộc về đúng 1 Applicant"
    )
    cv_vector_ref: Optional[List[Any]] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
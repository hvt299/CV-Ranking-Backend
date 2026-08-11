from pydantic import Field
from typing import Optional, List
from datetime import datetime
from app.schemas.cv_schema import CVDocumentCreate, ParsingStatus
from app.schemas.common_schema import utc_now

class CVDocumentDB(CVDocumentCreate):
    id: str
    owner_user_id: str = Field(...)
    is_primary: bool = Field(default=False, description="CV mặc định")
    
    parsing_status: ParsingStatus = Field(default=ParsingStatus.PENDING)
    parsing_error: Optional[str] = None
    
    cv_vector_ref: Optional[List[float]] = None
    
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = None
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.schemas.common_schema import AdminLevel

class AdministrativeUnitCreate(BaseModel):
    code: str = Field(...)
    name: str = Field(...)
    level: AdminLevel = Field(...)
    parent_code: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

class AdministrativeUnitResponse(AdministrativeUnitCreate):
    id: str
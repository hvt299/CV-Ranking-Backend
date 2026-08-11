from pydantic import BaseModel, Field
from typing import List, Optional

class SkillCreate(BaseModel):
    canonical_name: str = Field(...)
    industry: str = Field(...)
    aliases: List[str] = Field(default_factory=list)
    category: Optional[str] = None

class SkillUpdate(BaseModel):
    canonical_name: Optional[str] = None
    industry: Optional[str] = None
    aliases: Optional[List[str]] = None
    category: Optional[str] = None
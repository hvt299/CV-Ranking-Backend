from fastapi import APIRouter, Query
from typing import List, Optional
import re

from app.repositories.administrative_unit_repository import AdministrativeUnitRepository
from app.repositories.skill_repository import SkillRepository
from app.schemas.common_schema import AdminLevel

router = APIRouter(prefix="/api/v1/system", tags=["System & Master Data"])

@router.get("/locations")
async def get_locations():
    """
    Lấy danh sách Tỉnh/Thành phố.
    Bền vững: Lấy tất cả (không filter valid_to) để Frontend tự group theo version.
    """
    query = {"level": AdminLevel.PROVINCE.value} # Bỏ valid_to để lấy cả cũ và mới
    locations = await AdministrativeUnitRepository.find_many(query, limit=200)
    
    result = []
    for loc in locations:
        result.append({
            "id": str(loc["_id"]),
            "code": loc.get("code"),
            "name": loc.get("name"),
            "version": loc.get("version", "old") # Mặc định là old nếu không có
        })
        
    result.sort(key=lambda x: x.get("name", ""))
    return result

@router.get("/skills")
async def search_skills(
    q: Optional[str] = Query(None, description="Từ khóa tìm kiếm kỹ năng"),
    industry: Optional[str] = Query(None, description="Lọc theo ngành nghề (Cross-filtering)")
):
    """
    Tìm kiếm kỹ năng thông minh, hỗ trợ filter chéo theo ngành nghề.
    """
    query = {}
    conditions = []
    
    if q and q.strip():
        regex_pattern = re.compile(f".*{re.escape(q.strip())}.*", re.IGNORECASE)
        conditions.append({
            "$or": [
                {"canonical_name": {"$regex": regex_pattern}},
                {"aliases": {"$regex": regex_pattern}}
            ]
        })
        
    if industry and industry.strip():
        conditions.append({"industry": industry})
        
    if conditions:
        query["$and"] = conditions
        
    skills = await SkillRepository.find_many(query, limit=50)
    
    result = []
    for sk in skills:
        sk["id"] = str(sk["_id"])
        del sk["_id"]
        result.append(sk)
        
    return result
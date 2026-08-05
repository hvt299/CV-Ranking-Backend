import httpx
from typing import List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from datetime import datetime, timedelta, timezone
import jwt

from app.core.security import CurrentUser, require_hr, JWT_SECRET, ALGORITHM
from app.schemas.common_schema import CompanyStatus, UserRole
from app.schemas.company_schema import CompanyResponse
from app.schemas.shared_schema import LocationDetail
from app.services.email_service import send_hr_invite_email
from app.repositories.user_repository import UserRepository
from app.repositories.company_repository import CompanyRepository
import re
from app.database.config import get_db, Collections
from pydantic import ValidationError
from bson import ObjectId

router = APIRouter(prefix="/api/v1/companies", tags=["Company & HR Management"])

async def parse_address_heuristic(raw_address: str) -> dict:
    if not raw_address:
        return None
        
    db = get_db()
    
    address_clean = re.sub(r'[,.\-]', ' ', raw_address.lower())
    address_clean = re.sub(r'\s+', ' ', address_clean)
    address_clean = f" {address_clean} "
    
    provinces = await db[Collections.ADMINISTRATIVE_UNITS].find({"level": "province"}).to_list(100)
    provinces.sort(key=lambda x: len(x['name']), reverse=True)
    
    matched_province = None
    for p in provinces:
        clean_name = re.sub(r'^(tỉnh|thành phố|tp)\s+', '', p['name'], flags=re.IGNORECASE).strip().lower()
        if f" {clean_name} " in address_clean:
            matched_province = p
            break
            
    if not matched_province:
        return None

    prov_code = matched_province["code"]
    
    new_wards = await db[Collections.ADMINISTRATIVE_UNITS].find({
        "parent_code": prov_code, 
        "level": "ward", 
        "version": "new"
    }).to_list(1000)
    
    if new_wards:
        new_wards.sort(key=lambda x: len(x['name']), reverse=True)
        for w in new_wards:
            clean_w_name = re.sub(r'^(phường|xã|thị trấn)\s+', '', w['name'], flags=re.IGNORECASE).strip().lower()
            if f" {clean_w_name} " in address_clean:
                return {
                    "country": "Việt Nam",
                    "version": "new",
                    "province_code": prov_code,
                    "province_name": matched_province["name"],
                    "district_code": "",
                    "district_name": "",
                    "ward_code": w["code"],
                    "ward_name": w["name"],
                    "street_address": raw_address
                }

    old_districts = await db[Collections.ADMINISTRATIVE_UNITS].find({
        "parent_code": prov_code,
        "level": "district",
        "version": "old"
    }).to_list(100)
    old_districts.sort(key=lambda x: len(x['name']), reverse=True)
    
    matched_district = None
    for d in old_districts:
        clean_d_name = re.sub(r'^(quận|huyện|thị xã|thành phố|tp)\s+', '', d['name'], flags=re.IGNORECASE).strip().lower()
        if f" {clean_d_name} " in address_clean:
            matched_district = d
            break
            
    matched_ward = None
    if matched_district:
        old_wards = await db[Collections.ADMINISTRATIVE_UNITS].find({
            "parent_code": matched_district["code"],
            "level": "ward",
            "version": "old"
        }).to_list(1000)
        old_wards.sort(key=lambda x: len(x['name']), reverse=True)
        for w in old_wards:
            clean_w_name = re.sub(r'^(phường|xã|thị trấn)\s+', '', w['name'], flags=re.IGNORECASE).strip().lower()
            if f" {clean_w_name} " in address_clean:
                matched_ward = w
                break
                
    if matched_district:
        return {
            "country": "Việt Nam",
            "version": "old",
            "province_code": prov_code,
            "province_name": matched_province["name"],
            "district_code": matched_district["code"],
            "district_name": matched_district["name"],
            "ward_code": matched_ward["code"] if matched_ward else "",
            "ward_name": matched_ward["name"] if matched_ward else "",
            "street_address": raw_address
        }

    return {
        "country": "Việt Nam",
        "version": matched_province.get("version", "new"),
        "province_code": prov_code,
        "province_name": matched_province["name"],
        "district_code": "",
        "district_name": "",
        "ward_code": "",
        "ward_name": "",
        "street_address": raw_address
    }

@router.get("/lookup-tax/{tax_code}")
async def lookup_tax_code(tax_code: str):
    url = f"https://api.vietqr.io/v2/business/{tax_code}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            data = response.json()
            
            if data.get("code") == "00" and data.get("data"):
                raw_address = data["data"]["address"]
                
                structured_loc = await parse_address_heuristic(raw_address)

                return {
                    "tax_code": data["data"]["id"],
                    "company_name": data["data"]["name"],
                    "address": raw_address,
                    "structured_location": structured_loc, 
                    "status": data["data"]["status"]
                }
            elif data.get("code") == "52":
                raise HTTPException(status_code=404, detail="Mã số thuế không chính xác hoặc không tồn tại")
            else:
                error_desc = data.get("desc", "Không tìm thấy thông tin từ Mã số thuế này")
                raise HTTPException(status_code=404, detail=error_desc)
                
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail="Lỗi kết nối đến cổng tra cứu doanh nghiệp")
    
@router.get("/members", dependencies=[Depends(require_hr)])
async def get_company_members(current_user: CurrentUser = Depends(require_hr)):
    projection = {"hashed_password": 0, "reset_password_token": 0, "reset_password_expires": 0}
    members = await UserRepository.find_many({"company_id": current_user.company_id}, projection=projection, limit=100)
    
    result = []
    for m in members:
        m["id"] = str(m["_id"])
        del m["_id"]
        result.append(m)
    return result

@router.get("/settings", dependencies=[Depends(require_hr)])
async def get_company_settings(current_user: CurrentUser = Depends(require_hr)):
    company = await CompanyRepository.get_by_id(current_user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu công ty")
    
    company["id"] = str(company["_id"])
    del company["_id"]
    return company

@router.patch("/settings", dependencies=[Depends(require_hr)])
async def update_company_settings(
    payload: dict = Body(...), 
    current_user: CurrentUser = Depends(require_hr)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới được phép cập nhật thông tin công ty")

    update_data = {"updated_at": datetime.now(timezone.utc)}

    allowed_fields = ["tax_code", "industry", "size", "website", "address", 
                       "license_file_url", "name", "logo_url", "banner_url", "location"]
    for field in allowed_fields:
        if field in payload:
            update_data[field] = payload[field]

    if "location" in update_data:
        try:
            update_data["location"] = LocationDetail(**update_data["location"]).model_dump()
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=f"Dữ liệu địa điểm không hợp lệ: {e}")

    current_company = await CompanyRepository.get_by_id(current_user.company_id)

    tax_code_changed = "tax_code" in payload and payload["tax_code"] != current_company.get("tax_code")
    license_changed = "license_file_url" in payload and payload["license_file_url"] != current_company.get("license_file_url")

    if tax_code_changed or license_changed:
        update_data["status"] = CompanyStatus.PENDING_VERIFICATION.value
        
    await CompanyRepository.update(current_user.company_id, update_data)
    return {
        "status": "success",
        "message": "Đã cập nhật thông tin công ty",
        "new_company_status": update_data.get("status", current_company.get("status"))
    }

@router.post("/invite", dependencies=[Depends(require_hr)])
async def invite_hr_member(
    background_tasks: BackgroundTasks,
    email: str = Body(..., embed=True), 
    current_user: CurrentUser = Depends(require_hr)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới có quyền mời thành viên")
        
    company = await CompanyRepository.get_by_id(current_user.company_id)
    user = await UserRepository.get_by_id(current_user.id)
    
    existing_user = await UserRepository.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email này đã có tài khoản trên hệ thống")
        
    invite_token = jwt.encode(
        {
            "email": email, 
            "company_id": current_user.company_id, 
            "role": UserRole.HR_MEMBER.value,
            "exp": datetime.now(timezone.utc) + timedelta(days=7)
        },
        JWT_SECRET, algorithm=ALGORITHM
    )
    
    send_hr_invite_email(
        background_tasks, 
        to=email, 
        inviter_name=user.get("full_name", "Quản lý"), 
        company_name=company.get("name", "Công ty"), 
        token=invite_token
    )
    
    return {"status": "success", "message": f"Đã gửi thư mời thành công đến {email}"}

from bson import ObjectId
from app.schemas.company_schema import CompanyResponse

@router.get("/public/list", response_model=List[CompanyResponse])
async def get_public_companies():
    pipeline = [
        {"$match": {"status": CompanyStatus.VERIFIED.value}},
        {"$sort": {"avg_rating": -1, "view_count": -1, "created_at": -1}},
        {"$limit": 100}
    ]
    
    companies = await CompanyRepository.aggregate_companies(pipeline)
    
    result = []
    for comp in companies:
        comp["id"] = str(comp["_id"])
        result.append(comp)
        
    return result

@router.get("/public/{company_id}", response_model=CompanyResponse)
async def get_public_company_detail(company_id: str):
    try:
        obj_id = ObjectId(company_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Định dạng ID không hợp lệ")

    company = await CompanyRepository.find_one({"_id": obj_id, "status": CompanyStatus.VERIFIED.value})
    if not company:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty hoặc công ty chưa được xác thực")
        
    company["id"] = str(company["_id"])
    
    current_views = company.get("view_count", 0)
    await CompanyRepository.update(company_id, {"view_count": current_views + 1})
    company["view_count"] = current_views + 1
    
    return company
import httpx
from typing import List
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body
from datetime import datetime, timedelta, timezone
import jwt

from app.core.security import CurrentUser, require_hr, JWT_SECRET, ALGORITHM
from app.schemas.common_schema import CompanyStatus, UserRole
from app.schemas.company_schema import CompanyResponse, InviteMemberPayload,  DepartmentCreate, DepartmentUpdate, DepartmentResponse, AssignMemberPayload
from app.schemas.shared_schema import LocationDetail
from app.services.email_service import send_hr_invite_email
from app.services.analytics_service import AnalyticsService
from app.repositories.user_repository import UserRepository
from app.repositories.company_repository import CompanyRepository
from app.repositories.department_repository import DepartmentRepository
from app.repositories.administrative_unit_repository import AdministrativeUnitRepository
import re
from app.middleware.subscription import require_tier
from app.middleware.rate_limit import limiter
from fastapi import Request, Response
from pydantic import ValidationError
from bson import ObjectId

router = APIRouter(prefix="/api/v1/companies", tags=["Company & HR Management"])

async def parse_address_heuristic(raw_address: str) -> dict:
    if not raw_address:
        return None
        
    address_clean = re.sub(r'[,.\-]', ' ', raw_address.lower())
    address_clean = re.sub(r'\s+', ' ', address_clean)
    address_clean = f" {address_clean} "
    
    provinces = await AdministrativeUnitRepository.find_many({"level": "province"}, limit=100)
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
    
    new_wards = await AdministrativeUnitRepository.find_many({
        "parent_code": prov_code, 
        "level": "ward", 
        "version": "new"
    }, limit=1000)
    
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

    old_districts = await AdministrativeUnitRepository.find_many({
        "parent_code": prov_code,
        "level": "district",
        "version": "old"
    }, limit=100)
    old_districts.sort(key=lambda x: len(x['name']), reverse=True)
    
    matched_district = None
    for d in old_districts:
        clean_d_name = re.sub(r'^(quận|huyện|thị xã|thành phố|tp)\s+', '', d['name'], flags=re.IGNORECASE).strip().lower()
        if f" {clean_d_name} " in address_clean:
            matched_district = d
            break
            
    matched_ward = None
    if matched_district:
        old_wards = await AdministrativeUnitRepository.find_many({
            "parent_code": matched_district["code"],
            "level": "ward",
            "version": "old"
        }, limit=1000)
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
@limiter.limit("10/minute")
async def lookup_tax_code(request: Request, response: Response, tax_code: str):
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
    return members

@router.get("/settings", dependencies=[Depends(require_hr)])
async def get_company_settings(current_user: CurrentUser = Depends(require_hr)):
    company = await CompanyRepository.get_by_id(current_user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu công ty")
    return company

@router.patch("/settings", dependencies=[Depends(require_hr)])
async def update_company_settings(
    payload: dict = Body(...), 
    current_user: CurrentUser = Depends(require_hr)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới được phép cập nhật thông tin công ty")

    current_company = await CompanyRepository.get_by_id(current_user.company_id)
    if not current_company:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu công ty")
        
    if current_company.get("owner_user_id") and str(current_company.get("owner_user_id")) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Từ chối truy cập: Chỉ người tạo (Owner gốc) mới được quyền sửa thông tin công ty.")

    update_data = {"updated_at": datetime.now(timezone.utc)}

    allowed_string_fields = ["tax_code", "industry", "size", "website", "address", "license_file_url", "name", "logo_url", "banner_url"]
    for field in allowed_string_fields:
        if field in payload and payload[field] is not None:
            update_data[field] = str(payload[field]).strip()

    if "location" in payload and payload["location"] is not None:
        try:
            update_data["location"] = LocationDetail(**payload["location"]).model_dump()
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=f"Dữ liệu địa điểm không hợp lệ: {e}")

    tax_code_changed = "tax_code" in update_data and update_data["tax_code"] != current_company.get("tax_code")
    license_changed = "license_file_url" in update_data and update_data["license_file_url"] != current_company.get("license_file_url")

    if tax_code_changed or license_changed:
        update_data["status"] = CompanyStatus.PENDING_VERIFICATION.value
        
    await CompanyRepository.update(current_user.company_id, update_data)
    return {
        "status": "success",
        "message": "Đã cập nhật thông tin công ty",
        "new_company_status": update_data.get("status", current_company.get("status"))
    }

@router.post("/invite", dependencies=[Depends(require_hr)])
@limiter.limit("20/day")
async def invite_hr_member(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    payload: InviteMemberPayload = Body(...), 
    current_user: CurrentUser = Depends(require_hr)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới có quyền mời thành viên")
        
    company = await CompanyRepository.get_by_id(current_user.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu công ty")

    if company.get("owner_user_id") and str(company.get("owner_user_id")) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Từ chối truy cập: Chỉ người tạo (Owner gốc) mới được quyền mời thành viên.")

    if payload.department_id:
        dept = await DepartmentRepository.get_by_id(payload.department_id)
        if not dept or dept.get("company_id") != current_user.company_id:
            raise HTTPException(status_code=400, detail="Phòng ban không tồn tại hoặc không thuộc công ty này")
        
    user = await UserRepository.get_by_id(current_user.id)
    
    safe_email = str(payload.email).strip()
    existing_user = await UserRepository.find_one({"email": safe_email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email này đã có tài khoản trên hệ thống")
        
    invite_token = jwt.encode(
        {
            "email": safe_email, 
            "company_id": current_user.company_id, 
            "role": UserRole.HR_MEMBER.value,
            "department_id": payload.department_id,
            "department_roles": payload.department_roles,
            "exp": datetime.now(timezone.utc) + timedelta(days=7)
        },
        JWT_SECRET, algorithm=ALGORITHM
    )
    
    send_hr_invite_email(
        background_tasks, 
        to=safe_email, 
        inviter_name=user.get("full_name", "Quản lý"), 
        company_name=company.get("name", "Công ty"), 
        token=invite_token
    )
    
    return {"status": "success", "message": f"Đã gửi thư mời thành công đến {safe_email}"}

@router.get("/{company_id}/analytics", dependencies=[Depends(require_tier("can_export_analytics"))])
async def get_company_analytics(company_id: str, current_user: CurrentUser = Depends(require_hr)):
    if current_user.role != UserRole.HR_OWNER.value or current_user.company_id != company_id:
        raise HTTPException(
            status_code=403, 
            detail="Bạn không có quyền xem dữ liệu phân tích của công ty này"
        )
    
    result = await AnalyticsService.get_company_pro_analytics(company_id)
    
    result["status"] = "success"
    return result

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
        comp["id"] = comp.get("id") or str(comp.pop("_id", ""))
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
    
    current_views = company.get("view_count", 0)
    current_profile_views = company.get("profile_view_count", 0)
    
    await CompanyRepository.update_custom(
        {"_id": obj_id},
        {"$inc": {"view_count": 1, "profile_view_count": 1}}
    )
    
    company["view_count"] = current_views + 1
    company["profile_view_count"] = current_profile_views + 1
    
    return company

@router.post("/departments", response_model=DepartmentResponse, dependencies=[Depends(require_hr)])
async def create_department(
    payload: DepartmentCreate, 
    current_user: CurrentUser = Depends(require_hr)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới được tạo phòng ban")
    
    record = payload.model_dump()
    record["company_id"] = current_user.company_id
    record["created_at"] = datetime.now(timezone.utc)
    record["updated_at"] = datetime.now(timezone.utc)
    
    _id = await DepartmentRepository.create(record)
    record["id"] = _id
    return record

@router.get("/departments", response_model=List[DepartmentResponse], dependencies=[Depends(require_hr)])
async def get_departments(current_user: CurrentUser = Depends(require_hr)):
    depts = await DepartmentRepository.get_by_company_id(current_user.company_id)
    return depts

@router.patch("/departments/{dept_id}", dependencies=[Depends(require_hr)])
async def update_department(
    dept_id: str,
    payload: DepartmentUpdate,
    current_user: CurrentUser = Depends(require_hr)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới được sửa thông tin phòng ban")
    
    dept = await DepartmentRepository.get_by_id(dept_id)
    if not dept or dept.get("company_id") != current_user.company_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban hợp lệ")
        
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return {"status": "success", "message": "Không có dữ liệu mới để cập nhật"}
        
    update_data["updated_at"] = datetime.now(timezone.utc)
    await DepartmentRepository.update(dept_id, update_data)
    return {"status": "success", "message": "Đã cập nhật thông tin phòng ban"}

@router.delete("/departments/{dept_id}", dependencies=[Depends(require_hr)])
async def delete_department(dept_id: str, current_user: CurrentUser = Depends(require_hr)):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới được xóa phòng ban")
    
    dept = await DepartmentRepository.get_by_id(dept_id)
    if not dept or dept.get("company_id") != current_user.company_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban hợp lệ")
        
    await DepartmentRepository.delete(dept_id)
    
    await UserRepository.update_many(
        {"department_id": dept_id},
        {"department_id": None, "department_roles": []}
    )
    
    return {"status": "success", "message": "Đã xóa phòng ban và gỡ phân bổ các nhân sự liên quan"}

@router.patch("/members/{user_id}/department", dependencies=[Depends(require_hr)])
async def assign_member_to_department(
    user_id: str,
    payload: AssignMemberPayload,
    current_user: CurrentUser = Depends(require_hr)
):
    if current_user.role != UserRole.HR_OWNER.value:
        raise HTTPException(status_code=403, detail="Chỉ HR Owner mới được phân bổ nhân sự")
    
    target_user = await UserRepository.get_by_id(user_id)
    if not target_user or target_user.get("company_id") != current_user.company_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân sự trong công ty")

    if payload.department_id:
        dept = await DepartmentRepository.get_by_id(payload.department_id)
        if not dept or dept.get("company_id") != current_user.company_id:
            raise HTTPException(status_code=404, detail="Phòng ban không tồn tại hoặc không thuộc công ty này")

    await UserRepository.update(user_id, {
        "department_id": payload.department_id,
        "department_roles": payload.department_roles,
        "updated_at": datetime.now(timezone.utc)
    })

    return {"status": "success", "message": "Đã cập nhật phân bổ phòng ban cho nhân sự"}
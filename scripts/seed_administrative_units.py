import os
import csv
import asyncio
from datetime import datetime, timezone
from app.database.config import db_instance, connect_to_mongo, close_mongo_connection
from app.repositories.administrative_unit_repository import AdministrativeUnitRepository
from app.database.config import Collections
from app.schemas.common_schema import AdminLevel

async def seed_locations():
    await connect_to_mongo()
    db = db_instance.db
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOCATIONS_FOLDER = os.path.join(BASE_DIR, "data", "administrative_units")
    
    await AdministrativeUnitRepository.delete_many({})
    print("Đã dọn dẹp collection administrative_units hiện tại.")
    
    inserted_count = 0
    files_to_import = [
        ("provinces.csv", "province", "old"),
        ("districts.csv", "district", "old"),
        ("wards.csv", "ward", "old"),
        ("new_provinces.csv", "province", "new"),
        ("new_wards.csv", "ward", "new")
    ]
    
    for filename, unit_type, version in files_to_import:
        file_path = os.path.join(LOCATIONS_FOLDER, filename)
        if not os.path.exists(file_path):
            print(f"Bỏ qua {filename} vì không tìm thấy file.")
            continue
            
        # ÁP DỤNG NGHIỆP VỤ THỜI GIAN THỰC (Time-Series)
        if version == "old":
            # Từ 1/12/2024 đến 23:59:59 30/06/2025
            valid_from = datetime(2024, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
            valid_to = datetime(2025, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
        else:
            # Từ 1/07/2025 trở đi (Vô thời hạn)
            valid_from = datetime(2025, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
            valid_to = None
            
        with open(file_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            batch = []
            
            for row in reader:
                doc = {
                    "version": version,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "deleted_at": None
                }
                
                # Trích xuất Parent Code an toàn (tránh để chuỗi rỗng '' mà chuyển hẳn thành None nếu không có)
                if unit_type == "province":
                    doc["code"] = row.get("province_code") or row.get("code", "")
                    doc["name"] = row.get("province_name") or row.get("name", "")
                    doc["level"] = AdminLevel.PROVINCE.value
                    doc["parent_code"] = None
                elif unit_type == "district":
                    doc["code"] = row.get("district_code") or row.get("code", "")
                    doc["name"] = row.get("district_name") or row.get("name", "")
                    doc["level"] = AdminLevel.DISTRICT.value
                    parent_code = row.get("province_code", "")
                    doc["parent_code"] = parent_code if parent_code else None
                elif unit_type == "ward":
                    doc["code"] = row.get("ward_code") or row.get("code", "")
                    doc["name"] = row.get("ward_name") or row.get("name", "")
                    doc["level"] = AdminLevel.WARD.value
                    parent_code = row.get("district_code", "")
                    doc["parent_code"] = parent_code if parent_code else None
                
                batch.append(doc)
                
                if len(batch) >= 1000:
                    await db[Collections.ADMINISTRATIVE_UNITS].insert_many(batch)
                    inserted_count += len(batch)
                    batch = []
                    
            if batch:
                await db[Collections.ADMINISTRATIVE_UNITS].insert_many(batch)
                inserted_count += len(batch)
                
        print(f"Đã import file {filename} thành công (version: {version}).")
                
    print(f"Hoàn tất! Đã chuẩn hóa và import {inserted_count} đơn vị hành chính vào MongoDB.")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_locations())
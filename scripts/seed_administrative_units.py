import os
import csv
import asyncio
from app.database.config import db_instance, connect_to_mongo, close_mongo_connection
from app.repositories.administrative_unit_repository import AdministrativeUnitRepository
from app.database.config import Collections

async def seed_locations():
    await connect_to_mongo()
    db = db_instance.db
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOCATIONS_FOLDER = os.path.join(BASE_DIR, "data", "administrative_units")
    
    # Quét sạch collection thông qua BaseRepository
    await AdministrativeUnitRepository.delete_many({})
    print("Đã dọn dẹp collection administrative_units hiện tại.")
    
    inserted_count = 0
    
    # Mapping các file cần import kèm siêu dữ liệu (Metadata)
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
            print(f"Bỏ qua {filename} vì không tìm thấy file trong thư mục data/administrative_units.")
            continue
            
        with open(file_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            batch = []
            
            for row in reader:
                doc = dict(row)
                
                # Gắn thêm nhãn để Query dễ dàng ở Frontend
                doc["unit_type"] = unit_type
                doc["version"] = version
                doc["deleted_at"] = None
                
                batch.append(doc)
                
                # Insert theo lô (Batching) 1000 record/lần để tối ưu I/O MongoDB
                if len(batch) >= 1000:
                    await db[Collections.ADMINISTRATIVE_UNITS].insert_many(batch)
                    inserted_count += len(batch)
                    batch = []
                    
            # Insert nốt phần dư cuối cùng
            if batch:
                await db[Collections.ADMINISTRATIVE_UNITS].insert_many(batch)
                inserted_count += len(batch)
                
        print(f"Đã import file {filename} thành công.")
                
    print(f"Hoàn tất kịch bản! Đã import tổng cộng {inserted_count} đơn vị hành chính vào MongoDB.")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_locations())
import os
import csv
import asyncio
from app.database.config import db_instance, connect_to_mongo, close_mongo_connection
from app.repositories.skill_repository import SkillRepository
from app.database.config import Collections

async def seed_skills():
    await connect_to_mongo()
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SKILLS_FOLDER = os.path.join(BASE_DIR, "data", "skills")
    
    await SkillRepository.delete_many({})
    
    inserted_count = 0
    for industry_folder in os.listdir(SKILLS_FOLDER):
        industry_path = os.path.join(SKILLS_FOLDER, industry_folder)
        if not os.path.isdir(industry_path): continue
            
        for filename in os.listdir(industry_path):
            if not filename.endswith(".csv"): continue
            
            with open(os.path.join(industry_path, filename), encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                
                for row in reader:
                    if len(row) < 3: continue
                    industry = row[0].strip().lower()
                    category = row[1].strip()
                    canonical_name = row[2].strip()
                    aliases = [v.strip().lower() for v in row[3:] if v.strip()]
                    
                    await SkillRepository.create({
                        "industry": industry,
                        "category": category,
                        "canonical_name": canonical_name,
                        "aliases": aliases,
                        "deleted_at": None
                    })
                    inserted_count += 1
                    
    print(f"Đã import thành công {inserted_count} kỹ năng vào MongoDB.")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_skills())
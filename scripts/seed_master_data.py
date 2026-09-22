import os
import csv
import asyncio
from app.database.config import db_instance, connect_to_mongo, close_mongo_connection
from app.repositories.language_repository import LanguageRepository
from app.repositories.certification_repository import CertificationRepository

async def seed_master_data():
    await connect_to_mongo()
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. Seed Languages
    LANG_FILE = os.path.join(BASE_DIR, "data", "languages", "languages.csv")
    if os.path.exists(LANG_FILE):
        await LanguageRepository.delete_many({})
        inserted_lang = 0
        with open(LANG_FILE, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) < 1: continue
                canonical_name = row[0].strip()
                aliases = [v.strip().lower() for v in row[1:] if v.strip()]
                
                await LanguageRepository.create({
                    "canonical_name": canonical_name,
                    "aliases": aliases
                })
                inserted_lang += 1
        print(f"Đã import thành công {inserted_lang} ngôn ngữ.")

    # 2. Seed Certifications
    CERT_FILE = os.path.join(BASE_DIR, "data", "certifications", "certifications.csv")
    if os.path.exists(CERT_FILE):
        await CertificationRepository.delete_many({})
        inserted_cert = 0
        with open(CERT_FILE, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) < 1: continue
                canonical_name = row[0].strip()
                aliases = [v.strip().lower() for v in row[1:2] if v.strip()]
                issuer = row[2].strip() if len(row) > 2 else None
                
                await CertificationRepository.create({
                    "canonical_name": canonical_name,
                    "aliases": aliases,
                    "issuer": issuer
                })
                inserted_cert += 1
        print(f"Đã import thành công {inserted_cert} chứng chỉ.")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_master_data())

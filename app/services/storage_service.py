import os
import cloudinary
import cloudinary.uploader
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

async def upload_file_to_cloudinary(file_bytes: bytes, filename: str) -> str:
    try:
        random_suffix = os.urandom(4).hex()
        safe_filename = filename.split('.')[0][:30]
        
        result = cloudinary.uploader.upload(
            file_bytes,
            resource_type="auto", 
            folder="ats_cv_library",
            public_id=f"{safe_filename}_{random_suffix}"
        )
        return result.get("secure_url")
    except Exception as e:
        logger.error(f"Lỗi khi upload lên Cloudinary: {e}")
        raise Exception("Không thể lưu trữ file CV vào Cloudinary lúc này")
    
async def delete_file_from_cloudinary(file_url: str) -> bool:
    try:
        if "cloudinary.com" not in file_url:
            return False
            
        upload_part = file_url.split('/upload/')[-1]
        path_parts = upload_part.split('/')
        
        if path_parts[0].startswith('v') and path_parts[0][1:].isdigit():
            path_parts = path_parts[1:]
            
        file_path_with_ext = '/'.join(path_parts)
        public_id = file_path_with_ext.rsplit('.', 1)[0]
        
        cloudinary.uploader.destroy(public_id, resource_type="auto")
        return True
    except Exception as e:
        logger.error(f"Lỗi khi xóa file Cloudinary: {e}")
        return False
import os
import cloudinary
import cloudinary.uploader
import logging
from dotenv import load_dotenv

import socket
import ipaddress
from urllib.parse import urlparse

load_dotenv()
logger = logging.getLogger(__name__)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

async def upload_file_to_cloudinary(file_bytes: bytes, filename: str, target_folder: str = "ats_cv_library") -> str:
    try:
        random_suffix = os.urandom(4).hex()
        safe_filename = filename.split('.')[0][:30]
        
        result = cloudinary.uploader.upload(
            file_bytes,
            resource_type="auto", 
            folder=target_folder,
            public_id=f"{safe_filename}_{random_suffix}"
        )
        return result.get("secure_url")
    except Exception as e:
        logger.error(f"Lỗi khi upload lên Cloudinary: {e}")
        raise Exception("Không thể lưu trữ file vào Cloudinary lúc này")
    
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

def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
            
        if parsed.hostname in ("localhost", "127.0.0.1", "169.254.169.254", "metadata.google.internal"):
            return False
            
        ip = socket.gethostbyname(parsed.hostname)
        ip_obj = ipaddress.ip_address(ip)
        
        if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local or ip_obj.is_multicast:
            return False
            
        return True
    except Exception as e:
        logger.warning(f"SSRF Shield Blocked URL ({url}): {e}")
        return False
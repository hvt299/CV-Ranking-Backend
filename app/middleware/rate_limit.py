import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv("REDIS_URL", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=redis_url,
    default_limits=["300/minute"],
    headers_enabled=True,
    # Với rediss:// (TLS), một số version limits/redis-py cần khai báo rõ
    # ssl_cert_reqs để tránh lỗi "CERTIFICATE_VERIFY_FAILED" tuỳ CA bundle của server.
    storage_options={"ssl_cert_reqs": None} if redis_url.startswith("rediss://") else {},
)
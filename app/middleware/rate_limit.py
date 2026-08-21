import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv("REDIS_URL", "")
rate_limit_url = redis_url if redis_url.startswith(("redis://", "rediss://", "unix://")) else "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=rate_limit_url,
    default_limits=["300/minute"],
    headers_enabled=True,
    storage_options={"ssl_cert_reqs": None} if rate_limit_url.startswith("rediss://") else {},
)
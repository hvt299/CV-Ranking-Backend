"""
Load biến môi trường với thứ tự ưu tiên:
1. .env.local  — chỉ dùng khi phát triển local, KHÔNG commit vào git.
2. .env        — giá trị fallback / dùng khi deploy lên Render.

Import module này ở nơi SỚM NHẤT có thể (đầu file main.py), trước khi
bất kỳ module nào khác đọc os.getenv(...), để đảm bảo biến đã sẵn sàng.
"""
from pathlib import Path
from dotenv import load_dotenv

# BASE_DIR trỏ về thư mục gốc project (chứa main.py, .env, .env.local)
# Điều chỉnh số lần .parent nếu cấu trúc thư mục của bạn khác
BASE_DIR = Path(__file__).resolve().parent.parent.parent

ENV_LOCAL = BASE_DIR / ".env.local"
ENV_DEFAULT = BASE_DIR / ".env"

if ENV_LOCAL.exists():
    # override=True: giá trị trong .env.local sẽ ghi đè lên bất kỳ biến nào
    # đã tồn tại (kể cả biến hệ thống OS đã set sẵn)
    load_dotenv(dotenv_path=ENV_LOCAL, override=True)

if ENV_DEFAULT.exists():
    # override=False: chỉ điền vào những biến CHƯA có giá trị,
    # không ghi đè lên những gì .env.local đã set ở trên
    load_dotenv(dotenv_path=ENV_DEFAULT, override=False)
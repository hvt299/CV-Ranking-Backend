from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

ENV_LOCAL = BASE_DIR / ".env.local"
ENV_DEFAULT = BASE_DIR / ".env"

if ENV_LOCAL.exists():
    load_dotenv(dotenv_path=ENV_LOCAL, override=True)

if ENV_DEFAULT.exists():
    load_dotenv(dotenv_path=ENV_DEFAULT, override=False)
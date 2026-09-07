import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "tof.db"

APP_SECRET = os.getenv("APP_SECRET", "dev-app-secret")
TREE_SECRET = os.getenv("TREE_SECRET", "dev-tree-secret")
DEMO_LOGIN = os.getenv("DEMO_LOGIN", "true").lower() == "true"
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "").strip()
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "").strip()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
TERMS_VERSION = "2026-03-27"
GROWTH_RULE_VERSION = 1
SESSION_COOKIE = "tof_session"
CSRF_COOKIE = "tof_csrf"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
AI_DAILY_LIMIT = 3

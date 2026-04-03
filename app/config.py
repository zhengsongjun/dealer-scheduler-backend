import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:123456@localhost:5432/dealer_manager")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 525600  # 365 days
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Google OR API
GOOGLE_OR_API_KEY = os.getenv("GOOGLE_OR_API_KEY", "")
GOOGLE_OR_API_ENDPOINT = "https://optimization.googleapis.com/v1/mathopt:solveMathOptModel"
USE_CLOUD_SOLVER = os.getenv("USE_CLOUD_SOLVER", "true").lower() == "true"

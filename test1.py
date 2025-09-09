import os

# Application secret key
SECRET_KEY = os.getenv("APP_SECRET_KEY", "default_secret")

# Database URL for connecting
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")

# Timeout for DB connections
DB_TIMEOUT = int(os.getenv("DB_TIMEOUT", "30"))

# Debug mode flag
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

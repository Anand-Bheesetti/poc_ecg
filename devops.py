# config.py (after changes - large PR with env & config changes)

import os

class Config:
    # Debugging and Logging
    DEBUG = os.getenv("APP_DEBUG", "False").lower() == "true"
    LOG_LEVEL = os.getenv("APP_LOG_LEVEL", "DEBUG")  # Changed from INFO -> DEBUG
    LOG_FILE = os.getenv("APP_LOG_FILE", "/var/log/app/app.log")

    # Database Config
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/appdb")
    DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "20"))
    DATABASE_TIMEOUT = int(os.getenv("DATABASE_TIMEOUT", "60"))

    # Caching Config
    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "True").lower() == "true"
    CACHE_BACKEND = os.getenv("CACHE_BACKEND", "redis")
    CACHE_URL = os.getenv("CACHE_URL", "redis://localhost:6379/0")

    # API Config
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", "60"))  # Increased from 30 → 60
    API_RETRY_COUNT = int(os.getenv("API_RETRY_COUNT", "5"))

    # Security Config
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret")
    TOKEN_EXPIRY = int(os.getenv("TOKEN_EXPIRY", "3600"))

    # Feature Flags
    FEATURE_X_ENABLED = os.getenv("FEATURE_X_ENABLED", "False").lower() == "true"
    FEATURE_Y_ENABLED = os.getenv("FEATURE_Y_ENABLED", "True").lower() == "true"

    # Deployment/Env Specific
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    REGION = os.getenv("DEPLOY_REGION", "us-east-1")
    ENABLE_METRICS = os.getenv("ENABLE_METRICS", "True").lower() == "true"

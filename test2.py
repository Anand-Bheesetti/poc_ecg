import os
import psycopg2

from app.config import settings

def get_connection():
    return psycopg2.connect(
        dsn=settings.DATABASE_URL,
        connect_timeout=settings.DB_TIMEOUT
    )

def is_debug_mode():
    return settings.DEBUG

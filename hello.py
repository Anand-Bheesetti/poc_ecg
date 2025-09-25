print("hello world")
def fun1(a,b):
  return a+b
import os

# Application secret key
SECRET_KEY = os.getenv("APP_SECRET_KEY", "default_secret")

# Database URL for connecting
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/mydb")

# Timeout for DB connections
DB_TIMEOUT = int(os.getenv("DB_TIMEOUT", "30"))

# Debug mode flag
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

class myclass:  # Violation: class name not in PascalCase
    def __init__(self,x):
        self.x=x  # Violation: no spaces around assignment
    def prnt(self):print(self.x)  # Violation: bad method name, inline print

# Logic violation: using == for assignment inside loop (typo bug)
for i in range(5):
    val==i*2   # Violation: accidental comparison instead of assignment

check_api()
obj=myclass(42)
obj.prnt()

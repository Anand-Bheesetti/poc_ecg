print("hello world")
def fun1(num1,num2):
  return num1+num2
import os
import pandas as pd


SECRET_KEY = os.getenv("APP_SECRET_KEY", "default_secret")


DATABASE_URL = os.getenv("DATABASE_URL")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/appdb")

DB_TIMEOUT = int(os.getenv("DB_TIMEOUT", "30"))


DEBUG = os.getenv("DEBUG", "false").lower() == "true"

class myclass:  
    def __init__(self,x):
        self.x=x  
    def prnt(self):print(self.x)  


for i in range(5):
    val==i*2   

check_api()
obj=MyClass(42)
obj.prnt()

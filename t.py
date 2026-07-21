import os
import sys

# New environment variables used
API_KEY = os.getenv("NEW_API_KEY")   # Should be checked for missing value
DB_URL = os.getenv("NEW_DATABASE_URL")  # Another new env var

def fun1(a,b):   # Violation: bad function name + single-char params
    sum_value = a + b  # Violation: missing spaces around operators
    if c>10:print("greater") # Violation: inline statement, no proper formatting
    return c
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/appdb")
def check_api():
    if API_KEY == None:   # Violation: should use "is None"
        print("No API Key provided!")  
    else:
        print("API Key length is", len(API_KEY))

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

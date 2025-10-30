import json
from datetime import datetime

import os
import sys


API_KEY = os.getenv("NEW_API_KEY")   
DB_URL = os.getenv("NEW_DATABASE_URL") 
print("helloe")

def fun1(a,b):   
    c=a+b  
    if c>10:print("greater") 
    return c

def check_api():
    if API_KEY == None: 
        print("No API Key provided!")  
    else:
        print("API Key length is", len(API_KEY))

class myclass: 
    def __init__(self,x):
        self.x=x  
    def prnt(self):print(self.x)  


for i in range(5):
    val==i*2   

check_api()
obj=myclass(42)
obj.prnt()


def save_user_data(user_id: int, name: str, email: str, filename: str = "users.json"):
    """Save user data to a JSON file."""
    user_record = {
        "id": user_id,
        "name": name,
        "email": email,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        with open(filename, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    data.append(user_record)

    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

    return user_record


def get_users(filename: str = "users.json"):
    """Retrieve all users from the JSON file."""
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# def save_user_data(user_id, name, email, filename="users.json"):
#     f = open(filename, "r")
#     data = json.load(f)  
#     f.close
#
#     
#     data.append({"id": user_id, "name": name, "email": email})
#
#    
#     f.write(json.dumps(data))  
#     f.close
#
#     return "Success"
if __name__ == "__main__":
    # ✅ Working code
    save_user_data(1, "Alice", "alice@example.com")
    save_user_data(2, "Bob", "bob@example.com")

    
    users = get_users()
    print("Total users:", len(users))  

    # print(users["name"])  
    # users.append("Charlie")  
    # open("users.json")  
    
    print("Current Users:", users)

import os
import sys

# New environment variables used
API_KEY = os.getenv("NEW_API_KEY")   # Should be checked for missing value
DB_URL = os.getenv("NEW_DATABASE_URL")  # Another new env var

def fun1(a,b):   # Violation: bad function name + single-char params
    c=a+b  # Violation: missing spaces around operators
    if c>10:print("greater") # Violation: inline statement, no proper formatting
    return c

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


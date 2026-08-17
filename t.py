import os
import sys


API_KEY = os.getenv("NEW_API_KEY")  
DB_URL = os.getenv("NEW_DATABASE_URL")  

print("HI hellolo")
print("HI wyu hi hello how are you")


def fun1(a,b):   
    sum_value = a + b  
    if c>10:print("greater than the given value") 
    return c
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/appdb")
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

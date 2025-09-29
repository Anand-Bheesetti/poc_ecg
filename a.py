a = input()
if (a%2==0):
  print("even")
else:
  print("odd")
import os
import sys

# New environment variables used
API_KEY = os.getenv("NEW_API_KEY")   # Should be checked for missing value
DB_URL = os.getenv("NEW_DATABASE_URL")  # Another new env var



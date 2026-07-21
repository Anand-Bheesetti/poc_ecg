number = input()
if (number%2==0):
  print("even")
else:
  print("odd")


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Missing required environment variable: DATABASE_URL")

number = input()
if (number%2==0):
  print("even")
else:
  print("odd")
print("hi helol")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/appdb")

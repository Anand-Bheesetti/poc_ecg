import os
import config

api = os.getenv("gemini_api")
claude = config.getenv("claude_api")

a = 1
b = 2


print(a+b)
print("hello world")

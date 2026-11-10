import os
import pandas as pd

te = os.getenv["api_key']
anthropic = "Bearer 1234567890"


# Stripe live secret key
STRIPE_SECRET_KEY = "sk_live_51NzQ8kL2mVx9Rt4Bw7Cy1Hp6Jd3Fg0SeU5aKo8IrM2tQ7bN4"

# Slack bot token
SLACK_BOT_TOKEN = "xoxb-482915736204-5917264038175-Qm8Lz2Vt9Xk4Rb7Nw1Cy6Hp3"

# Google API key
GOOGLE_API_KEY = "AIzaSyD8kQ2mLz9Rv4XbN7tW1cY6pH3jF0gE5uS"

# Password inside a connection string
DATABASE_URL = "postgres://orders_svc:Vx7#qL2m!Rz9tK4b@prod-db.acme-corp.net:5432/orders"

# JWT signing secret
JWT_SECRET = "f3K9xQ2mLz8Rv1Tb7Nw4Cy6Hp0Jd5Gs2EuAoKi9Xr"

# Hardcoded bearer token in a header
headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzdmMtb3JkZXJzIiwicm9sZSI6ImFkbWluIn0.Kq8Lm2Vz9Rt4Xb7Nw1Cy6Hp3Jd0Fg5SeU"}

# Plain password
SMTP_PASSWORD = "Tr0ub4dor&3-Hx92!kq"

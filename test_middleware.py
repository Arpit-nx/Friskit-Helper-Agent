import jwt
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

payload = {
    # UMS claims
    "sessionId": "TEST_SESSION_001",
    "uuid": "TEST_UUID_001",
    "userId": "TEST_USER_001",
    "userCode": "TEST001",
    "userRole": "ADMIN",
    "isActive": True,

    # Expiration
    "exp": datetime.now(timezone.utc) + timedelta(hours=1)
}

token = jwt.encode(
    payload,
    os.getenv("JWT_SECRET_KEY"),
    algorithm=os.getenv("JWT_ALGORITHM")
)

print("\nGenerated JWT:\n")
print(token)


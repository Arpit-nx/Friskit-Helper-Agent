

import os

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

load_dotenv()

class JWTAuthMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, exempt_paths: set[str]):
        super().__init__(app)

        self.secret_key = os.getenv("JWT_SECRET_KEY")
        if not self.secret_key:
            raise RuntimeError("JWT_SECRET_KEY not set in environment")

        self.exempt_paths = exempt_paths
        self.algorithm = os.getenv("JWT_ALGORITHM")

        if not self.algorithm:
            raise RuntimeError("JWT_ALGORITHM not set in environment")

    async def dispatch(self, request: Request, call_next):

        # Skip verification for public routes
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"}
            )

        token = auth_header.split(" ", 1)[1]

        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                leeway=30,
            )

        except ExpiredSignatureError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token has expired"}
            )

        except InvalidTokenError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"}
            )

        # New UMS JWT support
        if "userId" in payload:

            required_fields = {
                "sessionId",
                "uuid",
                "userId",
                "userCode",
                "userRole",
            }

            if not required_fields.issubset(payload):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Missing required fields in token"}
                )

            if payload.get("isActive") is not True:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "User is not enabled"}
                )

            request.state.user_id = payload["userId"]
            request.state.user_code = payload["userCode"]
            request.state.user_role = payload["userRole"].upper()
            request.state.session_id = payload["sessionId"].upper()

            request.state.user_uuid = payload["uuid"]
            request.state.user_permission = payload.get("userPermission")
            request.state.email_id = payload.get("emailId")
            request.state.phone_number = payload.get("phoneNumber")
            request.state.display_name = payload.get("displayName")

        # Legacy JWT support
        else:

            required_fields = {
                "user_id",
                "user_code",
                "user_role"
            }

            if not required_fields.issubset(payload):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Missing required fields in token"}
                )

            if payload.get("user_status") != "Enabled":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "User is not enabled"}
                )

            request.state.user_id = payload["user_id"]
            request.state.user_code = payload["user_code"]
            request.state.user_role = payload["user_role"].upper()
            request.state.session_id = payload.get("session_id")

        return await call_next(request)

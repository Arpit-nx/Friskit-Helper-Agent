
import logging
import time
from uuid import uuid4
from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI, Depends, HTTPException, Request

from app.schemas import ChatRequest, ChatResponse
from app.dependencies import get_current_user
from app.pipeline import RAGPipeline
from app.middleware import JWTAuthMiddleware
from app.logging_config import configure_logging
from app.request_router import RequestRouter
from app.config import settings


# Logging
configure_logging()
log = logging.getLogger("rag.api")


# FastAPI application
app = FastAPI(
    title="Friskit Website Assistant",
    version="1.0.0",
    description="Authenticated RAG-based website navigation assistant"
)

# Authentication middleware
app.add_middleware(
    JWTAuthMiddleware,
    exempt_paths={
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    }
)

# Initialize RAG pipeline once
rag = RAGPipeline()
request_router = RequestRouter()


# CORS middleware — register last
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def log_request_metrics(request: Request, call_next):
    request_id = uuid4().hex
    request.state.request_id = request_id
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started_at) * 1000
        log.exception(
            "HTTP_REQUEST_FAILED request_id=%s method=%s path=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    log_level = (
        logging.ERROR if response.status_code >= 500
        else logging.WARNING if response.status_code >= 400
        else logging.INFO
    )
    log.log(
        log_level,
        "HTTP_REQUEST_COMPLETE request_id=%s method=%s path=%s status=%d duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

# Health check
@app.get("/health")
async def health():
    return {"status": "healthy"}


# Chat endpoint
@app.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):

    request_id = request.state.request_id
    role = current_user["userrole"]

    log.info(
        "CHAT_REQUEST request_id=%s role=%s current_page=%s",
        request_id,
        role,
        payload.current_page
    )

    try:
        decision = request_router.route(payload.question)
        log.info("CHAT_ROUTE request_id=%s route=%s", request_id, decision.route)

        if decision.route == "direct":
            return ChatResponse(answer=decision.answer or "")

        # Execute asynchronous RAG pipeline
        result = await rag.ask(
            payload.question,
            role,
            payload.current_page
        )

        # Validate pipeline response
        if not isinstance(result, dict):
            log.error("INVALID_RAG_RESPONSE type=%s", type(result))
            raise RuntimeError("INVALID_RAG_RESPONSE")

        answer = result.get("answer")

        if not answer:
            log.error("RAG_RESPONSE_MISSING")
            raise RuntimeError("RAG_RESPONSE_MISSING")

        # Extract navigation context
        page_context = result.get("page_context") or {}

        return ChatResponse(
            answer=result.get("answer", ""),
            steps=result.get("steps", []),
            id=result.get("id")
        )

    except Exception:
        log.exception(
            "CHAT_REQUEST_FAILED request_id=%s",
            request_id
        )

        raise HTTPException(
            status_code=502,
            detail="Unable to generate a response at the moment."
        )

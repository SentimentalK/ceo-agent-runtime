"""
Production-oriented HTTP resolver service for content.resolve_url.
Exposes:
  - GET  /healthz     (Liveness probe, unauthenticated)
  - GET  /readyz      (Readiness probe, fails closed if TOOLS_INTERNAL_TOKEN is unset)
  - POST /v1/resolve  (Authenticated synchronous URL metadata resolver)
"""

import os
import sys
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    from .contracts import ContentMetadataV1, ResolveUrlInputV1
    from .models import ResolveError, UnsupportedURLError
    from .resolver import resolve_url
except (ImportError, ValueError):
    from contracts import ContentMetadataV1, ResolveUrlInputV1
    from models import ResolveError, UnsupportedURLError
    from resolver import resolve_url

app = FastAPI(
    title="Content Resolver Service",
    description="Internal CEO provider-side service for lightweight URL metadata resolution.",
    version="1.0.0",
)


class ResolveRequest(BaseModel):
    schema_version: int = Field(default=1, description="Wire contract schema version (must be 1)")
    url: str = Field(..., description="Target media URL to resolve")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Normalize Pydantic validation errors into structured error JSON."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": {
                "code": "invalid_request",
                "message": f"Invalid request body: {exc.errors()}",
            }
        },
    )


def get_configured_internal_token() -> Optional[str]:
    """Retrieve internal token from environment."""
    token = os.environ.get("TOOLS_INTERNAL_TOKEN")
    if token and token.strip():
        return token.strip()
    return None


@app.get("/healthz", tags=["Health"])
async def healthz():
    """
    Process liveness probe.
    Returns 200 when the process is alive. Unauthenticated for Kubernetes liveness probes.
    """
    return {"status": "ok"}


@app.get("/readyz", tags=["Health"])
async def readyz(response: Response):
    """
    Readiness probe with fail-closed semantics.
    Verifies essential runtime configuration (TOOLS_INTERNAL_TOKEN).
    If unconfigured or empty, returns 503 to prevent Kubernetes from routing traffic.
    """
    token = get_configured_internal_token()
    if not token:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "error": "TOOLS_INTERNAL_TOKEN is not configured",
        }
    return {"status": "ready"}


@app.post("/v1/resolve", tags=["Resolver"])
async def resolve(
    payload: ResolveRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Synchronously resolve canonical metadata for a supported URL.
    Requires Bearer token matching TOOLS_INTERNAL_TOKEN.
    """
    # 1. Verify server auth configuration
    expected_token = get_configured_internal_token()
    if not expected_token:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "auth_not_configured",
                    "message": "Server authentication not configured: TOOLS_INTERNAL_TOKEN is missing.",
                }
            },
        )

    # 2. Authenticate request
    if not authorization:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": {
                    "code": "missing_token",
                    "message": "Authorization header is required (Bearer <token>).",
                }
            },
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": {
                    "code": "invalid_token",
                    "message": "Authorization header must use Bearer scheme.",
                }
            },
        )

    provided_token = parts[1]
    if provided_token != expected_token:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": {
                    "code": "invalid_token",
                    "message": "Invalid authorization token.",
                }
            },
        )

    # 3. Validate schema_version
    if payload.schema_version != 1:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "unsupported_schema_version",
                    "message": f"Unsupported schema_version: {payload.schema_version}. Only schema_version 1 is supported.",
                }
            },
        )

    target_url = payload.url.strip() if payload.url else ""
    if not target_url:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "invalid_url",
                    "message": "Field 'url' must not be empty.",
                }
            },
        )

    # 4. Resolve metadata via lightweight resolver capability
    try:
        raw_meta = resolve_url(target_url)
    except UnsupportedURLError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "unsupported_url",
                    "message": str(e),
                }
            },
        )
    except ResolveError as e:
        # Upstream platform reached but deterministic metadata resolution failed
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {
                    "code": "resolve_failed",
                    "message": str(e),
                }
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_error",
                    "message": f"Internal server error: {e}",
                }
            },
        )

    # 5. Serialize to V1 wire contract
    v1_meta = ContentMetadataV1.from_content_metadata(raw_meta, schema_version=1)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=v1_meta.to_dict(),
    )

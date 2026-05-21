from __future__ import annotations

import logging
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

LANGFUSE_INTERNAL_URL = "http://langfuse-web:3000"
DEFAULT_EMAIL = "admin@piap.local"
DEFAULT_PASSWORD = "piap_admin_123456"


def _build_proxy_trace_url(trace_id: str) -> str:
    project_id = str(getattr(settings, "langfuse_project_id", "piap-local") or "piap-local")
    return f"/langfuse/project/{project_id}/traces/{trace_id}"


@router.get("/langfuse/redirect")
async def langfuse_redirect(
    trace_id: str = Query(..., description="Langfuse trace ID"),
):
    email = str(getattr(settings, "langfuse_init_user_email", "") or "").strip() or DEFAULT_EMAIL
    password = DEFAULT_PASSWORD

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        try:
            csrf_resp = await client.get(f"{LANGFUSE_INTERNAL_URL}/api/auth/csrf")
            csrf_resp.raise_for_status()
        except Exception as exc:
            logger.error("Langfuse CSRF fetch failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Langfuse auth endpoint unreachable") from exc

        try:
            csrf_data = csrf_resp.json()
        except Exception as exc:
            logger.error("Langfuse CSRF parse failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid Langfuse auth response") from exc

        csrf_token = csrf_data.get("csrfToken", "")

        try:
            login_resp = await client.post(
                f"{LANGFUSE_INTERNAL_URL}/api/auth/callback/credentials",
                data={
                    "csrfToken": csrf_token,
                    "email": email,
                    "password": password,
                    "redirect": "false",
                    "json": "true",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                cookies=csrf_resp.cookies,
            )
            login_resp.raise_for_status()
        except Exception as exc:
            logger.error("Langfuse login failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Langfuse login failed") from exc

    session_token = login_resp.cookies.get("next-auth.session-token")
    if not session_token:
        logger.error("Langfuse login did not return session token")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Langfuse session not established")

    redirect_url = _build_proxy_trace_url(trace_id)
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="next-auth.session-token",
        value=session_token,
        path="/",
        httponly=True,
        secure=False,
        samesite="lax",
    )
    for name, value in login_resp.cookies.items():
        if name != "next-auth.session-token":
            response.set_cookie(
                key=name,
                value=value,
                path="/",
                httponly=name.startswith("__Host-") or name.startswith("__Secure-"),
            )

    return response

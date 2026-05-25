from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_EMAIL = "admin@piap.local"
DEFAULT_PASSWORD = "piap_admin_123456"


def _langfuse_auth_base_url() -> str:
    return str(getattr(settings, "langfuse_host", "") or "http://127.0.0.1:3000").rstrip("/")


def _build_proxy_trace_url(trace_id: str) -> str:
    project_id = str(getattr(settings, "langfuse_project_id", "piap-local") or "piap-local")
    return f"/project/{project_id}/traces/{trace_id}"


@router.get("/langfuse/redirect")
async def langfuse_redirect(
    trace_id: str = Query(..., description="Langfuse trace ID"),
):
    email = str(getattr(settings, "langfuse_init_user_email", "") or "").strip() or DEFAULT_EMAIL
    password = str(getattr(settings, "langfuse_init_user_password", "") or "").strip() or DEFAULT_PASSWORD
    langfuse_base_url = _langfuse_auth_base_url()

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        try:
            csrf_resp = await client.get(f"{langfuse_base_url}/api/auth/csrf")
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
                f"{langfuse_base_url}/api/auth/callback/credentials",
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

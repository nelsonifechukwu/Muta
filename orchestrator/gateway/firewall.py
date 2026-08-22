"""Fail-closed HTTP identity firewall shared by assembled and split gateway apps."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from orchestrator.gateway.auth import is_operator_request, principal_from_request
from orchestrator.gateway.share_routes import strict_share_security


async def enforce_share_firewall(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    api_prefix: str,
) -> Response:
    """Apply the same role boundary whether the router is mounted at `/v1` or `/`."""
    if not strict_share_security():
        return await call_next(request)
    prefix = api_prefix.rstrip("/")
    path = request.url.path
    operator = is_operator_request(request)
    diagnostics = path in {"/openapi.json", "/redoc", "/docs"} or path.startswith(
        ("/internal/", "/redoc/", "/docs/")
    )
    if diagnostics and not operator:
        return JSONResponse(status_code=404, content={"detail": "not found"})
    if prefix and not path.startswith(f"{prefix}/"):
        return await call_next(request)
    relative = path[len(prefix) :] if prefix else path
    public = {
        "/health",
        "/ready",
        "/share/status",
        "/share/signup",
        "/share/login",
        "/share/logout",
    }
    if relative in public or relative.startswith("/share/enrollments/"):
        return await call_next(request)
    if relative == "/auth/session":
        if operator:
            return await call_next(request)
        return JSONResponse(status_code=403, content={"detail": "host access is local only"})
    principal = principal_from_request(request)
    if principal is None or principal.role == "legacy":
        return JSONResponse(status_code=401, content={"detail": "sign in to continue"})
    if principal.role == "host" and not operator:
        return JSONResponse(status_code=403, content={"detail": "host access is local only"})
    return await call_next(request)

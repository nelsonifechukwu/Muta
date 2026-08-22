"""Muta Share's LAN enrollment, host control, and account-lifecycle API."""

# FastAPI declares dependency injection through call-valued defaults by design.

from __future__ import annotations

import contextlib
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import Response as RawResponse

from contracts.models import (
    ShareCredentials,
    ShareEnrollmentExchange,
    ShareEnrollmentResponse,
    ShareHostStatus,
    ShareHostUpdate,
    ShareLogoutResponse,
    ShareSessionResponse,
    ShareSignupResponse,
    ShareStatus,
    ShareUserAction,
)
from orchestrator.gateway.auth import (
    AuthPrincipal,
    is_operator_request,
    principal_from_request,
    request_token,
    require_principal,
)
from orchestrator.gateway.auxiliary import get_owner_work_manager
from orchestrator.gateway.deps import (
    get_capacity_controller,
    get_engine,
    get_generation_manager,
    get_reaper,
    get_resource_service,
    get_twin_store,
    runtime_lifecycle,
)
from orchestrator.gateway.lan import LanServerError, get_lan_manager
from orchestrator.gateway.sharing import (
    SESSION_COOKIE,
    AuthenticationError,
    EnrollmentError,
    IssuedSession,
    SharingService,
    get_sharing_service,
)

router = APIRouter()


def strict_share_security() -> bool:
    """Strict by default in the product, opt-out only for legacy in-process test clients."""
    configured = os.environ.get("MUTA_SHARE_STRICT")
    if configured is not None:
        return configured.strip().lower() not in {"0", "false", "no", "off"}
    return "PYTEST_CURRENT_TEST" not in os.environ


def _remote_https_required(request: Request) -> None:
    if is_operator_request(request):
        return
    if request.url.scheme != "https":
        raise HTTPException(
            status_code=426,
            detail="use the host's HTTPS join URL before sending a password",
            headers={"Upgrade": "TLS/1.2"},
        )


def _peer_key(request: Request, username: str) -> str:
    peer = request.client.host if request.client else "unknown"
    return f"{peer}:{username.casefold()}"


def _set_session_cookie(response: Response, issued: IssuedSession, *, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


def _member_response(issued: IssuedSession) -> ShareSessionResponse:
    principal = issued.principal
    return ShareSessionResponse(
        user_id=principal.subject,
        username=principal.username or "",
        expires_at=issued.expires_at,
    )


def _host_read(
    request: Request,
    principal: AuthPrincipal = Depends(require_principal),
) -> AuthPrincipal:
    if principal.role != "host" or not is_operator_request(request):
        raise HTTPException(status_code=403, detail="only the laptop operator can do that")
    return principal


def _host_write(
    request: Request,
    principal: AuthPrincipal = Depends(_host_read),
    csrf: str | None = Header(default=None, alias="X-Muta-CSRF"),
) -> AuthPrincipal:
    verify_host_csrf(principal, csrf)
    return principal


def verify_host_csrf(principal: AuthPrincipal, csrf: str | None) -> None:
    if not principal.session_id or not get_sharing_service().verify_csrf(
        principal.session_id, csrf
    ):
        raise HTTPException(status_code=403, detail="invalid host request token")


@router.get("/share/status", response_model=ShareStatus, tags=["sharing"])
def share_status(request: Request) -> ShareStatus:
    service = get_sharing_service()
    settings = service.settings()
    principal = principal_from_request(request)
    manager = get_lan_manager()
    secure = request.url.scheme == "https" or is_operator_request(request)
    message = ""
    if not settings["enabled"]:
        message = "This laptop is not sharing Muta right now."
    elif not secure:
        message = "Open the secure join URL before signing in."
    return ShareStatus(
        enabled=settings["enabled"],
        secure=secure,
        authenticated=principal is not None and principal.role in {"host", "member"},
        role=principal.role if principal and principal.role in {"host", "member"} else None,
        user_id=principal.subject if principal else None,
        username=principal.username if principal else None,
        join_url=manager.primary_url(),
        message=message,
    )


@router.post("/share/signup", response_model=ShareSignupResponse, tags=["sharing"])
def share_signup(request: Request, req: ShareCredentials) -> ShareSignupResponse:
    _remote_https_required(request)
    try:
        result = get_sharing_service().signup(
            req.username,
            req.password,
            throttle_key=_peer_key(request, req.username),
        )
    except (ValueError, EnrollmentError, AuthenticationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ShareSignupResponse.model_validate(result)


@router.post(
    "/share/enrollments/{enrollment_id}",
    response_model=ShareEnrollmentResponse,
    tags=["sharing"],
)
def share_enrollment(
    enrollment_id: str,
    exchange: ShareEnrollmentExchange,
    request: Request,
    response: Response,
) -> ShareEnrollmentResponse:
    _remote_https_required(request)
    try:
        result, issued = get_sharing_service().enrollment(enrollment_id, exchange.secret)
    except EnrollmentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if issued is not None:
        _set_session_cookie(response, issued, secure=not is_operator_request(request))
        result.update(authenticated=True, user_id=issued.principal.subject)
    return ShareEnrollmentResponse.model_validate(result)


@router.post("/share/login", response_model=ShareSessionResponse, tags=["sharing"])
def share_login(
    request: Request, response: Response, req: ShareCredentials
) -> ShareSessionResponse:
    _remote_https_required(request)
    try:
        issued = get_sharing_service().login(
            req.username,
            req.password,
            throttle_key=_peer_key(request, req.username),
        )
    except (ValueError, AuthenticationError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    _set_session_cookie(response, issued, secure=not is_operator_request(request))
    return _member_response(issued)


@router.post("/share/logout", response_model=ShareLogoutResponse, tags=["sharing"])
def share_logout(request: Request, response: Response) -> ShareLogoutResponse:
    token = request_token(request.headers.get("authorization"), request.cookies.get(SESSION_COOKIE))
    get_sharing_service().logout(token)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return ShareLogoutResponse()


@router.get("/share/me", response_model=ShareSessionResponse, tags=["sharing"])
def share_me(principal: AuthPrincipal = Depends(require_principal)) -> ShareSessionResponse:
    if principal.role != "member":
        raise HTTPException(status_code=403, detail="this endpoint is for shared members")
    return ShareSessionResponse(
        user_id=principal.subject,
        username=principal.username or "",
        expires_at="",
    )


def _host_payload(service: SharingService) -> ShareHostStatus:
    settings = service.settings()
    manager = get_lan_manager()
    warning = manager.last_error
    try:
        capacity = get_capacity_controller().status(settings["memory_mode"])
    except (OSError, ValueError) as exc:
        capacity = {}
        warning = str(exc)
    return ShareHostStatus(
        enabled=settings["enabled"],
        memory_mode=settings["memory_mode"],
        listener_running=manager.running,
        join_urls=manager.urls(),
        certificate_fingerprint=manager.certificate_fingerprint(),
        users=service.users(),
        capacity=capacity,
        updated_at=settings["updated_at"],
        warning=warning,
    )


@router.get("/share/host", response_model=ShareHostStatus, tags=["sharing"])
def share_host_status(_principal: AuthPrincipal = Depends(_host_read)) -> ShareHostStatus:
    return _host_payload(get_sharing_service())


@router.put("/share/host", response_model=ShareHostStatus, tags=["sharing"])
def update_share_host(
    request: Request,
    req: ShareHostUpdate,
    _principal: AuthPrincipal = Depends(_host_write),
) -> ShareHostStatus:
    service = get_sharing_service()
    manager = get_lan_manager()
    with runtime_lifecycle():
        previous = service.settings()
        capacity = get_capacity_controller()
        snapshot = capacity.snapshot()
        try:
            capacity.apply(req.memory_mode)
            if req.enabled:
                manager.start(request.app)
            service.update_settings(enabled=req.enabled, memory_mode=req.memory_mode)
            if not req.enabled:
                manager.stop()
        except Exception as exc:
            # This is a small local saga across SQLite, llama-server, and the TLS listener.
            # Any one may fail after another has changed, so restore all three to the snapshot.
            with contextlib.suppress(Exception):
                service.update_settings(
                    enabled=previous["enabled"], memory_mode=previous["memory_mode"]
                )
            with contextlib.suppress(Exception):
                if previous["enabled"]:
                    manager.start(request.app)
                else:
                    manager.stop()
            with contextlib.suppress(Exception):
                capacity.restore(snapshot, previous["memory_mode"])
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _host_payload(service)


@router.post(
    "/share/host/users/{user_id}/approve",
    response_model=ShareUserAction,
    tags=["sharing"],
)
def approve_share_user(
    user_id: str, _principal: AuthPrincipal = Depends(_host_write)
) -> ShareUserAction:
    try:
        get_sharing_service().approve(user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ShareUserAction(id=user_id, status="approved")


@router.post(
    "/share/host/users/{user_id}/reject",
    response_model=ShareUserAction,
    tags=["sharing"],
)
def reject_share_user(
    user_id: str, _principal: AuthPrincipal = Depends(_host_write)
) -> ShareUserAction:
    try:
        get_sharing_service().reject(user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ShareUserAction(id=user_id, status="rejected")


def erase_share_user(user_id: str, service: SharingService | None = None) -> dict[str, int]:
    """Idempotent deletion saga: revoke first, stop work, erase every durable learner store."""
    service = service or get_sharing_service()
    service.begin_removal(user_id)
    generations = get_generation_manager()
    generations.stop_student(user_id)
    if generations.active(user_id):
        raise RuntimeError("a learner generation is still draining")
    if not get_owner_work_manager().stop_owner(user_id):
        raise RuntimeError("a learner image request is still draining")
    if not get_resource_service().stop_owner(user_id):
        raise RuntimeError("a learner resource is still being prepared")
    engine = get_engine()
    conversations = engine.store.list_conversations(user_id)
    for row in conversations:
        conversation_id = row.get("id") if isinstance(row, dict) else getattr(row, "id", None)
        if conversation_id:
            with contextlib.suppress(OSError):
                get_reaper().drop(str(conversation_id))
    counts = engine.store.delete_student(user_id)
    twin = get_twin_store().path_for(user_id)
    twin_removed = int(twin.is_file())
    twin.unlink(missing_ok=True)
    service.finalize_removal(user_id)
    return {**{key: int(value) for key, value in counts.items()}, "learning_twin": twin_removed}


def reconcile_share_deletions() -> None:
    service = get_sharing_service()
    for user_id in service.deleting_ids():
        with contextlib.suppress(Exception):
            erase_share_user(user_id, service)


@router.delete(
    "/share/host/users/{user_id}",
    response_model=ShareUserAction,
    tags=["sharing"],
)
def remove_share_user(
    user_id: str, _principal: AuthPrincipal = Depends(_host_write)
) -> ShareUserAction:
    try:
        erased = erase_share_user(user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="account access is revoked; data cleanup will resume when Muta restarts",
        ) from exc
    return ShareUserAction(id=user_id, status="removed", erased=erased)


@router.get("/share/host/qr.png", tags=["sharing"], response_class=RawResponse)
def share_qr(_principal: AuthPrincipal = Depends(_host_read)) -> RawResponse:
    try:
        body = get_lan_manager().qr_png()
    except LanServerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RawResponse(body, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/share/host/ca.pem", tags=["sharing"], response_class=RawResponse)
def share_ca(_principal: AuthPrincipal = Depends(_host_read)) -> RawResponse:
    try:
        body = get_lan_manager().ca_bytes()
    except LanServerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RawResponse(
        body,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": 'attachment; filename="muta-rootCA.pem"'},
    )

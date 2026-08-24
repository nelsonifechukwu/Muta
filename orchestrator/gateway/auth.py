"""Per-student identity for the `/v1` surface.

The threat this closes: with no notion of a caller, every data endpoint trusted a
client-supplied `student_id`, and attachments were fetched by a guessable serial id — so on
the shared-classroom LAN any device could read or delete any other student's data (the audit's
critical IDOR/broken-access findings).

The model here is deliberately offline and account-free — there is no external identity
provider on a flash-drive deployment. A caller is identified by a **bearer token**:

- **Dev / default (no `MUTA_AUTH_SECRET`)**: the token *is* the student id. The shipped UI
  already generates a random per-device UUID (`crypto.randomUUID()`), so treating it as an
  opaque bearer secret means an attacker must *know* a victim's UUID to act as them — the
  enumerable `1,2,3…` attack is gone, which is the concrete fix the audit asked for.
- **Hardened (set `MUTA_AUTH_SECRET`)**: `mint_token()` issues an HMAC-signed token binding
  the student id, and `verify_token()` rejects anything not signed by this server. Now a
  guessed UUID is not enough — the token cannot be forged. `POST /v1/auth/session` mints one.

Ownership is then enforced at the store (a conversation/attachment is scoped to its owner);
this module only answers "who is calling?". Kept dependency-light so importing the app stays
offline and cheap.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Cookie, Header, HTTPException, Query, Request
from starlette.requests import HTTPConnection

from orchestrator.gateway.sharing import SESSION_COOKIE, SESSION_PREFIX, get_sharing_service

_SECRET_ENV = "MUTA_AUTH_SECRET"
# Bound the token so a signed value cannot be a prompt-bomb in its own right, and reject
# absurd student ids early.
MAX_STUDENT_ID = 128
_OPERATOR_ID_FILE_ENV = "MUTA_OPERATOR_ID_FILE"


@dataclass(frozen=True)
class AuthPrincipal:
    """The single server-resolved identity used across JSON, SSE, media and WebSocket paths."""

    subject: str
    role: Literal["host", "member", "legacy"]
    session_id: str | None = None
    username: str | None = None
    auth_kind: Literal["share", "legacy"] = "legacy"


def _secret() -> bytes | None:
    raw = os.environ.get(_SECRET_ENV)
    return raw.encode("utf-8") if raw else None


def _sign(student_id: str, secret: bytes) -> str:
    return hmac.new(secret, student_id.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def mint_token(student_id: str) -> str:
    """Issue a bearer token for a student id. Signed when a secret is configured, else the
    id itself (the per-device secret model above)."""
    student_id = (student_id or "").strip()
    if not student_id or len(student_id) > MAX_STUDENT_ID:
        raise ValueError("invalid student id")
    secret = _secret()
    if secret is None:
        return student_id
    raw = f"{student_id}:{_sign(student_id, secret)}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def operator_student_id() -> str:
    """Return the persistent random identity used only for loopback operator sessions.

    The id is deliberately stored outside browser state: browser storage is scoped by origin,
    and an SSH tunnel's local port is part of that origin.  An exclusive mode-0600 create keeps
    concurrent first requests from producing different ids.
    """
    path = Path(os.environ.get(_OPERATOR_ID_FILE_ENV, "data/operator-student-id"))

    def read() -> str:
        value = path.read_text().strip()
        parsed = uuid.UUID(value)
        if str(parsed) != value:
            raise ValueError("operator student id must be a canonical UUID")
        return value

    try:
        return read()
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        value = str(uuid.uuid4())
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return read()
        with os.fdopen(fd, "w") as stream:
            stream.write(value + "\n")
        return value


def verify_token(token: str | None) -> str | None:
    """Resolve a bearer token to its student id, or None if it is missing/forged."""
    if not token:
        return None
    token = token.strip()
    if token.startswith(SESSION_PREFIX):
        principal = get_sharing_service().resolve_session(token)
        return principal.subject if principal is not None else None
    secret = _secret()
    if secret is None:
        return token if 0 < len(token) <= MAX_STUDENT_ID else None
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        student_id, sig = raw.rsplit(":", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    if not student_id or len(student_id) > MAX_STUDENT_ID:
        return None
    return student_id if hmac.compare_digest(sig, _sign(student_id, secret)) else None


def _token_from_header(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def request_token(
    authorization: str | None,
    session_cookie: str | None,
    query_token: str | None = None,
) -> str | None:
    """Prefer the HttpOnly share cookie; retain header/query compatibility for local tools."""
    return session_cookie or _token_from_header(authorization) or query_token


def resolve_principal(token: str | None) -> AuthPrincipal | None:
    if not token:
        return None
    if token.startswith(SESSION_PREFIX):
        principal = get_sharing_service().resolve_session(token)
        if principal is None:
            return None
        return AuthPrincipal(
            subject=principal.subject,
            role=principal.role,
            session_id=principal.session_id,
            username=principal.username,
            auth_kind="share",
        )
    student_id = verify_token(token)
    if student_id is None:
        return None
    return AuthPrincipal(subject=student_id, role="legacy", auth_kind="legacy")


def principal_from_request(request: Request) -> AuthPrincipal | None:
    return resolve_principal(
        request_token(
            request.headers.get("authorization"),
            request.cookies.get(SESSION_COOKIE),
            request.query_params.get("token"),
        )
    )


@contextmanager
def member_write_lease(principal: AuthPrincipal | None) -> Iterator[None]:
    """Serialize a member's durable write with host account removal.

    Host and legacy-local identities do not live in the Host-mode roster and therefore do
    not need this lease. Strict-mode member identities do.
    """
    if principal is not None and principal.role == "member":
        with get_sharing_service().member_write(principal.subject):
            yield
        return
    yield


def _is_ip_loopback(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _operator_host_allowed(request: HTTPConnection) -> bool:
    allowed = {"localhost", "127.0.0.1", "::1"}
    allowed.update(
        item.strip().lower().rstrip(".")
        for item in os.environ.get("MUTA_OPERATOR_HOSTS", "").split(",")
        if item.strip()
    )
    raw_host = request.headers.get("host", "")
    try:
        host = urlsplit(f"//{raw_host}").hostname or ""
    except ValueError:
        return False
    if host.lower().rstrip(".") not in allowed:
        return False
    # Browsers attach Origin to state-changing fetches. Reject a DNS-rebinding origin while
    # allowing local CLI clients that intentionally send no Origin header.
    origin = request.headers.get("origin")
    if origin:
        try:
            origin_host = urlsplit(origin).hostname or ""
        except ValueError:
            return False
        if origin_host.lower().rstrip(".") not in allowed:
            return False
    return True


def is_loopback_request(request: HTTPConnection) -> bool:
    """Only the direct primary listener can bootstrap host authority.

    Forwarded headers deliberately do not count. The operator URL is the loopback-only backend
    listener; the separate TLS LAN listener preserves the actual peer and can never mint a host.
    """
    peer = request.client.host if request.client else ""
    return _is_ip_loopback(peer)


def is_operator_request(request: HTTPConnection) -> bool:
    """Trust the loopback listener, including its container-only port after host NAT.

    Compose publishes container port 8000 on host 127.0.0.1 only. The application therefore
    sees the bridge peer rather than 127.0.0.1, but can distinguish that private primary
    listener from Host mode's dedicated 8443 listener by the ASGI server port.
    """
    if not _operator_host_allowed(request):
        return False
    server = request.scope.get("server")
    server_port = int(server[1]) if server else None
    # A laptop-side SSH relay makes a learner request arrive at GCP from 127.0.0.1. Listener
    # identity is therefore load-bearing: the dedicated TLS share port can never mint or reuse
    # host authority, even when its peer and a forged Host header both look loopback-local.
    if server_port == int(os.environ.get("MUTA_SHARE_PORT", "8443")):
        return False
    if is_loopback_request(request):
        return True
    if os.environ.get("MUTA_TRUST_PRIMARY_LISTENER") != "1":
        return False
    return bool(
        server_port is not None
        and server_port == int(os.environ.get("MUTA_PRIMARY_PORT", "8000"))
    )


def require_principal(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> AuthPrincipal:
    principal = resolve_principal(request_token(authorization, session_cookie))
    if principal is None:
        raise HTTPException(status_code=401, detail="sign in to continue")
    return principal


def require_caller(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> str:
    """FastAPI dependency: the authenticated student id, or 401. For endpoints a fetch()
    client reaches (it can set the Authorization header)."""
    principal = resolve_principal(request_token(authorization, session_cookie))
    if principal is None:
        raise HTTPException(status_code=401, detail="sign in to continue")
    return principal.subject


def optional_caller(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> str | None:
    """Resolve an optional bearer token for legacy-public endpoints with private extensions."""
    principal = resolve_principal(request_token(authorization, session_cookie))
    return principal.subject if principal is not None else None


def caller_from_token(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    token: str | None = Query(default=None),
) -> str:
    """FastAPI dependency for URLs a browser loads directly (an <img>/download link cannot
    set headers): accept the token from the Authorization header *or* a `?token=` query param.
    401 when neither resolves."""
    principal = resolve_principal(request_token(authorization, session_cookie, token))
    if principal is None:
        raise HTTPException(status_code=401, detail="sign in to continue")
    return principal.subject

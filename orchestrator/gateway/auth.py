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
import os
import uuid
from pathlib import Path

from fastapi import Header, HTTPException, Query

_SECRET_ENV = "MUTA_AUTH_SECRET"
# Bound the token so a signed value cannot be a prompt-bomb in its own right, and reject
# absurd student ids early.
MAX_STUDENT_ID = 128
_OPERATOR_ID_FILE_ENV = "MUTA_OPERATOR_ID_FILE"


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


def require_caller(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: the authenticated student id, or 401. For endpoints a fetch()
    client reaches (it can set the Authorization header)."""
    student_id = verify_token(_token_from_header(authorization))
    if student_id is None:
        raise HTTPException(status_code=401, detail="sign in to continue")
    return student_id


def caller_from_token(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> str:
    """FastAPI dependency for URLs a browser loads directly (an <img>/download link cannot
    set headers): accept the token from the Authorization header *or* a `?token=` query param.
    401 when neither resolves."""
    student_id = verify_token(_token_from_header(authorization) or token)
    if student_id is None:
        raise HTTPException(status_code=401, detail="sign in to continue")
    return student_id

"""Streaming ASGI request-body ceiling for the direct Host-mode listener."""

from __future__ import annotations

import os

from starlette.responses import JSONResponse


class _RequestTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int | None = None) -> None:
        self.app = app
        self.max_bytes = max_bytes or int(
            os.environ.get("MUTA_MAX_REQUEST_BYTES", str(32 * 1024 * 1024))
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", ()))
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                if int(raw_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(status_code=400, content={"detail": "invalid body size"})
                await response(scope, receive, send)
                return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestTooLarge:
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope, receive, send) -> None:
        response = JSONResponse(status_code=413, content={"detail": "request body is too large"})
        await response(scope, receive, send)

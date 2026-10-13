"""Bound upload bodies before multipart parsing, including chunked requests."""

from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        size = 0
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = self.max_bytes + 1
        if declared > self.max_bytes:
            return await JSONResponse(
                {"detail": "Request body exceeds the upload limit."}, status_code=413
            )(scope, receive, send)

        async def bounded_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                # Starlette turns this into a client-safe parsing error; it never consumes more body.
                raise ValueError("Request body exceeds the upload limit.")
            return message

        return await self.app(scope, bounded_receive, send)

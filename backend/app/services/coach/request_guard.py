"""Coach-only normalized validation/errors; no secret input echo or debug traceback."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings


class CoachRequestGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(f"{get_settings().api_prefix}/coach/"):
            return await call_next(request)
        length = request.headers.get("content-length")
        if length and (not length.isdecimal() or int(length) > 16_384):
            return JSONResponse({"detail": "request_too_large"}, status_code=413)
        # Bounded body even for chunked transport; never log/reflect it.
        size, pieces = 0, []
        async for piece in request.stream():
            size += len(piece)
            if size > 16_384:
                return JSONResponse({"detail": "request_too_large"}, status_code=413)
            pieces.append(piece)
        request._body = b"".join(pieces)
        try:
            response = await call_next(request)
        except Exception:
            return JSONResponse({"detail": "coach_internal_error"}, status_code=500)
        # FastAPI validation includes raw input; completely replace its body.
        if response.status_code == 422:
            response = JSONResponse({"detail": "invalid_coach_request"}, status_code=422)
        # Only content-addressed pack clips (immutable by fingerprint) may be cached.
        immutable_clip = (response.status_code == 200 and "/coach/packs/" in request.url.path
                          and "immutable" in response.headers.get("cache-control", ""))
        if not immutable_clip:
            response.headers["Cache-Control"] = "no-store"
        return response
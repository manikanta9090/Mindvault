"""Request-scoped middleware."""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from fastapi import Request, Response

from app.core.logging import logger

NextHandler = Callable[[Request], Awaitable[Response]]


async def request_logging_middleware(request: Request, call_next: NextHandler) -> Response:
    """Log one structured record per HTTP request."""

    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http_request_failed",
            extra={"method": request.method, "path": request.url.path},
        )
        raise

    logger.info(
        "http_request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
    )
    return response

"""Application middleware."""
from fastapi import Request
from starlette.concurrency import run_in_threadpool

from app.core.errors import api_error
from app.core.security import utcnow
from app.services.auth_limits import allow_auth_request


async def auth_rate_limit(request: Request, call_next):
    if request.method == 'POST' and request.url.path.startswith('/api/v1/auth/'):
        now = utcnow()
        minute = now.replace(second=0, microsecond=0)
        address = request.client.host if request.client else 'unknown'
        if not await run_in_threadpool(allow_auth_request, request.app.state.engine,
                                       request.app.state.jwt_secret, address, minute):
            response = api_error(429, 'RATE_LIMITED', '请求过于频繁，请稍后再试')
            response.headers['Retry-After'] = str(60 - now.second)
            return response
    return await call_next(request)

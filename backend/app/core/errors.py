"""Uniform API error type and JSON error response helpers."""
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: dict | None = None):
        self.status, self.code, self.message = status, code, message
        self.detail = detail or {}


def api_error(status: int, code: str, message: str, detail: dict | None = None) -> JSONResponse:
    headers = {'Cache-Control': 'no-store'}
    if status == 401:
        headers['WWW-Authenticate'] = 'Bearer'
    return JSONResponse({'code': code, 'message': message, 'detail': detail or {}},
                        status_code=status, headers=headers)


def auth_required() -> JSONResponse:
    return api_error(401, 'AUTH_REQUIRED', '请检查登录信息或重新登录')

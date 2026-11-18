import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine

from app.auth import APIError, api_error, auth_rate_limit, router
from app.media import PhotoStorage
from app.media_api import router as media_router
from app.pet_api import router as pet_router
from app.task_api import router as task_router


def health():
    return {'status': 'ok'}


app = FastAPI(title='绒星 API', version='0.1.0')
app.get('/api/v1/health')(health)


def create_dev_app():
    url = os.environ.get('DATABASE_URL')
    secret = os.environ.get('JWT_SECRET', '')
    if not url:
        raise RuntimeError('DATABASE_URL is required for local auth')
    if len(secret.encode('utf-8')) < 32:
        raise RuntimeError('JWT_SECRET must be at least 32 bytes')

    @asynccontextmanager
    async def lifespan(instance: FastAPI):
        engine = create_engine(url, hide_parameters=True)
        instance.state.engine = engine
        try:
            yield
        finally:
            engine.dispose()

    instance = FastAPI(title='绒星 API（本地联调）', version='0.1.0', lifespan=lifespan)
    instance.state.jwt_secret = secret
    versions = {kind: os.environ.get(f'{kind.upper()}_VERSION', '').strip() for kind in ('privacy', 'terms')}
    if any(len(version) > 32 for version in versions.values()):
        raise RuntimeError('Policy versions must be at most 32 characters')
    instance.state.policy_versions = versions
    links = {kind: os.environ.get(f'{kind.upper()}_URL', '').strip() for kind in versions}
    for link in filter(None, links.values()):
        parsed = urlsplit(link)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None:
            raise RuntimeError('Policy URLs must be HTTPS links')
    instance.state.policy_links = links
    instance.state.photo_storage = PhotoStorage.from_env()
    instance.get('/api/v1/health')(health)
    instance.include_router(router)
    instance.include_router(pet_router)
    instance.include_router(task_router)
    instance.include_router(media_router)
    instance.middleware('http')(auth_rate_limit)
    instance.add_middleware(CORSMiddleware, allow_origin_regex=r'http://(?:localhost|127\.0\.0\.1):[0-9]+',
                            allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
                            allow_headers=['Authorization', 'Content-Type'])

    @instance.exception_handler(APIError)
    async def rejected(_request: Request, error: APIError):
        return api_error(error.status, error.code, error.message)

    @instance.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError):
        return api_error(400, 'VALIDATION_ERROR', '请检查请求字段')

    return instance

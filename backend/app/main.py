import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine

from app.auth import APIError, api_error, auth_rate_limit, router
from app.avatar_api import router as avatar_router
from app.avatar_assets_api import router as avatar_assets_router
from app.config_api import router as config_router
from app.media import PhotoStorage
from app.rules import load_action_map
from app.media_api import router as media_router
from app.pet_api import router as pet_router
from app.placeholders import load_library
from app.health_api import router as health_router
from app.screening_api import router as screening_router
from app.task_api import router as task_router
from app.advice import load_advice_templates
from app.triage import load_rules


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
    rules_dir = Path(os.environ.get('RULES_DIR') or Path(__file__).resolve().parents[1] / 'rules')
    instance.state.action_map = load_action_map(rules_dir)
    instance.state.triage_rules = load_rules(rules_dir)
    instance.state.advice_templates = load_advice_templates(rules_dir)
    placeholder_dir = Path(os.environ.get('PLACEHOLDER_DIR') or Path(__file__).resolve().parents[1] / 'assets' / 'placeholders')
    instance.state.placeholder_library = load_library(placeholder_dir)
    instance.get('/api/v1/health')(health)
    instance.include_router(router)
    instance.include_router(pet_router)
    instance.include_router(avatar_router)
    instance.include_router(avatar_assets_router)
    instance.include_router(task_router)
    instance.include_router(media_router)
    instance.include_router(config_router)
    instance.include_router(screening_router)
    instance.include_router(health_router)
    instance.middleware('http')(auth_rate_limit)
    instance.add_middleware(CORSMiddleware, allow_origin_regex=r'http://(?:localhost|127\.0\.0\.1):[0-9]+',
                            allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
                            allow_headers=['Authorization', 'Content-Type'])

    @instance.exception_handler(APIError)
    async def rejected(_request: Request, error: APIError):
        return api_error(error.status, error.code, error.message, error.detail)

    @instance.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError):
        return api_error(400, 'VALIDATION_ERROR', '请检查请求字段')

    return instance

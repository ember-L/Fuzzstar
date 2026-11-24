"""Operations console: admin-only APIs and the static console shell.

Admin access is granted by listing an already verified account email in
``ADMIN_EMAILS``. There is no separate admin password: the console signs in
through the normal auth endpoint, so sessions, revocation and rate limits keep
working exactly as they do for the mobile app.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT
from app.core.db import get_db
from app.core.deps import admin_user
from app.core.errors import APIError
from app.core.security import utcnow
from app.models import User
from app.services import admin_stats

ADMIN_DIR = BACKEND_ROOT / 'admin'
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

router = APIRouter()
api = APIRouter(prefix='/api/v1/admin', tags=['admin'])


class UserStatusInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: Literal['active', 'suspended']


def _no_store(response: Response) -> None:
    response.headers['Cache-Control'] = 'no-store'


@api.get('/session')
def admin_session(response: Response, admin: User = Depends(admin_user),
                  db: Session = Depends(get_db)):
    _no_store(response)
    email = admin_stats.user_email(db, admin.id)
    return {
        'admin': {'id': admin.id, 'nickname': admin.nickname, 'email': email},
        'console': {'title': '绒星 · 运营管理台', 'window_days': 30},
    }


@api.get('/overview')
def admin_overview(response: Response, days: int = Query(30, ge=1, le=180),
                   _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    _no_store(response)
    return admin_stats.overview(db, now=utcnow(), days=days)


@api.get('/users')
def admin_users(response: Response, query: str = Query('', max_length=80), status: str = 'all',
                page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    _no_store(response)
    return admin_stats.list_users(db, query=query, status=status,
                                  page=page, page_size=page_size)


@api.get('/users/{user_id}')
def admin_user_detail(user_id: int, response: Response, _admin: User = Depends(admin_user),
                      db: Session = Depends(get_db)):
    _no_store(response)
    detail = admin_stats.user_detail(db, user_id)
    if detail is None:
        raise APIError(404, 'NOT_FOUND', '未找到该用户')
    return detail


@api.patch('/users/{user_id}/status')
def admin_update_user_status(user_id: int, data: UserStatusInput, response: Response,
                             admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    _no_store(response)
    try:
        result = admin_stats.set_user_status(db, admin=admin, user_id=user_id,
                                            status=data.status, now=utcnow())
    except LookupError as exc:
        raise APIError(404, 'NOT_FOUND', '未找到该用户') from exc
    except PermissionError as exc:
        raise APIError(409, 'STATUS_LOCKED', str(exc)) from exc
    except ValueError as exc:
        raise APIError(400, 'VALIDATION_ERROR', str(exc)) from exc
    return result


@api.get('/pets')
def admin_pets(response: Response, query: str = Query('', max_length=80), status: str = 'all',
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
               _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    _no_store(response)
    return admin_stats.list_pets(db, query=query, status=status,
                                 page=page, page_size=page_size)


@api.get('/screenings')
def admin_screenings(request: Request, response: Response, query: str = Query('', max_length=80),
                     state: str = 'all', redline: str = 'all', page: int = Query(1, ge=1),
                     page_size: int = Query(20, ge=1, le=100),
                     _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    _no_store(response)
    return admin_stats.list_screenings(db, query=query, state=state, redline=redline,
                                       page=page, page_size=page_size,
                                       bundle=request.app.state.triage_rules)


@api.get('/screenings/{screening_id}')
def admin_screening_detail(screening_id: int, request: Request, response: Response,
                           _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    _no_store(response)
    detail = admin_stats.screening_detail(db, screening_id,
                                          bundle=request.app.state.triage_rules)
    if detail is None:
        raise APIError(404, 'NOT_FOUND', '未找到该初筛记录')
    return detail


@api.get('/ai-usage')
def admin_ai_usage(response: Response, days: int = Query(30, ge=1, le=180),
                   _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    _no_store(response)
    return admin_stats.ai_usage(db, now=utcnow(), days=days)


@api.get('/audit')
def admin_audit(response: Response, page: int = Query(1, ge=1),
                page_size: int = Query(20, ge=1, le=100),
                _admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    _no_store(response)
    return admin_stats.audit_log(db, page=page, page_size=page_size)


@router.get('/admin', include_in_schema=False)
@router.get('/admin/', include_in_schema=False)
def admin_console():
    page = (ADMIN_DIR / 'index.html').read_text(encoding='utf-8')
    return HTMLResponse(page, headers={
        'Cache-Control': 'no-store',
        'Content-Security-Policy': CSP,
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer',
    })


class AdminAssets(StaticFiles):
    """Static assets for the console, cached briefly and never sniffed."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-cache'
        return response


def install_assets(app) -> None:
    app.mount('/admin/assets', AdminAssets(directory=str(ADMIN_DIR / 'assets')),
              name='admin-assets')

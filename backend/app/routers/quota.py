"""T17 F11-2/3: quota display and read-only plans/entitlements (no billing)."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user
from app.core.security import utcnow
from app.models import Entitlement, Plan, User
from app.services.quota import quota_snapshot

router = APIRouter(prefix='/api/v1')

# Code-defined catalog (Ruling: tables exist for future paid plans; v1 serves
# this catalog, never prices, and the paywall answer is always 测试期免费).
PLANS = [
    {'code': 'free', 'name': '免费版',
     'entitlements': {'screening_per_day': 10, 'avatar_gen_per_day': 3, 'chat_msg_per_day': 50,
                      'gif_export': True, 'audio_interpret': True}},
    {'code': 'pro', 'name': '专业版（规划中）',
     'entitlements': {'screening_per_day': 30, 'avatar_gen_per_day': 10, 'chat_msg_per_day': 200,
                      'gif_export': True, 'audio_interpret': True, 'priority_support': True}},
]
PAYWALL_MESSAGE = '测试期免费'


@router.get('/quota')
def read_quota(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return quota_snapshot(db, user.id, now=utcnow())


@router.get('/plans')
def list_plans(response: Response, _user: User = Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return {'items': PLANS}


@router.get('/me/entitlement')
def my_entitlement(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    row = db.execute(select(Entitlement, Plan).join(Plan, Plan.id == Entitlement.plan_id)
                     .where(Entitlement.user_id == user.id)).first()
    if row is None:
        return {'plan': 'free', 'status': 'active', 'message': PAYWALL_MESSAGE,
                'entitlements': PLANS[0]['entitlements'], 'expires_at': None}
    entitlement, plan = row
    return {'plan': plan.code, 'status': entitlement.status, 'message': PAYWALL_MESSAGE,
            'entitlements': plan.entitlements,
            'expires_at': entitlement.expires_at.isoformat() if entitlement.expires_at else None}

"""版本化配置下发（ARCHITECTURE：GET /config/action-map）。"""
from fastapi import APIRouter, Depends, Request, Response

from app.auth import APIError
from app.pet_api import consented_user

router = APIRouter(prefix='/api/v1/config', tags=['config'])


@router.get('/action-map')
def action_map(request: Request, response: Response, _user=Depends(consented_user)):
    mapping = request.app.state.action_map
    if mapping is None:
        raise APIError(503, 'CONFIG_UNAVAILABLE', '动作映射配置缺失')
    response.headers['Cache-Control'] = 'no-store'
    return mapping

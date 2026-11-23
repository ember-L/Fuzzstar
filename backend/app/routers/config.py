"""版本化配置下发（ARCHITECTURE：GET /config/action-map、/config/motion）。"""
from fastapi import APIRouter, Depends, Request, Response

from app.core.errors import APIError
from app.core.deps import consented_user
from app.routers.motion import public_config

router = APIRouter(prefix='/api/v1/config', tags=['config'])


@router.get('/action-map')
def action_map(request: Request, response: Response, _user=Depends(consented_user)):
    mapping = request.app.state.action_map
    if mapping is None:
        raise APIError(503, 'CONFIG_UNAVAILABLE', '动作映射配置缺失')
    response.headers['Cache-Control'] = 'no-store'
    return mapping


@router.get('/motion')
def motion_config(request: Request, response: Response, _user=Depends(consented_user)):
    """F14-4：动作集、状态与手势映射随配置下发，改映射不发版。"""
    config = request.app.state.motion_config
    if config is None:
        raise APIError(503, 'MOTION_UNAVAILABLE', '萌宠动图配置缺失')
    response.headers['Cache-Control'] = 'no-store'
    return public_config(config)

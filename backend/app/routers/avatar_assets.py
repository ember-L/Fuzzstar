"""占位资产下发（FRD F03-4）：版本化清单 + 公开只读片文件。

片文件为通用占位内容（非用户数据），公开读；版本化路径不可变，可长缓存。
"""
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse

from app.core.errors import APIError
from app.core.deps import consented_user
from app.services.placeholders import manifest_payload

router = APIRouter(prefix='/api/v1/avatar', tags=['avatar'])


def require_library(request: Request):
    library = request.app.state.placeholder_library
    if library is None:
        raise APIError(503, 'PLACEHOLDER_UNAVAILABLE', '占位片库尚未构建')
    return library


def placeholder_base_url(request: Request) -> str:
    return str(request.base_url).rstrip('/') + '/api/v1/avatar/placeholders'


def group_payload(library, body_type: str, base_url: str) -> dict:
    version = library.manifest['version']
    return {'version': version, 'body_type': body_type,
            'clips': {action: f'{base_url}/{version}/{body_type}/{action}.mp4'
                      for action in library.manifest['actions']}}


@router.get('/placeholder-manifest')
def placeholder_manifest(request: Request, response: Response, _user=Depends(consented_user)):
    library = require_library(request)
    response.headers['Cache-Control'] = 'no-store'
    return manifest_payload(library, base_url=placeholder_base_url(request))


@router.get('/placeholders/{version}/{body_type}/{filename}')
def placeholder_clip(version: str, body_type: str, filename: str, request: Request):
    library = require_library(request)
    if not filename.endswith('.mp4'):
        raise APIError(404, 'NOT_FOUND', '未找到占位片')
    path = library.clip_path(version, body_type, filename[:-4])
    if path is None or not path.is_file():
        raise APIError(404, 'NOT_FOUND', '未找到占位片')
    return FileResponse(path, media_type='video/mp4',
                        headers={'Cache-Control': 'public, max-age=31536000, immutable'})

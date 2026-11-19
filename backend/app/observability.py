"""T18: structured JSON logs (ARCH:517) with a strict redaction policy.

Never log query strings, request bodies, headers, emails, passwords or tokens.
user_id is an internal integer; request_id correlates client and server traces.
"""
import json
import logging
import re
import time
from uuid import uuid4

import jwt

ACCESS = logging.getLogger('rongxing.access')
WORKER = logging.getLogger('rongxing.worker')
QUOTA = logging.getLogger('rongxing.quota')

_REQUEST_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
QUOTA_DENIAL_RETENTION_DAYS = 90


def _emit(logger, **fields):
    logger.info(json.dumps(fields, ensure_ascii=False, default=str))


def log_task_event(event, *, task_id, task_type, attempts=None, status=None):
    fields = {'event': event, 'task_id': task_id, 'task_type': task_type}
    if attempts is not None:
        fields['attempts'] = attempts
    if status is not None:
        fields['status'] = status
    _emit(WORKER, **fields)


def log_quota_denial(user_id, metric, used, limit):
    _emit(QUOTA, event='quota_denied', user_id=user_id, metric=metric, used=used, limit=limit)


def _bearer_user_id(request):
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer '):
        return None
    try:
        # Best-effort correlation only; authorization itself is verified downstream.
        claims = jwt.decode(header[7:], options={'verify_signature': False})
        sub = claims.get('sub')
        return int(sub) if isinstance(sub, str) and sub.isdigit() else None
    except Exception:
        return None


async def request_log(request, call_next):
    incoming = request.headers.get('x-request-id', '')
    request_id = incoming if _REQUEST_ID.match(incoming) else uuid4().hex
    started = time.perf_counter()
    user_id = _bearer_user_id(request)

    def emit(status):
        _emit(ACCESS, event='http', request_id=request_id, method=request.method,
              path=request.url.path, status=status,
              duration_ms=round((time.perf_counter() - started) * 1000, 2), user_id=user_id)

    try:
        response = await call_next(request)
    except Exception:
        emit(500)
        raise
    response.headers['X-Request-ID'] = request_id
    emit(response.status_code)
    return response

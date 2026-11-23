"""浅离线幂等补发（FRD F07-5 / AC-07-5）：通用 Idempotency-Key 去重。

客户端 retry_queue 用同一键重发；服务端只缓存成功响应（2xx），
同键不同载荷返回 409，过期行由 worker sweep 按 IDEMPOTENCY_TTL 清理。
占位行先于业务记录写入并同事务提交，唯一约束挡住并发双写。
"""
import hashlib
import json
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.models import RequestIdempotency

IDEMPOTENCY_TTL = timedelta(days=7)
MAX_KEY_LENGTH = 64


def validate_key(key: Optional[str]) -> Optional[str]:
    if key is None:
        return None
    if not 1 <= len(key) <= MAX_KEY_LENGTH or not key.isprintable():
        raise APIError(400, 'VALIDATION_ERROR', 'Idempotency-Key 需为 1–64 个可打印字符')
    return key


def hash_request(path: str, body: dict) -> str:
    canonical = json.dumps([path, body], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def find_replay(db: Session, user_id: int, key: str, request_hash: str) -> Optional[dict]:
    row = db.scalar(select(RequestIdempotency).where(
        RequestIdempotency.user_id == user_id, RequestIdempotency.key == key))
    if row is None:
        return None
    if row.request_hash != request_hash or row.response_json is None:
        raise APIError(409, 'IDEMPOTENCY_CONFLICT', '该幂等键已用于不同的请求')
    return row.response_json

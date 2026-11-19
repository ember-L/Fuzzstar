"""T18 local p95 sampling of non-AI GET endpoints (in-process ASGI).

Methodology: temporary SQLite + seeded account/pet/diet/weight/task; requests
through the full middleware stack timed with perf_counter. The 500ms gate is a
LOCAL regression guard, not a production performance claim (FRD non-functional
acceptance needs real-device/load-test evidence).

Usage: python -m scripts.latency_sample [--samples 200] [--json]
"""
import argparse
import json
import math
import os
import time
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import main as app_main
from app.auth import utcnow
from app.identity import create_email_account, verify_email
from app.models import Base
from app.tasks import enqueue_task

ENDPOINTS = ('health', 'pets', 'pet_health', 'quota', 'diet_day', 'weights', 'action_map', 'task')
GATE_MS = 500


def _percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _stats(durations_ms):
    return {'n': len(durations_ms),
            'p50_ms': round(_percentile(durations_ms, 0.50), 2),
            'p95_ms': round(_percentile(durations_ms, 0.95), 2),
            'max_ms': round(max(durations_ms), 2)}


def measure(*, samples=200):
    with TemporaryDirectory() as tmp:
        url = 'sqlite:///' + str(Path(tmp) / 'bench.db')
        env = {'DATABASE_URL': url, 'JWT_SECRET': 'bench-signing-key-32-bytes-or-more',
               'PRIVACY_VERSION': 'p1', 'TERMS_VERSION': 't1',
               'PRIVACY_URL': 'https://example.com/privacy', 'TERMS_URL': 'https://example.com/terms'}
        with patch.dict(os.environ, env):
            app = app_main.create_dev_app()
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        now = utcnow()
        with Session(engine) as db, db.begin():
            token = create_email_account(db, 'bench@example.com', 'Strong123', now)
            verify_email(db, token, now)
        all_durations = []
        endpoints = {}
        with TestClient(app) as client:
            access = client.post('/api/v1/auth/login',
                                 json={'email': 'bench@example.com', 'password': 'Strong123'}).json()['access_token']
            headers = {'Authorization': f'Bearer {access}'}
            client.post('/api/v1/consents', json={'privacy': 'p1', 'terms': 't1'}, headers=headers)
            pet_id = client.post('/api/v1/pets', json={'name': '压测猫'}, headers=headers).json()['id']
            client.post(f'/api/v1/pets/{pet_id}/diet', json={'food_type': 'dry', 'amount_g': 50}, headers=headers)
            client.post(f'/api/v1/pets/{pet_id}/weights', json={'weight_kg': 4.0}, headers=headers)
            with Session(engine) as db, db.begin():
                task = enqueue_task(db, pet_id, 'avatar_batch', 'bench-media', {'media_id': 'bench-media'})
                task_id = task.id
            paths = {
                'health': '/api/v1/health',
                'pets': '/api/v1/pets',
                'pet_health': f'/api/v1/pets/{pet_id}/health',
                'quota': '/api/v1/quota',
                'diet_day': f'/api/v1/pets/{pet_id}/diet?date={now.date().isoformat()}&tz_offset_minutes=0',
                'weights': f'/api/v1/pets/{pet_id}/weights',
                'action_map': '/api/v1/config/action-map',
                'task': f'/api/v1/tasks/{task_id}',
            }
            for name in ENDPOINTS:
                durations = []
                for _ in range(samples):
                    started = time.perf_counter()
                    response = client.get(paths[name], headers=headers)
                    durations.append((time.perf_counter() - started) * 1000)
                    if response.status_code != 200:
                        raise RuntimeError(f'{name} returned {response.status_code}: {response.text[:200]}')
                endpoints[name] = _stats(durations)
                all_durations.extend(durations)
        engine.dispose()
    overall = _stats(all_durations)
    return {'samples_per_endpoint': samples, 'gate_ms': GATE_MS, 'endpoints': endpoints,
            'overall': overall, 'passed': overall['p95_ms'] <= GATE_MS}


def main():
    parser = argparse.ArgumentParser(description='非 AI 接口本地 p95 采样')
    parser.add_argument('--samples', type=int, default=200)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = measure(samples=args.samples)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"非 AI 接口本地采样（每端点 {args.samples} 次，进程内 ASGI，门禁 p95≤{GATE_MS}ms）")
        for name, stats in report['endpoints'].items():
            print(f"  {name:12s} n={stats['n']:4d} p50={stats['p50_ms']:8.2f}ms "
                  f"p95={stats['p95_ms']:8.2f}ms max={stats['max_ms']:8.2f}ms")
        overall = report['overall']
        print(f"  总体         n={overall['n']:4d} p50={overall['p50_ms']:8.2f}ms "
              f"p95={overall['p95_ms']:8.2f}ms max={overall['max_ms']:8.2f}ms")
        print('门禁：' + ('通过' if report['passed'] else '未通过'))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()

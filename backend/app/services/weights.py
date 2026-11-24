"""T13 体重骤变检测（FRD F08-2）：纯规则，7 天内 ±10% 标注并建议初筛。"""

from datetime import timedelta


def detect_sudden_change(points: list[dict], *, window_days: int = 7, threshold: float = 10.0) -> dict | None:
    """points: [{'weight_kg': float, 'measured_at': datetime}]；返回 |pct| 最大的触发项。"""
    if len(points) < 2:
        return None
    ordered = sorted(points, key=lambda p: p['measured_at'])
    latest = ordered[-1]
    window_start = latest['measured_at'] - timedelta(days=window_days)
    best = None
    for base in ordered[:-1]:
        if not window_start <= base['measured_at'] < latest['measured_at']:
            continue
        if base['weight_kg'] <= 0:
            continue
        pct = (latest['weight_kg'] - base['weight_kg']) / base['weight_kg'] * 100
        # 浮点容差：恰好 ±10% 视为触发（FRD「≥10%」含边界）。
        if (pct <= -threshold + 1e-9 or pct >= threshold - 1e-9) and (best is None or abs(pct) > abs(best[0])):
            best = (pct, base)
    if best is None:
        return None
    pct, base = best
    return {
        'direction': 'loss' if pct < 0 else 'gain',
        'pct': round(pct, 1),
        'baseline': {'weight_kg': base['weight_kg'], 'measured_at': base['measured_at'].isoformat()},
        'latest': {'weight_kg': latest['weight_kg'], 'measured_at': latest['measured_at'].isoformat()},
        'suggestion': 'screening',
    }

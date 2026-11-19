// 体重记录纯逻辑（F08）：范围/精度校验、时间回改档位、骤变文案、趋势区间与时间线映射。
// 自包含（不跨 lib 值导入），Node 可直接测试。

export interface WeightRecord {
  id: number;
  weight_kg: number;
  measured_at: string;
}

export interface WeightTrendAlert {
  direction: 'loss' | 'gain';
  pct: number;
  baseline: { weight_kg: number; measured_at: string };
  latest: { weight_kg: number; measured_at: string };
  suggestion: 'screening';
}

export type WeightResult = { ok: true; value: number } | { ok: false; message: string };

export function parseWeight(text: string): WeightResult {
  const trimmed = text.trim();
  if (!trimmed) return { ok: false, message: '请输入体重' };
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return { ok: false, message: '体重需为数字' };
  if (value < 0.1 || value > 30) return { ok: false, message: '体重需在 0.1–30kg 之间' };
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return { ok: false, message: '体重最多保留 2 位小数（精度 0.01kg）' };
  return { ok: true, value };
}

export const BACKDATE_OPTIONS: { label: string; hours: number }[] = [
  { label: '现在', hours: 0 },
  { label: '1 小时前', hours: 1 },
  { label: '3 小时前', hours: 3 },
  { label: '6 小时前', hours: 6 },
  { label: '12 小时前', hours: 12 },
  { label: '昨天此时', hours: 24 },
  { label: '2 天前', hours: 48 },
  { label: '3 天前', hours: 72 },
];

export function measuredAtFor(hours: number, now: Date = new Date()): string {
  return new Date(now.getTime() - hours * 3600000).toISOString();
}

export const SCREENING_SUGGESTION = '建议做一次健康初筛';

export function alertText(alert: WeightTrendAlert | null): string {
  if (!alert) return '';
  const magnitude = Math.abs(alert.pct);
  return alert.direction === 'loss' ? `7 天内体重下降 ${magnitude}%` : `7 天内体重上升 ${magnitude}%`;
}

export function trendRange(points: { weight_kg: number }[]): { minKg: number; maxKg: number } {
  if (points.length === 0) return { minKg: 0, maxKg: 1 };
  let minKg = points[0].weight_kg;
  let maxKg = points[0].weight_kg;
  for (const point of points) {
    if (point.weight_kg < minKg) minKg = point.weight_kg;
    if (point.weight_kg > maxKg) maxKg = point.weight_kg;
  }
  if (minKg === maxKg) return { minKg: minKg - 0.5, maxKg: maxKg + 0.5 };
  return { minKg, maxKg };
}

export function weightTimeline(petId: number, items: WeightRecord[]) {
  return items.map(item => ({
    kind: 'weight' as const,
    id: item.id,
    createdAt: item.measured_at,
    title: `体重 ${item.weight_kg} kg`,
    route: `/weight/${petId}`,
  }));
}

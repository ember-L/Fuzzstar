// 饮食记录纯逻辑（F07）：克数校验、时间回改档位、本地自然日与时间线映射。
// 自包含（不跨 lib 值导入），Node 可直接测试。

export const FOOD_LABELS: Record<string, string> = { dry: '干粮', wet: '湿粮', snack: '零食', other: '其他' };

export interface DietRecord {
  id: number;
  food_type: string;
  food_name: string | null;
  amount_g: number;
  kcal_est: number | null;
  fed_at: string;
  note: string | null;
}

export type AmountResult = { ok: true; value: number } | { ok: false; message: string };

export function parseAmount(text: string): AmountResult {
  const trimmed = text.trim();
  if (!trimmed) return { ok: false, message: '请输入克数' };
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return { ok: false, message: '克数需为数字' };
  if (value <= 0) return { ok: false, message: '克数需大于 0' };
  if (value > 2000) return { ok: false, message: '单次克数不超过 2000' };
  return { ok: true, value: Math.round(value * 10) / 10 };
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

export function fedAtFor(hours: number, now: Date = new Date()): string {
  return new Date(now.getTime() - hours * 3600000).toISOString();
}

export function tzOffsetMinutes(now: Date = new Date()): number {
  return -now.getTimezoneOffset();
}

export function localDate(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

export function shiftDay(day: string, delta: number): string {
  const [year, month, date] = day.split('-').map(Number);
  const shifted = new Date(year, month - 1, date + delta, 12, 0, 0);
  return localDate(shifted);
}

function parseFedAt(iso: string): Date {
  const value = /Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`;
  return new Date(value);
}

export function dietTimeline(petId: number, items: DietRecord[]) {
  return items.map(item => {
    const fed = parseFedAt(item.fed_at);
    const kcal = item.kcal_est === null ? '' : ` · ${item.kcal_est} kcal`;
    return {
      kind: 'diet' as const,
      id: item.id,
      createdAt: item.fed_at,
      title: `${FOOD_LABELS[item.food_type] ?? item.food_type} ${item.amount_g}g${kcal}`,
      route: `/diet/${petId}?date=${localDate(fed)}`,
    };
  });
}

// 健康时间线（F06-1）：初筛／饮食／体重按本地自然日分组、时间倒序混排。
// T11 仅初筛记录；diet/weight 槽位待 T12/T13 交付后由各自页面构造插入。

export interface ScreeningHistoryItem {
  screening_id: number;
  state: string;
  redline_hit: boolean;
  created_at: string;
}

export type TimelineItem =
  | { kind: 'screening'; id: number; createdAt: string; state: string; redlineHit: boolean; route: string }
  | { kind: 'diet'; id: number; createdAt: string; title: string; route: string }
  | { kind: 'weight'; id: number; createdAt: string; title: string; route: string };

export interface DayGroup {
  day: string;
  label: string;
  items: TimelineItem[];
}

export function parseTimestamp(iso: string): number {
  const value = /Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`;
  return Date.parse(value);
}

export function screeningTimeline(items: ScreeningHistoryItem[]): TimelineItem[] {
  return items.map(item => ({
    kind: 'screening' as const,
    id: item.screening_id,
    createdAt: item.created_at,
    state: item.state,
    redlineHit: item.redline_hit,
    route: `/screening/result/${item.screening_id}`,
  }));
}

export function mergeTimeline(...groups: TimelineItem[][]): TimelineItem[] {
  return groups.flat().sort((a, b) => parseTimestamp(b.createdAt) - parseTimestamp(a.createdAt));
}

function localDayKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function dayLabel(date: Date, now: Date): string {
  const startOf = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const diffDays = Math.round((startOf(now) - startOf(date)) / 86400000);
  if (diffDays === 0) return '今天';
  if (diffDays === 1) return '昨天';
  const monthDay = `${date.getMonth() + 1}月${date.getDate()}日`;
  return date.getFullYear() === now.getFullYear() ? monthDay : `${date.getFullYear()}年${monthDay}`;
}

export function groupByLocalDay(items: TimelineItem[], now: Date): DayGroup[] {
  const sorted = mergeTimeline(items);
  const groups: DayGroup[] = [];
  for (const item of sorted) {
    const date = new Date(parseTimestamp(item.createdAt));
    const day = localDayKey(date);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.items.push(item);
    else groups.push({ day, label: dayLabel(date, now), items: [item] });
  }
  return groups;
}

export function formatClock(iso: string): string {
  const date = new Date(parseTimestamp(iso));
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

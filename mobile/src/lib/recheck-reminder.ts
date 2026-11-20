// 复查提醒（F06-2 / F10-1）：observe 结果 +24h 本地通知；复查完成或删猫时按猫取消。
// 纯逻辑层，调度/取消由 lib/notifications.ts 适配层执行（expo-notifications）。

export const RECHECK_DELAY_MS = 24 * 60 * 60 * 1000;

export interface RecheckReminder {
  identifier: string;
  fireAt: number;
  title: string;
  body: string;
  data: { petId: number; route: string };
}

export interface RecheckRecord {
  screening_id: number;
  pet_id: number;
  state: string;
  created_at: string;
}

function parseTimestamp(iso: string): number {
  const value = /Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`;
  return Date.parse(value);
}

export function recheckPrefix(petId: number): string {
  return `recheck-${petId}-`;
}

export function isRecheckIdentifier(identifier: string, petId?: number): boolean {
  if (petId !== undefined) return identifier.startsWith(recheckPrefix(petId));
  return /^recheck-\d+-\d+$/.test(identifier);
}

export function buildRecheckReminder(record: RecheckRecord, petName: string): RecheckReminder | null {
  if (record.state !== 'observe') return null;
  return {
    identifier: `${recheckPrefix(record.pet_id)}${record.screening_id}`,
    fireAt: parseTimestamp(record.created_at) + RECHECK_DELAY_MS,
    title: '复查提醒',
    body: `${petName} 的观察期已满 24 小时，建议复查一次初筛。如已好转可忽略，如加重请及时就医。`,
    data: { petId: record.pet_id, route: `/screening/${record.pet_id}` },
  };
}

export function routeFromNotificationData(data: Record<string, unknown> | null | undefined): string | null {
  const route = data?.route;
  return typeof route === 'string' && route.startsWith('/') ? route : null;
}

export function shouldSchedule(reminder: RecheckReminder | null, now: number): reminder is RecheckReminder {
  return reminder !== null && reminder.fireAt > now;
}

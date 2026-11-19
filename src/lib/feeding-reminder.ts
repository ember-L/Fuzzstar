// 喂养提醒（FRD F10-2）：每宠每日固定时间、默认关闭、可多时段、本地持久化。
// 纯逻辑层；DAILY 触发调度在 lib/notifications.ts（expo-notifications，沿用 T11 适配层）。

export const MAX_FEEDING_TIMES = 6;

export interface FeedingSettings {
  enabled: boolean;
  times: string[];
}

export const DEFAULT_FEEDING_SETTINGS: FeedingSettings = { enabled: false, times: [] };

export interface DailyReminder {
  identifier: string;
  hour: number;
  minute: number;
  title: string;
  body: string;
  data: { petId: number; route: string };
}

export function isValidTime(text: string): boolean {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(text);
}

export function normalizeSettings(input: { enabled: boolean; times: string[] }): FeedingSettings {
  const times = [...new Set(input.times.filter(isValidTime))].sort().slice(0, MAX_FEEDING_TIMES);
  return { enabled: input.enabled && times.length > 0, times };
}

export function feedingPrefix(petId: number): string {
  return `feeding-${petId}-`;
}

export function feedingIdentifier(petId: number, time: string): string {
  return `${feedingPrefix(petId)}${time.replace(':', '')}`;
}

export function isFeedingIdentifier(identifier: string, petId?: number): boolean {
  if (petId !== undefined) return identifier.startsWith(feedingPrefix(petId));
  return /^feeding-\d+-\d{4}$/.test(identifier);
}

export function buildFeedingReminders(settings: FeedingSettings, petId: number, petName: string): DailyReminder[] {
  if (!settings.enabled) return [];
  return settings.times.map(time => {
    const [hour, minute] = time.split(':').map(Number);
    return { identifier: feedingIdentifier(petId, time), hour, minute,
             title: '喂养提醒', body: `${petName} 到饭点啦，记得喂饭并顺手记一笔。`,
             data: { petId, route: `/diet/${petId}` } };
  });
}

export function parseSettings(json: string | null): FeedingSettings {
  if (!json) return { ...DEFAULT_FEEDING_SETTINGS, times: [] };
  try {
    const raw = JSON.parse(json) as { enabled?: unknown; times?: unknown };
    if (typeof raw.enabled !== 'boolean' || !Array.isArray(raw.times) || !raw.times.every(t => typeof t === 'string')) {
      return { ...DEFAULT_FEEDING_SETTINGS, times: [] };
    }
    return normalizeSettings({ enabled: raw.enabled, times: raw.times as string[] });
  } catch {
    return { ...DEFAULT_FEEDING_SETTINGS, times: [] };
  }
}

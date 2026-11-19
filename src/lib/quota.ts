export interface QuotaMetric { used: number; limit: number }
export interface QuotaSnapshot { day: string; metrics: Record<string, QuotaMetric> }
export interface QuotaEntry { metric: string; label: string; used: number; limit: number; exhausted: boolean }

export const QUOTA_LABELS: Record<string, string> = {
  screening: '健康初筛', avatar_gen: '分身生成', chat_msg: '聊天消息',
};
export const QUOTA_EXHAUSTED_HINT = '今日次数已用完，明日再试';
const METRIC_ORDER = ['screening', 'avatar_gen', 'chat_msg'];

export function quotaEntries(snapshot: QuotaSnapshot | null | undefined): QuotaEntry[] {
  if (!snapshot?.metrics) return [];
  const entries: QuotaEntry[] = [];
  for (const metric of METRIC_ORDER) {
    const value = snapshot.metrics[metric];
    if (!value) continue;
    entries.push({ metric, label: QUOTA_LABELS[metric] ?? metric, used: value.used, limit: value.limit,
      exhausted: value.used >= value.limit });
  }
  return entries;
}

// 无快照时放行（服务端仍是最终闸门），避免加载态误锁入口。
export function canUse(snapshot: QuotaSnapshot | null | undefined, metric: string): boolean {
  const value = snapshot?.metrics?.[metric];
  if (!value) return true;
  return value.used < value.limit;
}

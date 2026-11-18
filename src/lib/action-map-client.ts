// 动作映射客户端（F04-4）：版本比对更新，免发版生效；断网回退本地缓存。
import { isActionMap, mapChanged, type ActionMap } from './action-map.ts';

export interface MetaKV {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
}

export const ACTION_MAP_KEY = 'action_map';

export async function loadActionMap(
  fetchMap: (signal?: AbortSignal) => Promise<unknown>,
  kv: MetaKV,
  signal?: AbortSignal,
): Promise<ActionMap | null> {
  let cached: ActionMap | null = null;
  try {
    const raw = await kv.get(ACTION_MAP_KEY);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (isActionMap(parsed)) cached = parsed;
    }
  } catch { /* 缓存损坏按无缓存处理 */ }
  try {
    const fetched = await fetchMap(signal);
    if (isActionMap(fetched)) {
      if (mapChanged(cached, fetched)) await kv.set(ACTION_MAP_KEY, JSON.stringify(fetched));
      return fetched;
    }
  } catch { /* 离线：使用缓存 */ }
  return cached;
}

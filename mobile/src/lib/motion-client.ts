// 萌宠动图客户端（F14-4）：配置版本比对更新，免发版生效；断网回退本地缓存。
import { isMotionConfig, type MotionConfig } from './motion.ts';

export interface MetaKV {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
}

export const MOTION_CONFIG_KEY = 'motion_config';

export async function loadMotionConfig(
  fetchConfig: (signal?: AbortSignal) => Promise<unknown>,
  kv: MetaKV,
  signal?: AbortSignal,
): Promise<MotionConfig | null> {
  let cached: MotionConfig | null = null;
  try {
    const raw = await kv.get(MOTION_CONFIG_KEY);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (isMotionConfig(parsed)) cached = parsed;
    }
  } catch { /* 缓存损坏按无缓存处理 */ }
  try {
    const fetched = await fetchConfig(signal);
    if (isMotionConfig(fetched)) {
      if (!cached || cached.version !== fetched.version) {
        await kv.set(MOTION_CONFIG_KEY, JSON.stringify(fetched));
      }
      return fetched;
    }
  } catch { /* 离线：使用缓存 */ }
  return cached;
}

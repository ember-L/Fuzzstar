// 文件缓存 LRU（ARCH assets.ts / asset_index）。默认上限 200MB；
// 索引与文件 IO 注入，纯淘汰逻辑可测。缓存键用内容版本（version_id），不用会过期的签名 URL。

export const DEFAULT_MAX_BYTES = 200 * 1024 * 1024;

export interface CacheEntry {
  key: string;
  path: string;
  bytes: number;
  lastUsed: number;
}

export interface ResolvedAsset {
  uri: string;
  cached: boolean;
}

export interface CacheIO {
  list(): Promise<CacheEntry[]>;
  touch(key: string, lastUsed: number): Promise<void>;
  insert(entry: CacheEntry): Promise<void>;
  remove(entry: CacheEntry): Promise<void>;
  download(url: string, key: string, signal?: AbortSignal): Promise<{ path: string; bytes: number }>;
}

// 从最旧（lastUsed 最小，同值按 key）开始淘汰，直到 incoming 放得下。
export function planEvictions(entries: CacheEntry[], incomingBytes: number, maxBytes: number): string[] {
  const ordered = [...entries].sort((a, b) => a.lastUsed - b.lastUsed || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  let total = ordered.reduce((sum, e) => sum + e.bytes, 0);
  const evict: string[] = [];
  for (const e of ordered) {
    if (total + incomingBytes <= maxBytes) break;
    evict.push(e.key);
    total -= e.bytes;
  }
  return evict;
}

export function createAssetCache(io: CacheIO, maxBytes: number = DEFAULT_MAX_BYTES) {
  const inflight = new Map<string, Promise<ResolvedAsset | null>>();

  async function resolve(key: string, url: string, opts: { signal?: AbortSignal; now?: number } = {}): Promise<ResolvedAsset | null> {
    const now = opts.now ?? Date.now();
    const entries = await io.list();
    const hit = entries.find(e => e.key === key);
    if (hit) {
      await io.touch(key, now);
      return { uri: hit.path, cached: true };
    }
    let downloaded: { path: string; bytes: number };
    try {
      downloaded = await io.download(url, key, opts.signal);
    } catch {
      return null; // 断网/损坏：调用方沿回退链降级
    }
    if (downloaded.bytes > maxBytes) {
      await io.remove({ key, path: downloaded.path, bytes: downloaded.bytes, lastUsed: now });
      return { uri: url, cached: false };
    }
    for (const evictKey of planEvictions(entries, downloaded.bytes, maxBytes)) {
      const victim = entries.find(e => e.key === evictKey);
      if (victim) await io.remove(victim);
    }
    await io.insert({ key, path: downloaded.path, bytes: downloaded.bytes, lastUsed: now });
    return { uri: downloaded.path, cached: true };
  }

  return {
    resolve(key: string, url: string, opts: { signal?: AbortSignal; now?: number } = {}): Promise<ResolvedAsset | null> {
      const existing = inflight.get(key);
      if (existing) return existing;
      const task = resolve(key, url, opts).finally(() => { inflight.delete(key); });
      inflight.set(key, task);
      return task;
    },
  };
}

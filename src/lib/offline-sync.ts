// 浅离线补发循环（AC-07-5：联网后 ≤10s 同步）：5s 轮询＋ AppState 回前台＋ web online 事件。
// 不引入 netinfo；drain 串行防重叠，幂等键由服务端去重兜底。
import { AppState, Platform } from 'react-native';
import { api } from './api';
import { getOfflineStore } from './offline-store.ts';
import { drainQueue, type DrainResult, type QueueItem } from './retry-queue.ts';

export type SyncListener = (result: DrainResult) => void;

export function createOfflineSync(send: (item: QueueItem) => Promise<unknown>, intervalMs = 5000) {
  const listeners = new Set<SyncListener>();
  let timer: ReturnType<typeof setInterval> | null = null;
  let appStateSub: { remove: () => void } | null = null;
  let webOnline: (() => void) | null = null;
  let draining = false;

  async function drainNow(): Promise<void> {
    if (draining) return;
    draining = true;
    try {
      const store = await getOfflineStore();
      const result = await drainQueue(store.queue, send);
      if (result.synced > 0 || result.dropped.length > 0) {
        for (const listener of listeners) listener(result);
      }
    } catch {
      // 存储/网络异常留待下一轮；队列本身持久化不丢。
    } finally {
      draining = false;
    }
  }

  return {
    drainNow,
    subscribe(listener: SyncListener): () => void {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    start(): void {
      if (timer) return;
      void drainNow();
      timer = setInterval(() => { void drainNow(); }, intervalMs);
      appStateSub = AppState.addEventListener('change', state => { if (state === 'active') void drainNow(); });
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        webOnline = () => { void drainNow(); };
        window.addEventListener('online', webOnline);
      }
    },
    stop(): void {
      if (timer) { clearInterval(timer); timer = null; }
      appStateSub?.remove();
      appStateSub = null;
      if (webOnline && typeof window !== 'undefined') window.removeEventListener('online', webOnline);
      webOnline = null;
    },
  };
}

export const offlineSync = createOfflineSync(item => api.authorized(item.path, {
  method: item.method,
  headers: { 'Content-Type': 'application/json', 'Idempotency-Key': item.idempotencyKey },
  body: item.body,
}));

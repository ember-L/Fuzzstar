// 浅离线持久重试队列（FRD F07-5 / F09-6，ARCH retry_queue）。
// 纯逻辑层：存储适配在 lib/offline-store.ts（原生 SQLite / web 内存）。
// 音频永不入队：kind 白名单 diet / chat_text；重发携带同一 Idempotency-Key 防重复。

export type QueueKind = 'diet' | 'chat_text';

export interface QueueItem {
  id: number;
  kind: QueueKind;
  petId: number;
  method: string;
  path: string;
  body: string;
  idempotencyKey: string;
  attempts: number;
  createdAt: number;
  lastError: string | null;
}

export interface QueueStore {
  list(): Promise<QueueItem[]>;
  insert(item: Omit<QueueItem, 'id'>): Promise<number>;
  remove(id: number): Promise<void>;
  bump(id: number, attempts: number, error: string): Promise<void>;
}

export interface DrainResult {
  synced: number;
  dropped: { item: QueueItem; error: string }[];
  remaining: number;
  stopped: boolean;
}

export function generateKey(rand: () => number = Math.random): string {
  let key = '';
  for (let i = 0; i < 32; i += 1) key += Math.floor(rand() * 16).toString(16);
  return key;
}

// 网络错误/5xx/408/429 保留重试；其余 4xx（校验/归属/冲突）出队提示，避免坏请求无限重试。
export function classifyFailure(error: unknown): 'retry' | 'drop' {
  const status = (error as { status?: unknown } | null)?.status;
  if (typeof status !== 'number') return 'retry';
  if (status >= 500 || status === 408 || status === 429) return 'retry';
  return 'drop';
}

export function dietQueueItem(petId: number, body: object, idempotencyKey: string, createdAt: number): Omit<QueueItem, 'id'> {
  return { kind: 'diet', petId, method: 'POST', path: `/pets/${petId}/diet`,
           body: JSON.stringify(body), idempotencyKey, attempts: 0, createdAt, lastError: null };
}

export function parseDietBody(item: QueueItem): { food_type: string; amount_g: number; note: string | null; fed_at: string } {
  const body = JSON.parse(item.body) as { food_type?: string; amount_g?: number; note?: string; fed_at?: string };
  return { food_type: body.food_type ?? 'other', amount_g: body.amount_g ?? 0,
           note: body.note ?? null, fed_at: body.fed_at ?? new Date(item.createdAt).toISOString() };
}

// 按入队顺序补发；遇首个可重试失败即停（网络大概率仍断，保序防抖）。
export async function drainQueue(store: QueueStore, send: (item: QueueItem) => Promise<unknown>): Promise<DrainResult> {
  const items = (await store.list()).sort((a, b) => a.id - b.id);
  let synced = 0;
  let stopped = false;
  const dropped: { item: QueueItem; error: string }[] = [];
  for (const item of items) {
    try {
      await send(item);
      await store.remove(item.id);
      synced += 1;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (classifyFailure(error) === 'retry') {
        await store.bump(item.id, item.attempts + 1, message);
        stopped = true;
        break;
      }
      await store.remove(item.id);
      dropped.push({ item, error: message });
    }
  }
  return { synced, dropped, remaining: (await store.list()).length, stopped };
}

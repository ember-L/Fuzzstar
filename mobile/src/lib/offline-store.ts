// 浅离线持久层适配（FRD F07-5/F09-6/F10-2）：原生 expo-sqlite，web 内存化（同 asset-store 模式）。
// retry_queue 持久化待发送请求；chat_cache 镜像聊天历史（T15 接线）；reminder_settings 存喂养提醒开关与时间。
import { Platform } from 'react-native';
import type { QueueItem, QueueStore } from './retry-queue.ts';
import { mergeMessages, type CachedMessage, type ChatCacheStore } from './chat-cache.ts';
import { DEFAULT_FEEDING_SETTINGS, parseSettings, type FeedingSettings } from './feeding-reminder.ts';

export interface ReminderSettingsStore {
  get(petId: number): Promise<FeedingSettings>;
  set(petId: number, settings: FeedingSettings): Promise<void>;
}

export interface OfflineStore {
  queue: QueueStore;
  chat: ChatCacheStore;
  reminders: ReminderSettingsStore;
}

function memoryStore(): OfflineStore {
  let nextId = 1;
  const rows: QueueItem[] = [];
  const chats = new Map<number, CachedMessage[]>();
  const settings = new Map<number, FeedingSettings>();
  return {
    queue: {
      async list() { return rows.map(r => ({ ...r })); },
      async insert(item) { const id = nextId++; rows.push({ ...item, id }); return id; },
      async remove(id) { const i = rows.findIndex(r => r.id === id); if (i >= 0) rows.splice(i, 1); },
      async bump(id, attempts, error) { const row = rows.find(r => r.id === id); if (row) { row.attempts = attempts; row.lastError = error; } },
    },
    chat: {
      async put(petId, messages) { chats.set(petId, mergeMessages(chats.get(petId) ?? [], messages)); },
      async list(petId, limit = 200) { return (chats.get(petId) ?? []).slice(-limit); },
    },
    reminders: {
      async get(petId) { return settings.get(petId) ?? { ...DEFAULT_FEEDING_SETTINGS, times: [] }; },
      async set(petId, value) { settings.set(petId, value); },
    },
  };
}

let nativePromise: Promise<OfflineStore> | null = null;
let webStore: OfflineStore | null = null;

function nativeStore(): Promise<OfflineStore> {
  nativePromise ??= (async () => {
    const SQLite = await import('expo-sqlite');
    const db = await SQLite.openDatabaseAsync('rongxing-offline.db');
    await db.execAsync(
      'CREATE TABLE IF NOT EXISTS retry_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, pet_id INTEGER NOT NULL, method TEXT NOT NULL, path TEXT NOT NULL, body TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, attempts INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, last_error TEXT);' +
      'CREATE TABLE IF NOT EXISTS chat_cache (pet_id INTEGER NOT NULL, message_id TEXT NOT NULL, role TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL, created_at INTEGER NOT NULL, pending INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (pet_id, message_id));' +
      'CREATE TABLE IF NOT EXISTS reminder_settings (pet_id INTEGER PRIMARY KEY, settings TEXT NOT NULL, updated_at INTEGER NOT NULL);',
    );
    type Row = { id: number; kind: string; pet_id: number; method: string; path: string; body: string; idempotency_key: string; attempts: number; created_at: number; last_error: string | null };
    const toItem = (r: Row): QueueItem => ({ id: r.id, kind: r.kind as QueueItem['kind'], petId: r.pet_id, method: r.method,
      path: r.path, body: r.body, idempotencyKey: r.idempotency_key, attempts: r.attempts, createdAt: r.created_at, lastError: r.last_error });
    return {
      queue: {
        async list() {
          const rows = await db.getAllAsync<Row>('SELECT * FROM retry_queue ORDER BY id');
          return rows.map(toItem);
        },
        async insert(item) {
          const result = await db.runAsync(
            'INSERT INTO retry_queue (kind, pet_id, method, path, body, idempotency_key, attempts, created_at, last_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            item.kind, item.petId, item.method, item.path, item.body, item.idempotencyKey, item.attempts, item.createdAt, item.lastError);
          return result.lastInsertRowId;
        },
        async remove(id) { await db.runAsync('DELETE FROM retry_queue WHERE id = ?', id); },
        async bump(id, attempts, error) { await db.runAsync('UPDATE retry_queue SET attempts = ?, last_error = ? WHERE id = ?', attempts, error, id); },
      },
      chat: {
        async put(petId, messages) {
          const existing = await db.getAllAsync<{ message_id: string; role: string; kind: string; content: string; created_at: number; pending: number }>(
            'SELECT message_id, role, kind, content, created_at, pending FROM chat_cache WHERE pet_id = ?', petId);
          const merged = mergeMessages(existing.map(r => ({ id: r.message_id, role: r.role as CachedMessage['role'], kind: r.kind as CachedMessage['kind'],
            content: r.content, createdAt: r.created_at, pending: r.pending === 1 })), messages);
          await db.withTransactionAsync(async () => {
            await db.runAsync('DELETE FROM chat_cache WHERE pet_id = ?', petId);
            for (const m of merged) {
              await db.runAsync('INSERT INTO chat_cache (pet_id, message_id, role, kind, content, created_at, pending) VALUES (?, ?, ?, ?, ?, ?, ?)',
                petId, m.id, m.role, m.kind, m.content, m.createdAt, m.pending ? 1 : 0);
            }
          });
        },
        async list(petId, limit = 200) {
          const rows = await db.getAllAsync<{ message_id: string; role: string; kind: string; content: string; created_at: number; pending: number }>(
            'SELECT message_id, role, kind, content, created_at, pending FROM chat_cache WHERE pet_id = ? ORDER BY created_at, message_id LIMIT ?', petId, limit);
          return rows.map(r => ({ id: r.message_id, role: r.role as CachedMessage['role'], kind: r.kind as CachedMessage['kind'],
            content: r.content, createdAt: r.created_at, pending: r.pending === 1 }));
        },
      },
      reminders: {
        async get(petId) {
          const row = await db.getFirstAsync<{ settings: string }>('SELECT settings FROM reminder_settings WHERE pet_id = ?', petId);
          return parseSettings(row?.settings ?? null);
        },
        async set(petId, value) {
          await db.runAsync('INSERT OR REPLACE INTO reminder_settings (pet_id, settings, updated_at) VALUES (?, ?, ?)',
            petId, JSON.stringify(value), Date.now());
        },
      },
    };
  })();
  return nativePromise;
}

export function getOfflineStore(): Promise<OfflineStore> {
  if (Platform.OS === 'web') { webStore ??= memoryStore(); return Promise.resolve(webStore); }
  return nativeStore();
}

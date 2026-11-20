// 原生端资产存储适配（ARCH：expo-sqlite 只存索引与元数据，文件本体在文件系统）。
// web 端无文件缓存：索引内存化、下载直通远端 URL（浏览器 HTTP 缓存负责复用）。
import { Platform } from 'react-native';
import type { CacheEntry, CacheIO } from './asset-cache.ts';
import type { MetaKV } from './action-map-client.ts';

export interface AssetStore {
  io: CacheIO;
  kv: MetaKV;
}

function memoryStore(): AssetStore {
  const rows = new Map<string, CacheEntry>();
  const meta = new Map<string, string>();
  return {
    io: {
      async list() { return [...rows.values()]; },
      async touch(key, lastUsed) { const row = rows.get(key); if (row) row.lastUsed = lastUsed; },
      async insert(entry) { rows.set(entry.key, entry); },
      async remove(entry) { rows.delete(entry.key); },
      // web 直通：不落地文件，uri 即远端地址，bytes 记 0 不占 LRU 配额。
      async download(url) { return { path: url, bytes: 0 }; },
    },
    kv: {
      async get(key) { return meta.get(key) ?? null; },
      async set(key, value) { meta.set(key, value); },
    },
  };
}

let nativePromise: Promise<AssetStore> | null = null;

function nativeStore(): Promise<AssetStore> {
  nativePromise ??= (async () => {
    const SQLite = await import('expo-sqlite');
    const FileSystem = await import('expo-file-system/legacy');
    const db = await SQLite.openDatabaseAsync('rongxing-assets.db');
    await db.execAsync(
      'CREATE TABLE IF NOT EXISTS asset_index (key TEXT PRIMARY KEY, path TEXT NOT NULL, bytes INTEGER NOT NULL, last_used INTEGER NOT NULL);' +
      'CREATE TABLE IF NOT EXISTS kv_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);',
    );
    const dir = FileSystem.documentDirectory + 'avatar-cache/';
    await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => { /* 已存在 */ });
    const filePath = (key: string) => dir + key.replace(/[^a-zA-Z0-9._-]/g, '_') + '.mp4';
    return {
      io: {
        async list() {
          const rows = await db.getAllAsync<{ key: string; path: string; bytes: number; last_used: number }>(
            'SELECT key, path, bytes, last_used FROM asset_index',
          );
          return rows.map(r => ({ key: r.key, path: r.path, bytes: r.bytes, lastUsed: r.last_used }));
        },
        async touch(key, lastUsed) {
          await db.runAsync('UPDATE asset_index SET last_used = ? WHERE key = ?', lastUsed, key);
        },
        async insert(entry) {
          await db.runAsync(
            'INSERT OR REPLACE INTO asset_index (key, path, bytes, last_used) VALUES (?, ?, ?, ?)',
            entry.key, entry.path, entry.bytes, entry.lastUsed,
          );
        },
        async remove(entry) {
          await FileSystem.deleteAsync(entry.path, { idempotent: true }).catch(() => { /* 文件已不存在 */ });
          await db.runAsync('DELETE FROM asset_index WHERE key = ?', entry.key);
        },
        async download(url, key) {
          const target = filePath(key);
          const result = await FileSystem.downloadAsync(url, target);
          if (result.status !== 200) {
            await FileSystem.deleteAsync(target, { idempotent: true }).catch(() => {});
            throw new Error(`asset download failed: ${result.status}`);
          }
          const info = await FileSystem.getInfoAsync(target);
          const bytes = info.exists && typeof info.size === 'number' ? info.size : 0;
          return { path: target, bytes };
        },
      },
      kv: {
        async get(key) {
          const row = await db.getFirstAsync<{ value: string }>('SELECT value FROM kv_meta WHERE key = ?', key);
          return row?.value ?? null;
        },
        async set(key, value) {
          await db.runAsync('INSERT OR REPLACE INTO kv_meta (key, value) VALUES (?, ?)', key, value);
        },
      },
    };
  })();
  return nativePromise;
}

let webPromise: Promise<AssetStore> | null = null;

export function getAssetStore(): Promise<AssetStore> {
  if (Platform.OS === 'web') {
    webPromise ??= Promise.resolve(memoryStore());
    return webPromise;
  }
  return nativeStore();
}

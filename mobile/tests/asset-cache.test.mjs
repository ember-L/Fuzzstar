// T07 文件缓存 LRU（ARCH assets.ts，默认 200MB）。注入 IO，Node 可测。
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DEFAULT_MAX_BYTES, planEvictions, createAssetCache } from '../src/lib/asset-cache.ts';

const entry = (key, bytes, lastUsed) => ({ key, path: '/cache/' + key, bytes, lastUsed });

test('默认上限 200MB', () => {
  assert.equal(DEFAULT_MAX_BYTES, 200 * 1024 * 1024);
});

test('planEvictions 按 lastUsed 从旧到新淘汰直到放得下', () => {
  const entries = [entry('a', 40, 1), entry('b', 40, 2), entry('c', 40, 3)];
  assert.deepEqual(planEvictions(entries, 50, 120), ['a', 'b']);
  assert.deepEqual(planEvictions(entries, 10, 120), ['a']);
  assert.deepEqual(planEvictions(entries, 0, 120), []);
});

test('planEvictions 同 lastUsed 按 key 稳定排序；空索引不淘汰', () => {
  const entries = [entry('b', 10, 5), entry('a', 10, 5)];
  assert.deepEqual(planEvictions(entries, 15, 20), ['a', 'b']);
  assert.deepEqual(planEvictions([], 999, 20), []);
});

function fakeIO(options = {}) {
  const rows = new Map();
  const calls = { downloads: [], removed: [], touched: [] };
  let fail = options.fail ?? false;
  return {
    calls, rows, setFail: v => { fail = v; },
    io: {
      async list() { return [...rows.values()]; },
      async touch(key, lastUsed) { calls.touched.push([key, lastUsed]); rows.get(key).lastUsed = lastUsed; },
      async insert(e) { rows.set(e.key, e); },
      async remove(e) { calls.removed.push(e.key); rows.delete(e.key); },
      async download(url, key) {
        calls.downloads.push(url);
        if (fail) throw new Error('offline');
        return { path: '/cache/' + key, bytes: options.bytes ?? 10 };
      },
    },
  };
}

test('miss → 下载入库并返回本地路径', async () => {
  const f = fakeIO();
  const cache = createAssetCache(f.io, 100);
  const r = await cache.resolve('k1', 'https://x/clip.mp4', { now: 50 });
  assert.deepEqual(r, { uri: '/cache/k1', cached: true });
  assert.equal(f.rows.get('k1').bytes, 10);
  assert.equal(f.rows.get('k1').lastUsed, 50);
  assert.deepEqual(f.calls.downloads, ['https://x/clip.mp4']);
});

test('hit → 不下载，touch 更新 lastUsed', async () => {
  const f = fakeIO();
  const cache = createAssetCache(f.io, 100);
  await cache.resolve('k1', 'https://x/1.mp4', { now: 1 });
  const r = await cache.resolve('k1', 'https://x/2.mp4', { now: 9 });
  assert.deepEqual(r, { uri: '/cache/k1', cached: true });
  assert.equal(f.calls.downloads.length, 1);
  assert.deepEqual(f.calls.touched.at(-1), ['k1', 9]);
});

test('超上限先淘汰 LRU 再入库', async () => {
  const f = fakeIO({ bytes: 60 });
  const cache = createAssetCache(f.io, 100);
  await cache.resolve('old', 'https://x/old.mp4', { now: 1 });
  await cache.resolve('new', 'https://x/new.mp4', { now: 2 });
  assert.deepEqual(f.calls.removed, ['old']);
  assert.equal(f.rows.has('new'), true);
  assert.equal(f.rows.has('old'), false);
});

test('下载失败 → null，索引不变（调用方走回退链）', async () => {
  const f = fakeIO();
  f.setFail(true);
  const cache = createAssetCache(f.io, 100);
  assert.equal(await cache.resolve('k', 'https://x/k.mp4'), null);
  assert.equal(f.rows.size, 0);
});

test('单资产超上限 → 不缓存，直接远端播放并清理临时文件', async () => {
  const f = fakeIO({ bytes: 150 });
  const cache = createAssetCache(f.io, 100);
  const r = await cache.resolve('big', 'https://x/big.mp4', { now: 1 });
  assert.deepEqual(r, { uri: 'https://x/big.mp4', cached: false });
  assert.equal(f.rows.size, 0);
  assert.deepEqual(f.calls.removed, ['big']);
});

test('同 key 并发 resolve 只下载一次', async () => {
  const f = fakeIO();
  const cache = createAssetCache(f.io, 100);
  const [a, b] = await Promise.all([
    cache.resolve('k', 'https://x/k.mp4', { now: 1 }),
    cache.resolve('k', 'https://x/k.mp4', { now: 1 }),
  ]);
  assert.deepEqual(a, b);
  assert.equal(f.calls.downloads.length, 1);
});

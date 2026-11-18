// T07 动作映射客户端：版本比对更新（AC-04-4 免发版）、离线回退缓存。
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadActionMap } from '../src/lib/action-map-client.ts';

const MAP = { version: 'am-1', actions: ['idle'], priority: ['health', 'idle'], rules: [] };
const MAP2 = { ...MAP, version: 'am-2' };

function fakeKV(initial = null) {
  const store = new Map(initial ? [['action_map', initial]] : []);
  return {
    store,
    async get(key) { return store.get(key) ?? null; },
    async set(key, value) { store.set(key, value); },
  };
}

test('首次加载写入缓存', async () => {
  const kv = fakeKV();
  const map = await loadActionMap(async () => MAP, kv);
  assert.equal(map.version, 'am-1');
  assert.deepEqual(JSON.parse(kv.store.get('action_map')), MAP);
});

test('版本相同不重写；版本更新覆盖缓存', async () => {
  const kv = fakeKV(JSON.stringify(MAP));
  let writes = 0;
  const wrapped = { get: kv.get, set: async (k, v) => { writes += 1; await kv.set(k, v); } };
  await loadActionMap(async () => MAP, wrapped);
  assert.equal(writes, 0);
  const map = await loadActionMap(async () => MAP2, wrapped);
  assert.equal(map.version, 'am-2');
  assert.equal(writes, 1);
});

test('断网回退缓存；无缓存返回 null', async () => {
  const offline = async () => { throw new Error('network down'); };
  const kv = fakeKV(JSON.stringify(MAP));
  assert.equal((await loadActionMap(offline, kv)).version, 'am-1');
  assert.equal(await loadActionMap(offline, fakeKV()), null);
});

test('非法远端映射忽略，保留缓存', async () => {
  const kv = fakeKV(JSON.stringify(MAP));
  const map = await loadActionMap(async () => ({ version: 3 }), kv);
  assert.equal(map.version, 'am-1');
  assert.deepEqual(JSON.parse(kv.store.get('action_map')), MAP);
});

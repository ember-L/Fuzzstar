import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mergeMessages } from '../src/lib/chat-cache.ts';

function msg(id, overrides = {}) {
  return { id, role: 'user', kind: 'text', content: 'hi', createdAt: 1000, pending: false, ...overrides };
}

test('mergeMessages dedupes by id with incoming winning', () => {
  const merged = mergeMessages([msg('a', { content: 'old' })], [msg('a', { content: 'new' }), msg('b')]);
  assert.equal(merged.length, 2);
  assert.equal(merged.find(m => m.id === 'a').content, 'new');
});

test('mergeMessages clears pending when server confirms', () => {
  const merged = mergeMessages([msg('a', { pending: true })], [msg('a', { pending: false })]);
  assert.equal(merged[0].pending, false);
});

test('mergeMessages keeps local pending message absent from server list', () => {
  const merged = mergeMessages([msg('local', { pending: true, createdAt: 3000 })], [msg('a', { createdAt: 1000 })]);
  assert.equal(merged.length, 2);
  assert.equal(merged[1].id, 'local');
});

test('mergeMessages sorts ascending by createdAt then id', () => {
  const merged = mergeMessages([], [msg('b', { createdAt: 2000 }), msg('a', { createdAt: 1000 }), msg('c', { createdAt: 1000 })]);
  assert.deepEqual(merged.map(m => m.id), ['a', 'c', 'b']);
});

test('mergeMessages handles empty inputs', () => {
  assert.deepEqual(mergeMessages([], []), []);
  assert.equal(mergeMessages([msg('a')], []).length, 1);
});

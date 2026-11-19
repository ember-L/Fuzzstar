import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CHAT_INPUT_MAX, validateChatInput, chatQueueItem, parseChatBody, toCachedMessage, localPendingId, confirmSend } from '../src/lib/chat.ts';

test('validateChatInput trims and rejects empty', () => {
  assert.deepEqual(validateChatInput('  你好呀  '), { ok: true, value: '你好呀' });
  assert.equal(validateChatInput('   ').ok, false);
  assert.equal(validateChatInput('').ok, false);
});

test('validateChatInput enforces 500 char limit', () => {
  assert.equal(CHAT_INPUT_MAX, 500);
  assert.equal(validateChatInput('喵'.repeat(500)).ok, true);
  const tooLong = validateChatInput('喵'.repeat(501));
  assert.equal(tooLong.ok, false);
  assert.match(tooLong.message, /500/);
});

test('chatQueueItem targets session messages with idempotency key', () => {
  const item = chatQueueItem(3, 7, '今天吃饭了吗', 'abc123', 1000);
  assert.equal(item.kind, 'chat_text');
  assert.equal(item.petId, 3);
  assert.equal(item.method, 'POST');
  assert.equal(item.path, '/chat/sessions/7/messages');
  assert.deepEqual(JSON.parse(item.body), { kind: 'text', content: '今天吃饭了吗' });
  assert.equal(item.idempotencyKey, 'abc123');
  assert.equal(item.attempts, 0);
  assert.equal(item.createdAt, 1000);
  assert.equal(item.lastError, null);
});

test('parseChatBody extracts content', () => {
  const item = chatQueueItem(1, 2, '喵', 'k', 0);
  assert.deepEqual(parseChatBody(item), { content: '喵' });
});

test('toCachedMessage maps server payload with naive UTC timestamp', () => {
  const cached = toCachedMessage({ id: 12, role: 'pet', kind: 'text', content: '喵～', emotion_label: 'happy', emotion_confidence: null, task_id: null, created_at: '2026-11-19T10:00:00', source: 'llm' });
  assert.equal(cached.id, '12');
  assert.equal(cached.role, 'pet');
  assert.equal(cached.content, '喵～');
  assert.equal(cached.pending, false);
  assert.equal(cached.createdAt, Date.parse('2026-11-19T10:00:00Z'));
});

test('localPendingId is distinct from server ids', () => {
  assert.equal(localPendingId('key1'), 'local-key1');
});

test('confirmSend replaces pending placeholder with server pair sorted', () => {
  const old = { id: '1', role: 'user', kind: 'text', content: '早', createdAt: 100, pending: false };
  const pending = { id: localPendingId('k'), role: 'user', kind: 'text', content: '在吗', createdAt: 500, pending: true };
  const user = { id: 2, role: 'user', kind: 'text', content: '在吗', emotion_label: null, emotion_confidence: null, task_id: null, created_at: '2026-11-19T10:00:01' };
  const pet = { id: 3, role: 'pet', kind: 'text', content: '喵～', emotion_label: 'happy', emotion_confidence: null, task_id: null, created_at: '2026-11-19T10:00:02', source: 'llm' };
  const merged = confirmSend([old, pending], localPendingId('k'), user, pet);
  assert.deepEqual(merged.map(m => m.id), ['1', '2', '3']);
  assert.ok(merged.every(m => !m.pending));
});

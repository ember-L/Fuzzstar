import assert from 'node:assert/strict';
import test from 'node:test';
import { QUOTA_EXHAUSTED_HINT, QUOTA_LABELS, canUse, quotaEntries } from '../src/lib/quota.ts';

const snapshot = { day: '2026-11-20', metrics: {
  screening: { used: 10, limit: 10 }, avatar_gen: { used: 1, limit: 3 }, chat_msg: { used: 0, limit: 50 },
} };

test('quota entries keep metric order with labels and exhausted flags', () => {
  const entries = quotaEntries(snapshot);
  assert.deepEqual(entries.map(e => e.metric), ['screening', 'avatar_gen', 'chat_msg']);
  assert.deepEqual(entries.map(e => e.label), ['健康初筛', '分身生成', '聊天消息']);
  assert.equal(entries[0].exhausted, true);
  assert.equal(entries[1].exhausted, false);
  assert.equal(entries[1].used, 1);
  assert.equal(entries[1].limit, 3);
});

test('quota entries tolerate missing snapshot', () => {
  assert.deepEqual(quotaEntries(null), []);
  assert.deepEqual(quotaEntries(undefined), []);
});

test('canUse gates at limit and fails open without snapshot', () => {
  assert.equal(canUse(snapshot, 'screening'), false);
  assert.equal(canUse(snapshot, 'avatar_gen'), true);
  assert.equal(canUse(null, 'screening'), true);
  assert.equal(canUse(snapshot, 'unknown'), true);
});

test('exhausted hint matches server copy', () => {
  assert.ok(QUOTA_EXHAUSTED_HINT.includes('明日再试'));
  assert.equal(QUOTA_LABELS.chat_msg, '聊天消息');
});

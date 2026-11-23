import assert from 'node:assert/strict';
import { test } from 'node:test';
import { adviceNotice, shouldPollAdvice } from '../src/lib/screening-advice.ts';

const ready = { status: 'ready', source: 'llm', text: '建议文本', tips: ['t1'] };
const pending = { status: 'pending', source: null, text: null, tips: null };
const degraded = { status: 'degraded', source: 'template', text: '模板文本', tips: ['t'] };

test('pending with task polls', () => {
  assert.equal(shouldPollAdvice({ task_id: 'a'.repeat(32), advice: pending }), true);
});

test('pending without task does not poll', () => {
  assert.equal(shouldPollAdvice({ task_id: null, advice: pending }), false);
});

test('ready and degraded do not poll', () => {
  assert.equal(shouldPollAdvice({ task_id: 'a'.repeat(32), advice: ready }), false);
  assert.equal(shouldPollAdvice({ task_id: 'a'.repeat(32), advice: degraded }), false);
});

test('notice texts', () => {
  assert.equal(adviceNotice(pending), 'AI 建议生成中…');
  assert.equal(adviceNotice(degraded), 'AI 建议暂不可用，已按状态给出通用建议');
  assert.equal(adviceNotice(ready), null);
});

test('missing advice is treated as not pollable with no notice', () => {
  assert.equal(shouldPollAdvice({ task_id: null, advice: null }), false);
  assert.equal(adviceNotice(null), null);
});

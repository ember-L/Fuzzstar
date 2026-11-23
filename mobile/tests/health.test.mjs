import assert from 'node:assert/strict';
import { test } from 'node:test';
import { stateLabel, scoreDisplay, totalEffective, formatDateTime, isUrgent } from '../src/lib/health.ts';

test('state labels follow FRD tiers', () => {
  assert.equal(stateLabel('normal'), '正常');
  assert.equal(stateLabel('observe'), '观察中');
  assert.equal(stateLabel('vet'), '建议就医');
  assert.equal(stateLabel('urgent'), '紧急就医');
});

test('null score shows not-assessed placeholder, never default 100', () => {
  assert.equal(scoreDisplay(null), '未评估  --');
  assert.equal(scoreDisplay(90), '90');
  assert.equal(scoreDisplay(0), '0');
});

test('totalEffective sums effective deltas only', () => {
  const deductions = [
    { effective_delta: 10, decayed: false },
    { effective_delta: 0, decayed: true },
    { effective_delta: 30, decayed: false },
  ];
  assert.equal(totalEffective(deductions), 40);
  assert.equal(totalEffective([]), 0);
});

test('formatDateTime renders month-day hour-minute', () => {
  assert.equal(formatDateTime('2026-11-19T12:34:56'), '11-19 12:34');
});

test('isUrgent only for urgent state', () => {
  assert.equal(isUrgent('urgent'), true);
  assert.equal(isUrgent('vet'), false);
  assert.equal(isUrgent('normal'), false);
});

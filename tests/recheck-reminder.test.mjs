import assert from 'node:assert/strict';
import { test } from 'node:test';
import { RECHECK_DELAY_MS, buildRecheckReminder, recheckPrefix, isRecheckIdentifier, shouldSchedule, routeFromNotificationData } from '../src/lib/recheck-reminder.ts';

const RECORD = { screening_id: 12, pet_id: 3, state: 'observe', created_at: '2026-11-19T01:00:00' };

test('observe builds a +24h reminder named after the pet linking to its screening entry', () => {
  const reminder = buildRecheckReminder(RECORD, '团团');
  assert.ok(reminder);
  assert.equal(reminder.identifier, 'recheck-3-12');
  assert.equal(reminder.fireAt, Date.parse('2026-11-19T01:00:00Z') + RECHECK_DELAY_MS);
  assert.equal(RECHECK_DELAY_MS, 24 * 60 * 60 * 1000);
  assert.ok(reminder.body.includes('团团'));
  assert.deepEqual(reminder.data, { petId: 3, route: '/screening/3' });
});

test('normal, vet and urgent never register an observation reminder', () => {
  for (const state of ['normal', 'vet', 'urgent']) {
    assert.equal(buildRecheckReminder({ ...RECORD, state }, '团团'), null);
  }
});

test('naive timestamps are treated as UTC and explicit offsets respected', () => {
  const naive = buildRecheckReminder(RECORD, '团团');
  const zulu = buildRecheckReminder({ ...RECORD, created_at: '2026-11-19T01:00:00Z' }, '团团');
  const offset = buildRecheckReminder({ ...RECORD, created_at: '2026-11-19T09:00:00+08:00' }, '团团');
  assert.equal(naive.fireAt, zulu.fireAt);
  assert.equal(offset.fireAt, zulu.fireAt);
});

test('identifiers are scoped per pet for bulk cancellation', () => {
  assert.equal(recheckPrefix(3), 'recheck-3-');
  assert.equal(isRecheckIdentifier('recheck-3-12', 3), true);
  assert.equal(isRecheckIdentifier('recheck-3-12', 4), false);
  assert.equal(isRecheckIdentifier('recheck-30-12', 3), false);
  assert.equal(isRecheckIdentifier('feeding-3', 3), false);
  assert.equal(isRecheckIdentifier('recheck-3-12'), true);
  assert.equal(isRecheckIdentifier('other'), false);
});

test('notification tap routes only to internal paths', () => {
  assert.equal(routeFromNotificationData({ petId: 3, route: '/screening/3' }), '/screening/3');
  assert.equal(routeFromNotificationData({ route: 'https://evil.example' }), null);
  assert.equal(routeFromNotificationData({ route: 42 }), null);
  assert.equal(routeFromNotificationData(null), null);
  assert.equal(routeFromNotificationData(undefined), null);
});

test('expired reminders are not scheduled', () => {
  const reminder = buildRecheckReminder(RECORD, '团团');
  assert.equal(shouldSchedule(reminder, reminder.fireAt - 1), true);
  assert.equal(shouldSchedule(reminder, reminder.fireAt), false);
  assert.equal(shouldSchedule(reminder, reminder.fireAt + 1), false);
  assert.equal(shouldSchedule(null, 0), false);
});

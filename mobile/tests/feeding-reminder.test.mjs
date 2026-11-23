import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DEFAULT_FEEDING_SETTINGS, MAX_FEEDING_TIMES, buildFeedingReminders, feedingIdentifier,
         isFeedingIdentifier, isValidTime, normalizeSettings, parseSettings } from '../src/lib/feeding-reminder.ts';

test('isValidTime accepts 24h HH:MM only', () => {
  assert.ok(isValidTime('08:00'));
  assert.ok(isValidTime('23:59'));
  assert.ok(isValidTime('00:00'));
  assert.ok(!isValidTime('24:00'));
  assert.ok(!isValidTime('8:00'));
  assert.ok(!isValidTime('08:60'));
  assert.ok(!isValidTime('0800'));
  assert.ok(!isValidTime(''));
});

test('default settings are off with no times (F10-2)', () => {
  assert.deepEqual(DEFAULT_FEEDING_SETTINGS, { enabled: false, times: [] });
});

test('normalizeSettings filters invalid, dedupes, sorts and caps', () => {
  const normalized = normalizeSettings({ enabled: true, times: ['18:00', '08:00', '08:00', '25:00', '12:30', '06:00', '07:00', '09:00', '10:00'] });
  assert.equal(normalized.times.length, MAX_FEEDING_TIMES);
  assert.deepEqual(normalized.times, ['06:00', '07:00', '08:00', '09:00', '10:00', '12:30']);
  assert.equal(normalized.enabled, true);
});

test('normalizeSettings requires at least one time to stay enabled', () => {
  assert.equal(normalizeSettings({ enabled: true, times: [] }).enabled, false);
  assert.equal(normalizeSettings({ enabled: true, times: ['bad'] }).enabled, false);
});

test('feedingIdentifier and isFeedingIdentifier scope per pet', () => {
  const id = feedingIdentifier(3, '08:00');
  assert.equal(id, 'feeding-3-0800');
  assert.ok(isFeedingIdentifier(id));
  assert.ok(isFeedingIdentifier(id, 3));
  assert.ok(!isFeedingIdentifier(id, 4));
  assert.ok(!isFeedingIdentifier('recheck-3-9'));
});

test('buildFeedingReminders returns nothing when disabled', () => {
  assert.deepEqual(buildFeedingReminders({ enabled: false, times: ['08:00'] }, 3, '团团'), []);
});

test('buildFeedingReminders maps each time to a daily reminder', () => {
  const reminders = buildFeedingReminders({ enabled: true, times: ['08:00', '18:30'] }, 3, '团团');
  assert.equal(reminders.length, 2);
  assert.equal(reminders[0].identifier, 'feeding-3-0800');
  assert.equal(reminders[0].hour, 8);
  assert.equal(reminders[0].minute, 0);
  assert.equal(reminders[1].hour, 18);
  assert.equal(reminders[1].minute, 30);
  assert.ok(reminders[0].body.includes('团团'));
  assert.equal(reminders[0].data.route, '/diet/3');
  assert.equal(reminders[0].data.petId, 3);
});

test('parseSettings falls back to default on missing or corrupt storage', () => {
  assert.deepEqual(parseSettings(null), DEFAULT_FEEDING_SETTINGS);
  assert.deepEqual(parseSettings('not json'), DEFAULT_FEEDING_SETTINGS);
  assert.deepEqual(parseSettings('{"enabled":"yes"}'), DEFAULT_FEEDING_SETTINGS);
});

test('parseSettings roundtrips normalized settings', () => {
  const settings = normalizeSettings({ enabled: true, times: ['18:00', '08:00'] });
  assert.deepEqual(parseSettings(JSON.stringify(settings)), settings);
});

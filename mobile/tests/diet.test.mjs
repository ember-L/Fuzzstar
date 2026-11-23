import test from 'node:test';
import assert from 'node:assert/strict';
import { parseAmount, BACKDATE_OPTIONS, fedAtFor, dietTimeline, localDate, tzOffsetMinutes, shiftDay, FOOD_LABELS } from '../src/lib/diet.ts';

test('parseAmount accepts positive grams up to 2000 with one decimal', () => {
  assert.deepEqual(parseAmount('50'), { ok: true, value: 50 });
  assert.deepEqual(parseAmount('33.33'), { ok: true, value: 33.3 });
  assert.deepEqual(parseAmount(' 2000 '), { ok: true, value: 2000 });
});

test('parseAmount blocks zero negative overflow and non-numbers', () => {
  for (const text of ['0', '-5', '2001', 'abc', '']) {
    const result = parseAmount(text);
    assert.equal(result.ok, false, text);
    assert.ok(result.message);
  }
});

test('backdate options stay within seven days', () => {
  assert.ok(BACKDATE_OPTIONS.length >= 4);
  assert.equal(BACKDATE_OPTIONS[0].hours, 0);
  for (const option of BACKDATE_OPTIONS) {
    assert.ok(option.hours >= 0 && option.hours <= 72);
    assert.ok(option.label);
  }
  const now = new Date('2026-11-19T12:00:00Z');
  assert.equal(fedAtFor(24, now), '2026-11-18T12:00:00.000Z');
  assert.equal(fedAtFor(0, now), now.toISOString());
});

test('dietTimeline maps records to local-day diet routes', () => {
  const items = [
    { id: 1, food_type: 'dry', food_name: null, amount_g: 50, kcal_est: 190, fed_at: '2026-11-18T16:30:00', note: null },
    { id: 2, food_type: 'snack', food_name: null, amount_g: 20, kcal_est: null, fed_at: '2026-11-19T02:00:00', note: null },
  ];
  const mapped = dietTimeline(7, items);
  assert.equal(mapped[0].kind, 'diet');
  assert.equal(mapped[0].title, '干粮 50g · 190 kcal');
  assert.equal(mapped[1].title, '零食 20g');
  for (let i = 0; i < items.length; i += 1) {
    const parsed = new Date(items[i].fed_at + 'Z');
    const expected = localDate(parsed);
    assert.equal(mapped[i].route, `/diet/7?date=${expected}`);
    assert.equal(mapped[i].createdAt, items[i].fed_at);
  }
});

test('localDate and tzOffsetMinutes follow the runtime zone', () => {
  const now = new Date();
  assert.match(localDate(now), /^\d{4}-\d{2}-\d{2}$/);
  assert.equal(tzOffsetMinutes(now), -now.getTimezoneOffset());
});

test('shiftDay crosses month boundaries', () => {
  assert.equal(shiftDay('2026-11-19', -1), '2026-11-18');
  assert.equal(shiftDay('2026-11-01', -1), '2026-10-31');
  assert.equal(shiftDay('2026-12-31', 1), '2027-01-01');
});

test('food labels cover all four types', () => {
  assert.deepEqual(Object.keys(FOOD_LABELS).sort(), ['dry', 'other', 'snack', 'wet']);
});

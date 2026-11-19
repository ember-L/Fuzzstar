import test from 'node:test';
import assert from 'node:assert/strict';
import { parseWeight, BACKDATE_OPTIONS, measuredAtFor, weightTimeline, alertText, trendRange, SCREENING_SUGGESTION } from '../src/lib/weight.ts';

test('parseWeight accepts 0.1 to 30 with two decimals', () => {
  assert.deepEqual(parseWeight('4.25'), { ok: true, value: 4.25 });
  assert.deepEqual(parseWeight('0.1'), { ok: true, value: 0.1 });
  assert.deepEqual(parseWeight('30'), { ok: true, value: 30 });
  assert.deepEqual(parseWeight(' 4.2 '), { ok: true, value: 4.2 });
});

test('parseWeight blocks out of range non numbers and extra precision', () => {
  for (const text of ['0', '0.09', '30.01', '-1', 'abc', '', '4.255']) {
    const result = parseWeight(text);
    assert.equal(result.ok, false, text);
    assert.ok(result.message);
  }
});

test('backdate options stay within seventy two hours', () => {
  assert.ok(BACKDATE_OPTIONS.length >= 4);
  assert.equal(BACKDATE_OPTIONS[0].hours, 0);
  for (const option of BACKDATE_OPTIONS) {
    assert.ok(option.hours >= 0 && option.hours <= 72);
    assert.ok(option.label);
  }
});

test('measuredAtFor subtracts hours from now', () => {
  const now = new Date('2026-11-19T08:00:00Z');
  assert.equal(measuredAtFor(0, now), '2026-11-19T08:00:00.000Z');
  assert.equal(measuredAtFor(24, now), '2026-11-18T08:00:00.000Z');
});

test('weightTimeline maps records to weight slots', () => {
  const items = weightTimeline(7, [{ id: 3, weight_kg: 4.25, measured_at: '2026-11-19T02:00:00' }]);
  assert.deepEqual(items, [{ kind: 'weight', id: 3, createdAt: '2026-11-19T02:00:00', title: '体重 4.25 kg', route: '/weight/7' }]);
});

test('alertText describes loss and gain within seven days', () => {
  const base = { baseline: { weight_kg: 4, measured_at: 'x' }, latest: { weight_kg: 3.5, measured_at: 'y' }, suggestion: 'screening' };
  assert.equal(alertText({ ...base, direction: 'loss', pct: -12.5 }), '7 天内体重下降 12.5%');
  assert.equal(alertText({ ...base, direction: 'gain', pct: 10 }), '7 天内体重上升 10%');
  assert.equal(alertText(null), '');
  assert.equal(SCREENING_SUGGESTION, '建议做一次健康初筛');
});

test('trendRange returns padded bounds', () => {
  assert.deepEqual(trendRange([{ weight_kg: 4 }, { weight_kg: 4.5 }]), { minKg: 4, maxKg: 4.5 });
  const flat = trendRange([{ weight_kg: 4 }]);
  assert.ok(flat.minKg < 4 && flat.maxKg > 4);
  assert.deepEqual(trendRange([]), { minKg: 0, maxKg: 1 });
});

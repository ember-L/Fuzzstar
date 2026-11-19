import assert from 'node:assert/strict';
import { test } from 'node:test';
import { screeningTimeline, mergeTimeline, groupByLocalDay, formatClock } from '../src/lib/timeline.ts';

const NOW = new Date(2026, 10, 19, 13, 0, 0);
const iso = (y, mo, d, h, mi) => new Date(y, mo - 1, d, h, mi).toISOString();

test('screeningTimeline maps history items with state and result route', () => {
  const items = screeningTimeline([
    { screening_id: 7, state: 'observe', redline_hit: false, created_at: iso(2026, 11, 19, 9, 5) },
  ]);
  assert.equal(items.length, 1);
  assert.deepEqual(items[0], {
    kind: 'screening', id: 7, createdAt: iso(2026, 11, 19, 9, 5),
    state: 'observe', redlineHit: false, route: '/screening/result/7',
  });
});

test('mergeTimeline sorts mixed record kinds newest first across days', () => {
  const screening = screeningTimeline([
    { screening_id: 1, state: 'normal', redline_hit: false, created_at: iso(2026, 11, 18, 20, 0) },
    { screening_id: 2, state: 'observe', redline_hit: false, created_at: iso(2026, 11, 19, 8, 0) },
  ]);
  const diet = [{ kind: 'diet', id: 9, createdAt: iso(2026, 11, 19, 12, 30), title: '干粮 50g', route: '/diet/9' }];
  const weight = [{ kind: 'weight', id: 4, createdAt: iso(2026, 11, 17, 7, 45), title: '4.20 kg', route: '/weight/4' }];
  const merged = mergeTimeline(screening, diet, weight);
  assert.deepEqual(merged.map(item => [item.kind, item.id]), [
    ['diet', 9], ['screening', 2], ['screening', 1], ['weight', 4],
  ]);
});

test('groupByLocalDay groups by local calendar day, days and items descending', () => {
  const items = mergeTimeline(
    screeningTimeline([
      { screening_id: 1, state: 'normal', redline_hit: false, created_at: iso(2026, 11, 18, 20, 0) },
      { screening_id: 2, state: 'observe', redline_hit: false, created_at: iso(2026, 11, 19, 8, 0) },
      { screening_id: 3, state: 'vet', redline_hit: false, created_at: iso(2026, 11, 19, 12, 0) },
    ]),
  );
  const groups = groupByLocalDay(items, NOW);
  assert.deepEqual(groups.map(group => group.day), ['2026-11-19', '2026-11-18']);
  assert.deepEqual(groups[0].items.map(item => item.id), [3, 2]);
  assert.deepEqual(groups[1].items.map(item => item.id), [1]);
});

test('day labels use 今天/昨天 and month-day, crossing year keeps year', () => {
  const items = mergeTimeline(screeningTimeline([
    { screening_id: 1, state: 'normal', redline_hit: false, created_at: iso(2026, 11, 19, 8, 0) },
    { screening_id: 2, state: 'normal', redline_hit: false, created_at: iso(2026, 11, 18, 8, 0) },
    { screening_id: 3, state: 'normal', redline_hit: false, created_at: iso(2026, 11, 16, 8, 0) },
    { screening_id: 4, state: 'normal', redline_hit: false, created_at: iso(2025, 12, 31, 8, 0) },
  ]));
  const groups = groupByLocalDay(items, NOW);
  assert.deepEqual(groups.map(group => group.label), ['今天', '昨天', '11月16日', '2025年12月31日']);
});

test('empty input yields no groups and formatClock pads local time', () => {
  assert.deepEqual(groupByLocalDay([], NOW), []);
  assert.deepEqual(mergeTimeline(), []);
  assert.equal(formatClock(iso(2026, 11, 19, 9, 5)), '09:05');
});

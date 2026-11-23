// T07 动作选择引擎（FRD 附录 C / F04-4）。纯函数，Node 可测。
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { decideAction, isActionMap, mapChanged } from '../src/lib/action-map.ts';

const MAP = {
  version: 'am-2026-11-18',
  actions: ['idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right'],
  priority: ['health', 'chat_emotion', 'interaction', 'idle'],
  rules: [
    { source: 'health', condition: { state: 'normal', events: 'none' }, action: 'idle' },
    { source: 'health', condition: { state: ['observe', 'vet'] }, action: 'sick' },
    { source: 'health', condition: { state: 'urgent' }, action: 'sick' },
    { source: 'chat_emotion', condition: { emotion: 'happy' }, action: 'happy' },
    { source: 'chat_emotion', condition: { emotion: 'relaxed' }, action: 'idle' },
    { source: 'chat_emotion', condition: { emotion: 'annoyed' }, action: 'crouch' },
    { source: 'chat_emotion', condition: { emotion: 'fearful' }, action: 'sad' },
    { source: 'chat_emotion', condition: { emotion: 'painful' }, action: 'sick' },
    { source: 'chat_emotion', condition: { emotion: 'seeking_attention' }, action: ['look_left', 'look_right'] },
    { source: 'interaction', condition: { gesture: 'tap' }, action: ['look_left', 'look_right'] },
    { source: 'interaction', condition: { gesture: 'long_press' }, action: 'happy' },
  ],
};

test('健康 normal 无事件 → idle 待机', () => {
  const d = decideAction(MAP, { health: { state: 'normal' } }, {});
  assert.deepEqual(d, { action: 'idle', source: 'health', oneShot: false, alternate: false });
});

test('observe/vet/urgent → sick（AC-04-4 状态联动）', () => {
  for (const state of ['observe', 'vet', 'urgent']) {
    const d = decideAction(MAP, { health: { state } }, {});
    assert.equal(d.action, 'sick');
    assert.equal(d.oneShot, false);
  }
});

test('健康优先级高于情绪与交互', () => {
  const d = decideAction(MAP, { health: { state: 'observe' }, emotion: 'happy', gesture: 'tap' }, {});
  assert.equal(d.action, 'sick');
  assert.equal(d.source, 'health');
});

test('情绪高于交互；情绪动作一次性', () => {
  const d = decideAction(MAP, { health: { state: 'normal' }, emotion: 'annoyed', gesture: 'tap' }, {});
  assert.equal(d.action, 'crouch');
  assert.equal(d.source, 'chat_emotion');
  assert.equal(d.oneShot, true);
});

test('情绪映射全表', () => {
  const expect = { happy: 'happy', relaxed: 'idle', annoyed: 'crouch', fearful: 'sad', painful: 'sick' };
  for (const [emotion, action] of Object.entries(expect)) {
    assert.equal(decideAction(MAP, { emotion }, {}).action, action);
  }
});

test('seeking_attention 与 tap 左右交替（按 source 计数）', () => {
  const counters = {};
  const first = decideAction(MAP, { gesture: 'tap' }, counters);
  assert.equal(first.action, 'look_left');
  assert.equal(first.alternate, true);
  counters.interaction = (counters.interaction ?? 0) + 1;
  assert.equal(decideAction(MAP, { gesture: 'tap' }, counters).action, 'look_right');
  counters.interaction += 1;
  assert.equal(decideAction(MAP, { gesture: 'tap' }, counters).action, 'look_left');
  assert.equal(decideAction(MAP, { emotion: 'seeking_attention' }, {}).action, 'look_left');
});

test('long_press → happy 一次性', () => {
  const d = decideAction(MAP, { gesture: 'long_press' }, {});
  assert.equal(d.action, 'happy');
  assert.equal(d.oneShot, true);
});

test('无输入/无映射 → idle；未知状态不命中规则', () => {
  assert.equal(decideAction(MAP, {}, {}).action, 'idle');
  assert.equal(decideAction(null, { health: { state: 'observe' } }, {}).action, 'idle');
  assert.equal(decideAction(MAP, { health: { state: 'weird' } }, {}).action, 'idle');
});

test('health events 缺省按 none；有事件时 normal+none 不命中', () => {
  assert.equal(decideAction(MAP, { health: { state: 'normal' } }, {}).action, 'idle');
  assert.equal(decideAction(MAP, { health: { state: 'normal', events: 'active' } }, {}).action, 'idle');
});

test('isActionMap 形状守卫与版本比对', () => {
  assert.equal(isActionMap(MAP), true);
  assert.equal(isActionMap({ version: 1 }), false);
  assert.equal(isActionMap(null), false);
  assert.equal(isActionMap({ ...MAP, rules: 'x' }), false);
  assert.equal(mapChanged(null, MAP), true);
  assert.equal(mapChanged(MAP, MAP), false);
  assert.equal(mapChanged(MAP, { ...MAP, version: 'am-2026-12-01' }), true);
});

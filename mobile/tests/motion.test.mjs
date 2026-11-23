// F14 萌宠动图：状态映射、手势交替、一次性动作收尾与配置校验。
import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  emotionActions, gifUrl, initialMotionState, isMotionConfig, oneShotMs, pickInteraction,
  reduceMotion, standbyFor, statusLabel, MOTION_FADE_MS,
} from '../src/lib/motion.ts';

const config = {
  version: 'mo-test',
  max_seconds: 7,
  fps: 12,
  height: 480,
  standby: 'idle',
  actions: ['idle', 'happy', 'play', 'groom', 'stretch', 'yawn', 'sick', 'alert', 'look_left', 'look_right'],
  health: { normal: 'idle', observe: 'alert', vet: 'sick', urgent: 'sick' },
  gestures: {
    tap: { actions: ['happy', 'play'], replies: ['蹭了蹭你的手。', '扑了个空。'] },
    long_press: { actions: ['groom', 'stretch', 'yawn'], replies: ['开始洗脸。', '伸懒腰。', '打哈欠。'] },
    swipe_left: { actions: ['look_left'], replies: ['看向左边。'] },
    swipe_right: { actions: ['look_right'], replies: ['看向右边。'] },
  },
  emotions: { happy: 'happy', annoyed: 'alert', seeking_attention: ['look_left', 'look_right'] },
  labels: { idle: '待机', happy: '开心', play: '玩耍' },
  status_labels: { normal: '精神不错', observe: '在观察', vet: '建议就医', urgent: '建议立即就医' },
  min_ready: 8,
};

const view = {
  task_id: 'a'.repeat(32),
  status: 'succeeded',
  config_version: 'mo-test',
  base_image: { url: 'https://fake.local/base.png', version_id: 'v-base' },
  gifs: {
    idle: { status: 'ready', url: 'https://fake.local/idle.gif', duration_s: 3 },
    happy: { status: 'failed', url: null },
  },
  ready_count: 1,
  usable: false,
  config,
};

const apply = (state, events) => events.reduce(reduceMotion, state);

test('配置校验拒绝缺字段与未知待机动作', () => {
  assert.equal(isMotionConfig(config), true);
  assert.equal(isMotionConfig(null), false);
  assert.equal(isMotionConfig({ ...config, actions: [] }), false);
  assert.equal(isMotionConfig({ ...config, standby: 'dance' }), false);
  assert.equal(isMotionConfig({ ...config, max_seconds: 0 }), false);
});

test('健康状态决定待机动作，未登记状态回落到 standby（F14-3）', () => {
  assert.equal(standbyFor(config, 'normal'), 'idle');
  assert.equal(standbyFor(config, 'observe'), 'alert');
  assert.equal(standbyFor(config, 'vet'), 'sick');
  assert.equal(standbyFor(config, 'urgent'), 'sick');
  assert.equal(standbyFor(config, 'unknown'), 'idle');
  assert.equal(standbyFor(null, 'vet'), 'idle');
});

test('手势动作按计数交替，回应文案同步轮换（F14-2）', () => {
  const counters = {};
  const first = pickInteraction(config, 'tap', counters);
  counters.tap = 1;
  const second = pickInteraction(config, 'tap', counters);
  counters.tap = 2;
  const third = pickInteraction(config, 'tap', counters);
  assert.equal(first.action, 'happy');
  assert.equal(second.action, 'play');
  assert.equal(third.action, 'happy');
  assert.equal(first.reply, '蹭了蹭你的手。');
  assert.equal(second.reply, '扑了个空。');
  assert.equal(pickInteraction(config, 'unknown', counters), null);
});

test('情绪映射支持单动作与交替动作（F14-2）', () => {
  assert.deepEqual(emotionActions(config, 'happy'), ['happy']);
  assert.deepEqual(emotionActions(config, 'annoyed'), ['alert']);
  assert.deepEqual(emotionActions(config, 'seeking_attention'), ['look_left', 'look_right']);
  assert.deepEqual(emotionActions(config, 'painful'), []);
  assert.deepEqual(emotionActions(null, 'happy'), []);
});

test('一次性动作时长取 GIF 实际值，缺失回落配置上限', () => {
  assert.equal(oneShotMs(config, view, 'idle'), 3000);
  assert.equal(oneShotMs(config, view, 'happy'), 7000);
  assert.equal(MOTION_FADE_MS, 300);
});

test('只有 ready 且有 url 的动作才可播放', () => {
  assert.equal(gifUrl(view, 'idle'), 'https://fake.local/idle.gif');
  assert.equal(gifUrl(view, 'happy'), null);
  assert.equal(gifUrl(null, 'idle'), null);
});

test('状态文案缺失时返回空串，不污染 UI', () => {
  assert.equal(statusLabel(config, 'observe'), '在观察');
  assert.equal(statusLabel(config, 'unknown'), '');
  assert.equal(statusLabel(config, null), '');
});

test('待机切换不打断一次性动作，播完落到新待机', () => {
  let state = initialMotionState('idle');
  state = reduceMotion(state, { type: 'gesture', key: 'tap', actions: ['happy'], replies: ['蹭手'] });
  assert.equal(state.action, 'happy');
  assert.equal(state.oneShot, true);
  assert.equal(state.reply, '蹭手');
  state = reduceMotion(state, { type: 'standby', action: 'sick' });
  assert.equal(state.action, 'happy');
  assert.equal(state.standby, 'sick');
  state = reduceMotion(state, { type: 'settle' });
  assert.equal(state.action, 'sick');
  assert.equal(state.oneShot, false);
});

test('手势计数进入状态，连续点按交替动作且重新计时', () => {
  let state = initialMotionState('idle');
  const tap = { type: 'gesture', key: 'tap', actions: ['happy', 'play'], replies: ['一', '二'] };
  state = reduceMotion(state, tap);
  assert.equal(state.action, 'happy');
  assert.equal(state.counters.tap, 1);
  state = reduceMotion(state, tap);
  assert.equal(state.action, 'play');
  assert.equal(state.counters.tap, 2);
  assert.equal(state.reply, '二');
  state = reduceMotion(state, { type: 'settle' });
  assert.equal(state.action, 'idle');
});

test('非一次性状态 settle 不变；空动作规则被忽略', () => {
  const idle = initialMotionState('idle');
  assert.equal(reduceMotion(idle, { type: 'settle' }), idle);
  assert.equal(reduceMotion(idle, { type: 'gesture', key: 'tap', actions: [], replies: [] }), idle);
});

test('回应文案独立清除，不影响播放动作', () => {
  let state = reduceMotion(initialMotionState('idle'),
                           { type: 'gesture', key: 'tap', actions: ['happy'], replies: ['被摸了'] });
  state = reduceMotion(state, { type: 'clearReply' });
  assert.equal(state.reply, '');
  assert.equal(state.action, 'happy');
  assert.equal(reduceMotion(state, { type: 'clearReply' }), state);
});

test('同一待机重复下发不产生新对象，避免无谓重渲染', () => {
  const state = apply(initialMotionState('idle'), [{ type: 'standby', action: 'alert' }]);
  assert.equal(state.action, 'alert');
  assert.equal(reduceMotion(state, { type: 'standby', action: 'alert' }), state);
});

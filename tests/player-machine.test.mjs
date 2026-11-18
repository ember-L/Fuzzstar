// T07 播放状态机：仅 loop 边界切换（AC-03-5）、错误降级（AC-03-6）、一次性动作播完回待机。
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FADE_MS, initialPlayerState, reducePlayer } from '../src/lib/player-machine.ts';

const apply = (state, events) => events.reduce(reducePlayer, state);

test('淡入淡出时长 300ms；初始 idle 无切换', () => {
  assert.equal(FADE_MS, 300);
  const s = initialPlayerState();
  assert.equal(s.action, 'idle');
  assert.equal(s.pending, null);
  assert.equal(s.fading, false);
});

test('健康 standby 变化只在 loop 边界切换（AC-04-4 一个周期内）', () => {
  let s = initialPlayerState();
  s = reducePlayer(s, { type: 'standby', action: 'sick' });
  assert.equal(s.action, 'idle'); // 播放中途不穿帮
  assert.deepEqual(s.pending, { action: 'sick', oneShot: false });
  s = reducePlayer(s, { type: 'loopEnd' });
  assert.equal(s.action, 'sick');
  assert.equal(s.fading, true);
  assert.equal(s.pending, null);
});

test('一次性动作播完回待机；待机更新后回到新待机', () => {
  let s = apply(initialPlayerState(), [
    { type: 'request', action: 'happy', oneShot: true },
    { type: 'loopEnd' },
  ]);
  assert.equal(s.action, 'happy');
  assert.equal(s.oneShot, true);
  s = reducePlayer(s, { type: 'standby', action: 'sick' });
  assert.equal(s.action, 'happy'); // 一次性动作不打断
  s = reducePlayer(s, { type: 'loopEnd' });
  assert.equal(s.action, 'sick');
  assert.equal(s.oneShot, false);
});

test('个人片就绪只在下一 loop 边界替换（AC-03-5）', () => {
  let s = initialPlayerState();
  s = reducePlayer(s, { type: 'upgrade', action: 'idle' });
  assert.equal(s.fading, false);
  assert.deepEqual(s.pending, { action: 'idle', oneShot: false });
  s = reducePlayer(s, { type: 'loopEnd' });
  assert.equal(s.action, 'idle');
  assert.equal(s.fading, true); // 同动作也触发重解析与淡入淡出
});

test('错误逐级降级 personal→placeholder→static，立即切换不白屏', () => {
  let s = initialPlayerState();
  s = reducePlayer(s, { type: 'error', kind: 'personal' });
  assert.equal(s.degraded.idle, 'placeholder');
  assert.equal(s.urgent, true);
  assert.deepEqual(s.pending, { action: 'idle', oneShot: false });
  s = reducePlayer(s, { type: 'error', kind: 'placeholder' });
  assert.equal(s.degraded.idle, 'static');
  s = reducePlayer(s, { type: 'error', kind: 'static' });
  assert.equal(s.degraded.idle, 'static'); // 兜底不再降
});

test('upgrade 清除降级（新个人片版本到达）', () => {
  let s = reducePlayer(initialPlayerState(), { type: 'error', kind: 'personal' });
  s = reducePlayer(s, { type: 'upgrade', action: 'idle' });
  assert.equal(s.degraded.idle, undefined);
});

test('无 pending 非一次性 loopEnd 不淡入淡出（无缝循环）', () => {
  const s = reducePlayer(initialPlayerState(), { type: 'loopEnd' });
  assert.equal(s.fading, false);
  assert.equal(s.action, 'idle');
});

test('重复请求同一持续动作忽略；fadeDone 复位', () => {
  let s = apply(initialPlayerState(), [{ type: 'standby', action: 'sick' }, { type: 'loopEnd' }]);
  s = reducePlayer(s, { type: 'request', action: 'sick', oneShot: false });
  assert.equal(s.pending, null);
  s = reducePlayer(s, { type: 'fadeDone' });
  assert.equal(s.fading, false);
});

test('交互请求在待机播放时排队到 loop 边界', () => {
  let s = reducePlayer(initialPlayerState(), { type: 'request', action: 'look_left', oneShot: true });
  assert.equal(s.action, 'idle');
  s = reducePlayer(s, { type: 'loopEnd' });
  assert.equal(s.action, 'look_left');
  s = reducePlayer(s, { type: 'loopEnd' });
  assert.equal(s.action, 'idle');
});

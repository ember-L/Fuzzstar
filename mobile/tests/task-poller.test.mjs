import assert from 'node:assert/strict';
import test from 'node:test';
import { POLL_INTERVAL_MS, TASK_TIMEOUTS_MS, pollTask } from '../src/lib/task-poller.ts';
import { ApiError } from '../src/lib/session.ts';

const taskId = 'b'.repeat(32);

function harness({ statuses = ['running', 'running', 'succeeded'], visible = true, fail = null } = {}) {
  let clock = 0;
  const calls = [];
  const sleeps = [];
  let index = 0;
  const deps = {
    now: () => clock,
    sleep: async ms => { sleeps.push(ms); clock += ms; },
    isVisible: () => visible,
    fetchTask: async (id, signal) => {
      calls.push({ id, at: clock, aborted: signal.aborted });
      const i = index;
      index += 1;
      if (fail && fail(i)) throw fail(i);
      const status = statuses[Math.min(i, statuses.length - 1)];
      return { task_id: id, type: 'avatar_batch', status, result: status === 'succeeded' ? { usable: true, ready_count: 7 } : null };
    },
  };
  return { deps, calls, sleeps, advance: ms => { clock += ms; }, clock: () => clock };
}

test('polls every 2 seconds until the task settles and returns the result', async () => {
  const h = harness();
  const outcome = await pollTask(taskId, 'avatar_batch', { ...h.deps, signal: new AbortController().signal });
  assert.equal(outcome.kind, 'settled');
  assert.equal(outcome.task.status, 'succeeded');
  assert.deepEqual(outcome.task.result, { usable: true, ready_count: 7 });
  assert.deepEqual(h.calls.map(c => c.at), [0, POLL_INTERVAL_MS, 2 * POLL_INTERVAL_MS]);
  assert.ok(h.calls.every(c => c.id === taskId && !c.aborted));
});

test('failed tasks settle too so the UI can offer a retry', async () => {
  const h = harness({ statuses: ['running', 'failed'] });
  const outcome = await pollTask(taskId, 'avatar_batch', { ...h.deps, signal: new AbortController().signal });
  assert.equal(outcome.kind, 'settled');
  assert.equal(outcome.task.status, 'failed');
});

test('each task type has its own timeout and polling stops at the deadline', async () => {
  assert.deepEqual(TASK_TIMEOUTS_MS, { avatar_batch: 600_000, screening_analysis: 60_000, audio_interpret: 45_000, gif_export: 60_000 });
  for (const [type, limit] of Object.entries(TASK_TIMEOUTS_MS)) {
    const h = harness({ statuses: ['running'] });
    const outcome = await pollTask(taskId, type, { ...h.deps, signal: new AbortController().signal });
    assert.equal(outcome.kind, 'timeout', type);
    assert.ok(h.clock() >= limit, type);
    assert.ok(h.calls.every(c => c.at < limit), type);
  }
});

test('pauses fetching while hidden and resumes when visible again', async () => {
  let visible = true;
  const h = harness({ statuses: ['running', 'running', 'succeeded'] });
  h.deps.isVisible = () => visible;
  const originalSleep = h.deps.sleep;
  h.deps.sleep = async ms => { await originalSleep(ms); if (h.calls.length === 1) visible = false; if (h.clock() >= 10_000) visible = true; };
  const outcome = await pollTask(taskId, 'avatar_batch', { ...h.deps, signal: new AbortController().signal });
  assert.equal(outcome.kind, 'settled');
  const hiddenCalls = h.calls.filter(c => c.at >= 2_000 && c.at < 10_000);
  assert.equal(hiddenCalls.length, 0);
  assert.ok(h.calls.length >= 3);
});

test('aborting stops polling without another fetch', async () => {
  const controller = new AbortController();
  const h = harness({ statuses: ['running'] });
  const originalSleep = h.deps.sleep;
  h.deps.sleep = async ms => { await originalSleep(ms); controller.abort(); };
  const outcome = await pollTask(taskId, 'avatar_batch', { ...h.deps, signal: controller.signal });
  assert.equal(outcome.kind, 'aborted');
  assert.equal(h.calls.length, 1);
});

test('transient fetch errors are retried but a missing task is surfaced', async () => {
  const h = harness({ statuses: ['succeeded'], fail: i => (i === 0 ? new Error('network down') : null) });
  const outcome = await pollTask(taskId, 'avatar_batch', { ...h.deps, signal: new AbortController().signal });
  assert.equal(outcome.kind, 'settled');
  assert.equal(h.calls.length, 2);
  const gone = harness({ fail: () => new ApiError(404, 'NOT_FOUND', '任务不存在') });
  await assert.rejects(pollTask(taskId, 'avatar_batch', { ...gone.deps, signal: new AbortController().signal }), ApiError);
});

test('unknown task types require an explicit timeout', async () => {
  const h = harness();
  await assert.rejects(pollTask(taskId, 'mystery', { ...h.deps, signal: new AbortController().signal }), /timeout/i);
  const outcome = await pollTask(taskId, 'mystery', { ...h.deps, timeoutMs: 4_000, signal: new AbortController().signal });
  assert.equal(outcome.kind, 'timeout');
});

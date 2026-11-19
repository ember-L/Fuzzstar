export const POLL_INTERVAL_MS = 2_000;
export const TASK_TIMEOUTS_MS: Record<string, number> = {
  avatar_batch: 600_000,
  screening_analysis: 60_000,
  audio_interpret: 45_000,
  gif_export: 60_000,
};

export type TaskSnapshot = { task_id: string; type: string; status: string; result: unknown; download_url?: string | null };
export type PollOutcome =
  | { kind: 'settled'; task: TaskSnapshot }
  | { kind: 'timeout' }
  | { kind: 'aborted' };

type Deps = {
  fetchTask: (taskId: string, signal: AbortSignal) => Promise<TaskSnapshot>;
  signal: AbortSignal;
  intervalMs?: number;
  timeoutMs?: number;
  now?: () => number;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
  isVisible?: () => boolean;
};

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise(resolve => {
    if (signal.aborted || ms <= 0) return resolve();
    const done = () => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve(); };
    const timer = setTimeout(done, ms);
    signal.addEventListener('abort', done, { once: true });
  });
}

export async function pollTask(taskId: string, type: string, deps: Deps): Promise<PollOutcome> {
  const timeoutMs = deps.timeoutMs ?? TASK_TIMEOUTS_MS[type];
  if (timeoutMs === undefined) throw new Error(`Unknown task type "${type}": provide an explicit timeoutMs.`);
  const interval = deps.intervalMs ?? POLL_INTERVAL_MS;
  const now = deps.now ?? Date.now;
  const sleep = deps.sleep ?? delay;
  const isVisible = deps.isVisible ?? (() => true);
  const deadline = now() + timeoutMs;
  for (;;) {
    if (deps.signal.aborted) return { kind: 'aborted' };
    const remaining = deadline - now();
    if (remaining <= 0) return { kind: 'timeout' };
    if (!isVisible()) { await sleep(Math.min(interval, remaining), deps.signal); continue; }
    try {
      const task = await deps.fetchTask(taskId, deps.signal);
      if (deps.signal.aborted) return { kind: 'aborted' };
      if (task.status === 'succeeded' || task.status === 'failed') return { kind: 'settled', task };
    } catch (error) {
      if (deps.signal.aborted) return { kind: 'aborted' };
      const status = (error as { status?: unknown } | null)?.status;
      if (status === 404 || status === 403) throw error;
    }
    const wait = Math.min(interval, deadline - now());
    if (wait <= 0) return { kind: 'timeout' };
    await sleep(wait, deps.signal);
  }
}

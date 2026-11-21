// 萌宠动图（FRD F14-2/3/4）：配置校验、待机动作选择、手势映射与播放状态机。
// 纯函数：一次性动作由组件计时收尾，状态机只决定播哪个动作、何时回待机。

export interface MotionGesture {
  actions: string[];
  replies: string[];
}

export interface MotionConfig {
  version: string;
  max_seconds: number;
  fps: number;
  height: number;
  standby: string;
  actions: string[];
  health: Record<string, string>;
  gestures: Record<string, MotionGesture>;
  emotions?: Record<string, string | string[]>;
  labels: Record<string, string>;
  status_labels: Record<string, string>;
  min_ready: number;
}

export interface MotionGif {
  status: 'ready' | 'failed' | 'pending';
  url: string | null;
  version_id?: string;
  duration_s?: number;
}

export interface MotionView {
  task_id: string;
  status: string;
  config_version: string;
  base_image: { url: string; version_id: string } | null;
  gifs: Record<string, MotionGif>;
  ready_count: number;
  usable: boolean;
  config: MotionConfig;
}

export const MOTION_FADE_MS = 300;

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string');
}

export function isMotionConfig(value: unknown): value is MotionConfig {
  if (!value || typeof value !== 'object') return false;
  const config = value as Record<string, unknown>;
  if (typeof config.version !== 'string' || !config.version) return false;
  if (typeof config.standby !== 'string' || !config.standby) return false;
  if (!isStringArray(config.actions) || config.actions.length === 0) return false;
  if (config.actions.includes(config.standby) === false) return false;
  if (typeof config.max_seconds !== 'number' || config.max_seconds <= 0) return false;
  if (!config.health || typeof config.health !== 'object') return false;
  if (!config.gestures || typeof config.gestures !== 'object') return false;
  return true;
}

// 健康状态决定待机动作（F14-3）：未登记的状态回落到 standby，不改变红线语义。
export function standbyFor(config: MotionConfig | null, healthState?: string | null): string {
  if (!config) return 'idle';
  if (healthState && config.health[healthState]) return config.health[healthState];
  return config.standby;
}

// 同一手势按计数交替，避免每次点按都播同一条（F14-2）。
function pickFromRule(rule: MotionGesture, index: number): { action: string; reply: string } | null {
  if (rule.actions.length === 0) return null;
  const slot = index % rule.actions.length;
  return { action: rule.actions[slot], reply: rule.replies[slot % rule.replies.length] ?? '' };
}

export function pickInteraction(
  config: MotionConfig | null,
  gesture: string,
  counters: Record<string, number>,
): { action: string; reply: string } | null {
  const rule = config?.gestures?.[gesture];
  return rule ? pickFromRule(rule, counters[gesture] ?? 0) : null;
}

// 聊天情绪只触发一次性动作；未登记的情绪不改变待机（F14-2 与聊天联动）。
export function emotionActions(config: MotionConfig | null, emotion: string): string[] {
  const mapped = config?.emotions?.[emotion];
  if (!mapped) return [];
  return Array.isArray(mapped) ? mapped : [mapped];
}

// 一次性动作时长取该动作 GIF 的实际时长，缺失时回落到配置上限（F14-1 的 ≤7s）。
export function oneShotMs(config: MotionConfig | null, view: MotionView | null, action: string): number {
  const seconds = view?.gifs?.[action]?.duration_s ?? config?.max_seconds ?? 7;
  return Math.min(Math.max(seconds, 0.8), config?.max_seconds ?? 7) * 1000;
}

export function gifUrl(view: MotionView | null, action: string): string | null {
  const gif = view?.gifs?.[action];
  return gif?.status === 'ready' && gif.url ? gif.url : null;
}

export function actionLabel(config: MotionConfig | null, action: string): string {
  return config?.labels?.[action] ?? action;
}

export function statusLabel(config: MotionConfig | null, healthState?: string | null): string {
  if (!healthState) return '';
  return config?.status_labels?.[healthState] ?? '';
}

export interface MotionState {
  action: string;
  oneShot: boolean;
  standby: string;
  counters: Record<string, number>;
  reply: string;
}

export type MotionEvent =
  | { type: 'standby'; action: string }
  | { type: 'gesture'; key: string; actions: string[]; replies: string[] }
  | { type: 'settle' }
  | { type: 'clearReply' };

export function initialMotionState(standby = 'idle'): MotionState {
  return { action: standby, oneShot: false, standby, counters: {}, reply: '' };
}

export function reduceMotion(state: MotionState, event: MotionEvent): MotionState {
  switch (event.type) {
    case 'standby': {
      // 一次性动作播完前不打断，只记账新待机；播完 settle 自然落到新待机。
      if (event.action === state.standby && (state.oneShot || state.action === event.action)) return state;
      if (state.oneShot) return { ...state, standby: event.action };
      return { ...state, action: event.action, standby: event.action, oneShot: false };
    }
    case 'gesture': {
      const picked = pickFromRule({ actions: event.actions, replies: event.replies },
                                  state.counters[event.key] ?? 0);
      if (!picked) return state;
      return {
        ...state, action: picked.action, oneShot: true,
        counters: { ...state.counters, [event.key]: (state.counters[event.key] ?? 0) + 1 },
        reply: picked.reply,
      };
    }
    case 'settle':
      return state.oneShot ? { ...state, action: state.standby, oneShot: false } : state;
    case 'clearReply':
      return state.reply ? { ...state, reply: '' } : state;
    default:
      return state;
  }
}

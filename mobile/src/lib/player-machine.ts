// 播放状态机（FRD F03-5/6、AC-03-5/6、AC-04-4）。纯 reducer：
// 所有切换只在 loop 边界发生（动作中途不穿帮）；错误降级立即生效；一次性动作播完回待机。

export const FADE_MS = 300;

export type SourceKind = 'personal' | 'placeholder' | 'static';
export type Degraded = Record<string, 'placeholder' | 'static'>;

export interface PlayerState {
  action: string;
  oneShot: boolean;
  standby: string;
  pending: { action: string; oneShot: boolean } | null;
  urgent: boolean;
  fading: boolean;
  degraded: Degraded;
}

export type PlayerEvent =
  | { type: 'standby'; action: string }
  | { type: 'request'; action: string; oneShot: boolean }
  | { type: 'loopEnd' }
  | { type: 'error'; kind: SourceKind }
  | { type: 'upgrade'; action: string }
  | { type: 'fadeDone' };

export function initialPlayerState(standby = 'idle'): PlayerState {
  return { action: standby, oneShot: false, standby, pending: null, urgent: false, fading: false, degraded: {} };
}

export function reducePlayer(state: PlayerState, event: PlayerEvent): PlayerState {
  switch (event.type) {
    case 'standby': {
      if (event.action === state.standby) return state;
      const next = { ...state, standby: event.action };
      // 一次性动作播放中不打断，播完自然回到新待机；持续待机动作在下一 loop 边界切换。
      if (!state.oneShot && state.action !== event.action) {
        next.pending = { action: event.action, oneShot: false };
      }
      return next;
    }
    case 'request': {
      if (event.action === state.action && !event.oneShot) return state;
      if (event.action === state.action && state.oneShot) return state;
      return { ...state, pending: { action: event.action, oneShot: event.oneShot } };
    }
    case 'loopEnd': {
      if (state.pending) {
        return { ...state, action: state.pending.action, oneShot: state.pending.oneShot, pending: null, urgent: false, fading: true };
      }
      if (state.oneShot) {
        return { ...state, action: state.standby, oneShot: false, fading: true };
      }
      return state; // 无缝循环，不淡入淡出
    }
    case 'error': {
      const level = event.kind === 'personal' ? 'placeholder' : event.kind === 'placeholder' ? 'static' : null;
      if (!level) return state; // 静态兜底不再降级，永不白屏
      return {
        ...state,
        degraded: { ...state.degraded, [state.action]: level },
        pending: { action: state.action, oneShot: state.oneShot },
        urgent: true,
      };
    }
    case 'upgrade': {
      const degraded = { ...state.degraded };
      delete degraded[event.action];
      const next = { ...state, degraded };
      if (event.action === state.action && !state.oneShot) {
        next.pending = { action: state.action, oneShot: false };
      }
      return next;
    }
    case 'fadeDone':
      return state.fading ? { ...state, fading: false } : state;
    default:
      return state;
  }
}

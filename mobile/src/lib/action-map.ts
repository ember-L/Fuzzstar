// 动作映射引擎（FRD 附录 C / F04-4）。映射由 GET /config/action-map 版本化下发，
// 本模块只按服务端规则匹配，不内置规则副本：改映射不改代码。纯函数，便于测试。

export interface ActionMapRule {
  source: string;
  condition: Record<string, string | string[]>;
  action: string | string[];
  note?: string;
}

export interface ActionMap {
  version: string;
  actions: string[];
  priority: string[];
  rules: ActionMapRule[];
}

export interface TriggerInputs {
  health?: { state: string; events?: string } | null;
  emotion?: string | null;
  gesture?: string | null;
}

export interface ActionDecision {
  action: string;
  source: string;
  oneShot: boolean;
  alternate: boolean;
}

const IDLE: ActionDecision = { action: 'idle', source: 'idle', oneShot: false, alternate: false };

export function isActionMap(value: unknown): value is ActionMap {
  if (!value || typeof value !== 'object') return false;
  const map = value as Record<string, unknown>;
  return typeof map.version === 'string' && map.version.length > 0
    && Array.isArray(map.actions) && map.actions.every(a => typeof a === 'string')
    && Array.isArray(map.priority) && map.priority.every(p => typeof p === 'string')
    && Array.isArray(map.rules);
}

export function mapChanged(cached: ActionMap | null, fetched: ActionMap): boolean {
  return !cached || cached.version !== fetched.version;
}

function inputsFor(source: string, inputs: TriggerInputs): Record<string, string> | null {
  if (source === 'health') {
    if (!inputs.health) return null;
    return { state: inputs.health.state, events: inputs.health.events ?? 'none' };
  }
  if (source === 'chat_emotion') return inputs.emotion ? { emotion: inputs.emotion } : null;
  if (source === 'interaction') return inputs.gesture ? { gesture: inputs.gesture } : null;
  return null;
}

function matches(rule: ActionMapRule, values: Record<string, string>): boolean {
  return Object.entries(rule.condition).every(([key, expected]) => {
    const actual = values[key];
    if (actual === undefined) return false;
    return Array.isArray(expected) ? expected.includes(actual) : expected === actual;
  });
}

// 按 priority 顺序取第一条命中规则；数组动作按 counters[source] 交替。
// health 为持续状态；chat_emotion/interaction 一次性，播完回待机。
// 映射到 idle 的规则视为「回归待机」，不参与优先级覆盖（附录 C：待机是最低优先级基线）。
export function decideAction(
  map: ActionMap | null,
  inputs: TriggerInputs,
  counters: Record<string, number>,
): ActionDecision {
  if (!map) return IDLE;
  let standby: ActionDecision | null = null;
  for (const source of map.priority) {
    if (source === 'idle') continue;
    const values = inputsFor(source, inputs);
    if (!values) continue;
    const rule = map.rules.find(r => r.source === source && matches(r, values));
    if (!rule) continue;
    if (Array.isArray(rule.action)) {
      if (rule.action.length === 0) continue;
      const index = (counters[source] ?? 0) % rule.action.length;
      return { action: rule.action[index], source, oneShot: true, alternate: true };
    }
    if (rule.action === 'idle') {
      if (!standby) standby = { action: 'idle', source, oneShot: false, alternate: false };
      continue;
    }
    return { action: rule.action, source, oneShot: source !== 'health', alternate: false };
  }
  return standby ?? IDLE;
}

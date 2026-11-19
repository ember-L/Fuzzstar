// T08 首页健康聚合的纯展示逻辑（FRD F04）：状态文案、未评估占位、明细合计。
export interface Deduction {
  id: number;
  source: string;
  source_id: number | null;
  severity: string;
  symptoms: string[];
  score_delta: number;
  effective_delta: number;
  decayed: boolean;
  created_at: string;
  rules_version: string | null;
}

export interface HealthSummary {
  pet_id: number;
  state: string;
  score: number | null;
  rules_version: string;
  deductions: Deduction[];
  latest_screening: { screening_id: number; state: string; created_at: string } | null;
  diet_today: { date: string; total_g: number; total_kcal: number; count: number } | null;
  latest_weight: { weight_kg: number; measured_at: string } | null;
  urgent_card: { title: string; subtitle: string; preparation: string[] } | null;
}

const STATE_LABELS: Record<string, string> = {
  normal: '正常',
  observe: '观察中',
  vet: '建议就医',
  urgent: '紧急就医',
};

export function stateLabel(state: string): string {
  return STATE_LABELS[state] ?? state;
}

// 禁止默认 100：无初筛且无事件时后端给 null，UI 显示「未评估 --」。
export function scoreDisplay(score: number | null): string {
  return score === null ? '未评估  --' : String(score);
}

export function totalEffective(deductions: { effective_delta: number }[]): number {
  return deductions.reduce((sum, item) => sum + item.effective_delta, 0);
}

export function formatDateTime(iso: string): string {
  return iso.slice(5, 16).replace('T', ' ');
}

export function isUrgent(state: string): boolean {
  return state === 'urgent';
}

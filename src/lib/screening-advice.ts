export interface AdviceView {
  status: 'pending' | 'ready' | 'degraded';
  source: 'llm' | 'template' | null;
  text: string | null;
  tips: string[] | null;
}

export function shouldPollAdvice(detail: { task_id: string | null; advice: AdviceView | null }): boolean {
  return Boolean(detail.advice && detail.advice.status === 'pending' && detail.task_id);
}

export function adviceNotice(advice: AdviceView | null): string | null {
  if (!advice) return null;
  if (advice.status === 'pending') return 'AI 建议生成中…';
  if (advice.status === 'degraded') return 'AI 建议暂不可用，已按状态给出通用建议';
  return null;
}

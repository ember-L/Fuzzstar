// 初筛问卷的纯逻辑层：配置类型、必答校验、提交载荷与文案（FRD F05 / 附录 F）。
export interface SymptomSpec { code: string; label: string; frequency: boolean; severe_label: string | null }
export interface RedlineOption { code: string; label: string }
export interface RedlineSpec { code: string; label: string; options?: RedlineOption[]; derived?: { symptom: string; duration: string[] } }
export interface SymptomsConfig {
  version: string; duration_bands: string[]; frequency_bands: string[];
  spirit_options: string[]; appetite_options: string[]; notes_max: number;
  symptoms: SymptomSpec[]; redlines: RedlineSpec[];
}
export interface SymptomAnswer { duration: string | null; frequency: string | null; notes: string; severe: boolean }
export interface ScreeningMediaRef { mediaId: string; kind: 'photo' | 'video' }
export interface ScreeningForm {
  spirit: string | null; appetite: string | null;
  symptoms: Record<string, SymptomAnswer>;
  redlineOptions: string[]; media: ScreeningMediaRef[];
}

export const DISCLAIMER = 'AI 结果仅供日常健康管理参考,不替代专业兽医诊断';
export const STATE_LABELS: Record<string, string> = {
  normal: '状态良好', observe: '建议观察', vet: '建议就医', urgent: '建议立即就医',
};
export type StateTone = 'ok' | 'watch' | 'vet' | 'urgent';
export function stateTone(state: string): StateTone {
  if (state === 'urgent') return 'urgent';
  if (state === 'vet') return 'vet';
  if (state === 'observe') return 'watch';
  return 'ok';
}

export function emptyForm(): ScreeningForm {
  return { spirit: null, appetite: null, symptoms: {}, redlineOptions: [], media: [] };
}

export function missingFields(config: SymptomsConfig, form: ScreeningForm): string[] {
  const missing: string[] = [];
  if (!form.spirit) missing.push('spirit');
  if (!form.appetite) missing.push('appetite');
  for (const spec of config.symptoms) {
    const answer = form.symptoms[spec.code];
    if (!answer) continue;
    if (!answer.duration) missing.push(`${spec.code}.duration`);
    if (spec.frequency && !answer.frequency) missing.push(`${spec.code}.frequency`);
  }
  return missing;
}

export function buildPayload(form: ScreeningForm) {
  return {
    spirit: form.spirit,
    appetite: form.appetite,
    symptoms: Object.entries(form.symptoms).map(([code, answer]) => ({
      code,
      duration: answer.duration,
      ...(answer.frequency !== null ? { frequency: answer.frequency } : {}),
      ...(answer.notes ? { notes: answer.notes } : {}),
      ...(answer.severe ? { severe: true } : {}),
    })),
    redline_options: form.redlineOptions,
    media_ids: form.media.map(item => item.mediaId),
  };
}

export function mediaLimitError(media: { kind: 'photo' | 'video' }[]): string | null {
  const photos = media.filter(item => item.kind === 'photo').length;
  const videos = media.filter(item => item.kind === 'video').length;
  if (photos > 3) return '存证照片最多 3 张，请移除多余照片。';
  if (videos > 1) return '存证视频最多 1 段，请移除多余视频。';
  return null;
}

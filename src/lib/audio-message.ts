// 录音解读纯逻辑（FRD F09-3/4）：时长校验、情绪标签、置信度展示、录音格式。
// 自包含：Node ESM 测试可直接加载；录音/上传/轮询接线在聊天页。

export const AUDIO_MIN_SECONDS = 1;
export const AUDIO_MAX_SECONDS = 60;
export const AUDIO_CONFIDENCE_THRESHOLD = 0.4;
export const AUDIO_FOOTER = '情绪解读为娱乐性参考,置信度仅供判断展示。';

const EMOTION_LABELS: Record<string, string> = {
  happy: '开心', relaxed: '放松', annoyed: '烦躁', fearful: '害怕',
  painful: '疼痛', seeking_attention: '求关注', unrecognized: '未识别',
};

export function validateDuration(seconds: number): { ok: true; value: number } | { ok: false; message: string } {
  if (!Number.isFinite(seconds) || seconds < AUDIO_MIN_SECONDS) {
    return { ok: false, message: `录音太短，请至少录 ${AUDIO_MIN_SECONDS} 秒` };
  }
  if (seconds > AUDIO_MAX_SECONDS) {
    return { ok: false, message: `录音最长 ${AUDIO_MAX_SECONDS} 秒，已自动停止` };
  }
  return { ok: true, value: seconds };
}

export function emotionLabel(emotion: string | null | undefined): string {
  return (emotion && EMOTION_LABELS[emotion]) || EMOTION_LABELS.unrecognized;
}

export function confidenceText(emotion: string | null | undefined, confidence: number | null | undefined): string {
  if (!emotion || emotion === 'unrecognized') return '未识别';
  if (confidence == null || confidence < AUDIO_CONFIDENCE_THRESHOLD) return '不太确定';
  return `置信度 ${Math.round(confidence * 100)}%`;
}

export function recordingContentType(uri: string): string {
  const lower = uri.toLowerCase();
  if (lower.endsWith('.wav')) return 'audio/wav';
  if (lower.endsWith('.webm')) return 'audio/webm';
  if (lower.endsWith('.mp3')) return 'audio/mpeg';
  return 'audio/mp4';
}
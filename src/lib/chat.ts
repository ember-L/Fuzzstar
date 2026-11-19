// 文字聊天纯逻辑（FRD F09-1/2/6/7）：输入校验、离线队列项、缓存镜像映射。
// 自包含：仅类型导入，Node ESM 测试可直接加载；存储/网络接线在聊天页。
import type { QueueItem } from './retry-queue';
import type { CachedMessage } from './chat-cache';

export const CHAT_INPUT_MAX = 500;

export interface ChatMessage {
  id: number;
  role: 'user' | 'pet';
  kind: 'text' | 'audio';
  content: string | null;
  audio_url: string | null;
  emotion_label: string | null;
  emotion_confidence: number | null;
  task_id: string | null;
  created_at: string;
  source?: 'llm' | 'template' | 'redline';
}

export interface ChatGuidance {
  title: string;
  text: string;
  route: string;
}

export function validateChatInput(text: string): { ok: true; value: string } | { ok: false; message: string } {
  const value = text.trim();
  if (!value) return { ok: false, message: '说点什么吧' };
  if (value.length > CHAT_INPUT_MAX) return { ok: false, message: `消息不能超过 ${CHAT_INPUT_MAX} 字` };
  return { ok: true, value };
}

export function chatQueueItem(petId: number, sessionId: number, content: string, idempotencyKey: string, createdAt: number): Omit<QueueItem, 'id'> {
  return { kind: 'chat_text', petId, method: 'POST', path: `/chat/sessions/${sessionId}/messages`,
           body: JSON.stringify({ kind: 'text', content }), idempotencyKey, attempts: 0, createdAt, lastError: null };
}

export function parseChatBody(item: QueueItem): { content: string } {
  const body = JSON.parse(item.body) as { content?: string };
  return { content: body.content ?? '' };
}

function timestamp(iso: string): number {
  return Date.parse(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`);
}

export function toCachedMessage(message: ChatMessage, pending = false): CachedMessage {
  return { id: String(message.id), role: message.role, kind: message.kind,
           content: message.content ?? '', audioUrl: message.audio_url ?? null,
           emotionLabel: message.emotion_label, emotionConfidence: message.emotion_confidence,
           taskId: message.task_id, createdAt: timestamp(message.created_at), pending };
}

export function localPendingId(idempotencyKey: string): string {
  return `local-${idempotencyKey}`;
}

// 服务端确认后移除本地待发送占位，合并真实消息对（时间升序、同刻按 id 稳定）。
export function confirmSend(existing: CachedMessage[], localId: string, user: ChatMessage, pet: ChatMessage): CachedMessage[] {
  const byId = new Map<string, CachedMessage>();
  for (const message of existing) if (message.id !== localId) byId.set(message.id, message);
  for (const message of [toCachedMessage(user), toCachedMessage(pet)]) byId.set(message.id, message);
  return [...byId.values()].sort((a, b) => a.createdAt - b.createdAt || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

// 聊天缓存镜像（FRD F09-6）：弱网/飞行模式可读历史。
// 纯合并逻辑；持久化在 lib/offline-store.ts，聊天页接线随 T15。

export interface CachedMessage {
  id: string;
  role: 'user' | 'pet';
  kind: 'text' | 'audio';
  content: string;
  createdAt: number;
  pending: boolean;
}

export interface ChatCacheStore {
  put(petId: number, messages: CachedMessage[]): Promise<void>;
  list(petId: number, limit?: number): Promise<CachedMessage[]>;
}

// 按 id 去重（服务端确认覆盖本地待发送），时间升序、同刻按 id 稳定排序。
export function mergeMessages(existing: CachedMessage[], incoming: CachedMessage[]): CachedMessage[] {
  const byId = new Map<string, CachedMessage>();
  for (const message of existing) byId.set(message.id, message);
  for (const message of incoming) byId.set(message.id, message);
  return [...byId.values()].sort((a, b) => a.createdAt - b.createdAt || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

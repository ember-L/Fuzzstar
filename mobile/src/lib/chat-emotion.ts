// 聊天情绪总线（FRD F09-5）：回复到达→首页分身播一次对应动作后回待机。
// 聊天页 publish，首页订阅喂给 AvatarPlayer 的 emotionEvent prop（T07 预留）。
export interface EmotionEvent {
  id: number;
  petId: number;
  emotion: string;
}

export interface EmotionBus {
  publish(petId: number, emotion: string): EmotionEvent;
  subscribe(listener: (event: EmotionEvent) => void): () => void;
}

export function createEmotionBus(): EmotionBus {
  let nextId = 1;
  const listeners = new Set<(event: EmotionEvent) => void>();
  return {
    publish(petId, emotion) {
      const event: EmotionEvent = { id: nextId, petId, emotion };
      nextId += 1;
      for (const listener of [...listeners]) listener(event);
      return event;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
  };
}

export const emotionBus = createEmotionBus();

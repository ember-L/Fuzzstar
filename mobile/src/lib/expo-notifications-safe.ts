// expo-notifications 安全加载层。
// 背景：Expo Go 的内置原生模块版本可能落后于 npm 上的 JS 包（例如缺 ExpoTopicSubscriptionModule），
// 此时直接 import 会在模块初始化阶段抛错，导致整个 App 白屏。
// 这里改为惰性加载：原生模块不可用时返回 null，由调用方按「通知不可用」降级（软件内横幅 / 不调度）。
import type * as ExpoNotifications from 'expo-notifications';

export type NotificationsModule = typeof ExpoNotifications;

let cached: NotificationsModule | null | undefined;

export function getNotifications(): NotificationsModule | null {
  if (cached !== undefined) return cached;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    cached = require('expo-notifications') as NotificationsModule;
  } catch {
    cached = null;
  }
  return cached;
}

export function notificationsAvailable(): boolean {
  return getNotifications() !== null;
}

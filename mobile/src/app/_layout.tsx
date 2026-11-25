import { Stack, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { Platform } from 'react-native';
import { getNotifications } from '../lib/expo-notifications-safe';
import { routeFromNotificationData } from '../lib/recheck-reminder';
import { offlineSync } from '../lib/offline-sync';

// Expo Go 等环境可能缺少 expo-notifications 原生模块：缺失时跳过通知，不影响页面渲染。
const Notifications = Platform.OS === 'web' ? null : getNotifications();

if (Notifications) {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false }),
  });
}

export default function RootLayout() {
  const router = useRouter();
  // 浅离线补发循环：全局 5s 轮询＋回前台触发，饮食/文字待发送请求联网后自动补发（F07-5/F09-6）。
  useEffect(() => {
    offlineSync.start();
    return () => offlineSync.stop();
  }, []);
  useEffect(() => {
    if (Platform.OS === 'web') return;
    const module = getNotifications();
    if (!module) return;
    const subscription = module.addNotificationResponseReceivedListener(response => {
      const route = routeFromNotificationData(response.notification.request.content.data as Record<string, unknown>);
      if (route) router.push(route);
    });
    return () => subscription.remove();
  }, [router]);
  return <><StatusBar style="dark" /><Stack screenOptions={{ headerShown: false }} /></>;
}

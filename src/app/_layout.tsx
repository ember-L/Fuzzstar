import { Stack, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import { routeFromNotificationData } from '../lib/recheck-reminder';

if (Platform.OS !== 'web') {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false }),
  });
}

export default function RootLayout() {
  const router = useRouter();
  useEffect(() => {
    if (Platform.OS === 'web') return;
    const subscription = Notifications.addNotificationResponseReceivedListener(response => {
      const route = routeFromNotificationData(response.notification.request.content.data as Record<string, unknown>);
      if (route) router.push(route);
    });
    return () => subscription.remove();
  }, [router]);
  return <><StatusBar style="dark" /><Stack screenOptions={{ headerShown: false }} /></>;
}

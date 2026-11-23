// 本地通知适配层（F10）：expo-notifications 薄封装，便于后续按 FRD 评审切换 notifee。
// 网页端无本地通知能力：权限视为拒绝，走应用内横幅降级路径（F10-3）。
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import { isRecheckIdentifier, type RecheckReminder } from './recheck-reminder';
import { buildFeedingReminders, isFeedingIdentifier, type FeedingSettings } from './feeding-reminder';

export type PermissionState = 'granted' | 'denied' | 'undetermined';
export type ScheduleOutcome = 'scheduled' | 'denied' | 'unsupported';

function toState(settings: { granted: boolean; canAskAgain: boolean }): PermissionState {
  if (settings.granted) return 'granted';
  return settings.canAskAgain ? 'undetermined' : 'denied';
}

export async function getPermissionState(): Promise<PermissionState> {
  if (Platform.OS === 'web') return 'denied';
  return toState(await Notifications.getPermissionsAsync());
}

export async function requestPermission(): Promise<PermissionState> {
  if (Platform.OS === 'web') return 'denied';
  return toState(await Notifications.requestPermissionsAsync());
}

export async function scheduleRecheck(reminder: RecheckReminder): Promise<ScheduleOutcome> {
  if (Platform.OS === 'web') return 'unsupported';
  let permission = await getPermissionState();
  if (permission !== 'granted') permission = await requestPermission();
  if (permission !== 'granted') return 'denied';
  await Notifications.cancelScheduledNotificationAsync(reminder.identifier).catch(() => {});
  await Notifications.scheduleNotificationAsync({
    identifier: reminder.identifier,
    content: { title: reminder.title, body: reminder.body, data: reminder.data, sound: false },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: new Date(reminder.fireAt) },
  });
  return 'scheduled';
}

export async function cancelPetRechecks(petId: number): Promise<void> {
  if (Platform.OS === 'web') return;
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  await Promise.all(scheduled
    .filter(item => isRecheckIdentifier(item.identifier, petId))
    .map(item => Notifications.cancelScheduledNotificationAsync(item.identifier).catch(() => {})));
}

// 喂养提醒（F10-2）：DAILY 触发每天按时重复；先按猫取消再按当前设置重建，关闭即全部取消。
export async function scheduleFeeding(settings: FeedingSettings, petId: number, petName: string): Promise<ScheduleOutcome> {
  if (Platform.OS === 'web') return 'unsupported';
  await cancelPetFeeding(petId);
  if (!settings.enabled || settings.times.length === 0) return 'scheduled';
  let permission = await getPermissionState();
  if (permission !== 'granted') permission = await requestPermission();
  if (permission !== 'granted') return 'denied';
  for (const reminder of buildFeedingReminders(settings, petId, petName)) {
    await Notifications.scheduleNotificationAsync({
      identifier: reminder.identifier,
      content: { title: reminder.title, body: reminder.body, data: reminder.data, sound: false },
      trigger: { type: Notifications.SchedulableTriggerInputTypes.DAILY, hour: reminder.hour, minute: reminder.minute },
    });
  }
  return 'scheduled';
}

export async function cancelPetFeeding(petId: number): Promise<void> {
  if (Platform.OS === 'web') return;
  const scheduled = await Notifications.getAllScheduledNotificationsAsync();
  await Promise.all(scheduled
    .filter(item => isFeedingIdentifier(item.identifier, petId))
    .map(item => Notifications.cancelScheduledNotificationAsync(item.identifier).catch(() => {})));
}

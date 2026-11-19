import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { DEFAULT_FEEDING_SETTINGS, MAX_FEEDING_TIMES, isValidTime, normalizeSettings, type FeedingSettings } from '../../lib/feeding-reminder';
import { getPermissionState, requestPermission, scheduleFeeding, type PermissionState } from '../../lib/notifications';
import { getOfflineStore } from '../../lib/offline-store';
import { colors } from '../../theme';

const PRESET_TIMES = ['08:00', '12:00', '18:00', '22:00'];

export default function RemindersScreen() {
  const { petId } = useLocalSearchParams<{ petId: string }>();
  const [petName, setPetName] = useState('猫咪');
  const [settings, setSettings] = useState<FeedingSettings>(DEFAULT_FEEDING_SETTINGS);
  const [permission, setPermission] = useState<PermissionState>('undetermined');
  const [timeText, setTimeText] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getOfflineStore().then(store => store.reminders.get(Number(petId))).then(setSettings).catch(() => {});
    getPermissionState().then(setPermission).catch(() => {});
    api.authorized<{ name: string }>(`/pets/${petId}`).then(pet => setPetName(pet.name)).catch(() => {});
  }, [petId]);
  useEffect(() => { load(); }, [load]);

  const addTime = (time: string) => {
    if (!isValidTime(time)) { setError('时间需为 24 小时制 HH:MM，例如 08:00'); return; }
    if (settings.times.length >= MAX_FEEDING_TIMES) { setError(`最多 ${MAX_FEEDING_TIMES} 个时段`); return; }
    setError(null);
    setSettings(current => normalizeSettings({ enabled: current.enabled, times: [...current.times, time] }));
    setTimeText('');
  };
  const removeTime = (time: string) => setSettings(current => ({ ...current, times: current.times.filter(t => t !== time) }));

  const save = async () => {
    setBusy(true); setMessage(null); setError(null);
    const normalized = normalizeSettings(settings);
    try {
      const store = await getOfflineStore();
      await store.reminders.set(Number(petId), normalized);
      setSettings(normalized);
      const outcome = await scheduleFeeding(normalized, Number(petId), petName);
      if (outcome === 'scheduled') {
        setMessage(normalized.enabled ? `已保存，每天 ${normalized.times.join('、')} 提醒喂 ${petName}。` : '已关闭喂养提醒。');
      } else if (outcome === 'denied') {
        setError('通知权限被拒绝，提醒无法触发；授权后重新保存即可。');
      } else {
        setError('网页端不支持本地通知，请在 App 内设置喂养提醒。');
      }
      setPermission(await getPermissionState());
    } catch {
      setError('保存失败，请稍后重试');
    } finally { setBusy(false); }
  };

  const regrant = async () => {
    const state = await requestPermission();
    setPermission(state);
    if (state === 'granted') await save();
  };

  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>喂养提醒</Text>
      <Text style={styles.subtitle}>每猫独立、默认关闭；开关与时间仅保存在本机，到点本地通知。</Text>
      <View style={styles.card}>
        <View style={styles.switchRow}>
          <Text style={styles.cardTitle}>启用喂养提醒</Text>
          <Switch accessibilityLabel="启用喂养提醒" value={settings.enabled} disabled={busy || settings.times.length === 0}
            onValueChange={value => setSettings(normalizeSettings({ enabled: value, times: settings.times }))} />
        </View>
        {settings.times.length === 0 ? <Text style={styles.hint}>先添加至少一个提醒时间。</Text> : null}
        <View style={styles.chips}>
          {settings.times.map(time => (
            <Pressable key={time} accessibilityRole="button" accessibilityLabel={`移除时段 ${time}`} style={styles.chipOn} onPress={() => removeTime(time)}>
              <Text style={styles.chipOnText}>{time} ×</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.label}>常用时段（点击添加，最多 {MAX_FEEDING_TIMES} 个）</Text>
        <View style={styles.chips}>
          {PRESET_TIMES.filter(time => !settings.times.includes(time)).map(time => (
            <Pressable key={time} accessibilityRole="button" style={styles.chip} onPress={() => addTime(time)}>
              <Text style={styles.chipText}>{time}</Text>
            </Pressable>
          ))}
        </View>
        <TextInput accessibilityLabel="自定义提醒时间，24小时制" placeholder="自定义 HH:MM，如 07:30" maxLength={5}
          value={timeText} onChangeText={setTimeText} style={styles.input} />
        <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => addTime(timeText.trim())}>
          <Text style={styles.secondaryText}>添加时间</Text>
        </Pressable>
        <Pressable accessibilityRole="button" disabled={busy} style={[styles.primary, busy && styles.disabled]} onPress={save}>
          <Text style={styles.primaryText}>{busy ? '保存中…' : '保存提醒设置'}</Text>
        </Pressable>
        {message ? <Text style={styles.info}>{message}</Text> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
      </View>
      {permission === 'denied' ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>通知权限已拒绝</Text>
          <Text style={styles.hint}>提醒设置已保存，但系统不会弹出通知。重新授权后回到本页保存即可恢复。</Text>
          <Pressable accessibilityRole="button" style={styles.secondary} onPress={regrant}>
            <Text style={styles.secondaryText}>重新授权</Text>
          </Pressable>
        </View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  subtitle: { fontSize: 12, lineHeight: 18, color: colors.secondary },
  card: { padding: 16, borderRadius: 18, backgroundColor: colors.surface, gap: 10 },
  cardTitle: { fontSize: 15, fontWeight: '600', color: colors.text },
  switchRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  hint: { fontSize: 12, lineHeight: 18, color: colors.secondary },
  label: { fontSize: 13, fontWeight: '600', color: colors.secondary },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 14, borderRadius: 12, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border },
  chipText: { fontSize: 13, fontWeight: '600', color: colors.text },
  chipOn: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 14, borderRadius: 12, backgroundColor: colors.brand },
  chipOnText: { fontSize: 13, fontWeight: '700', color: colors.onBrand },
  input: { minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, paddingHorizontal: 14, fontSize: 15, color: colors.text },
  primary: { minHeight: 48, borderRadius: 14, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: colors.onBrand, fontWeight: '700', fontSize: 15 },
  secondary: { minHeight: 44, borderRadius: 14, borderWidth: 1, borderColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { color: colors.text, fontWeight: '700', fontSize: 14 },
  disabled: { opacity: 0.45 },
  info: { fontSize: 13, color: '#3D6B1E' },
  error: { fontSize: 13, color: '#B3261E' },
});

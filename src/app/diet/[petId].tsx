import { Link, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { BACKDATE_OPTIONS, FOOD_LABELS, fedAtFor, localDate, parseAmount, shiftDay, tzOffsetMinutes, type DietRecord } from '../../lib/diet';
import { ApiError } from '../../lib/session';
import { formatClock } from '../../lib/timeline';
import { colors } from '../../theme';

interface DailyView { date: string; items: DietRecord[]; total_g: number; total_kcal: number; count: number }

const FOOD_TYPES = ['dry', 'wet', 'snack', 'other'] as const;

function dayLabel(day: string): string {
  const today = localDate();
  if (day === today) return '今天';
  if (day === shiftDay(today, -1)) return '昨天';
  const [, month, date] = day.split('-');
  return `${Number(month)}月${Number(date)}日`;
}

function recordDay(fedAt: string): string {
  const value = /Z|[+-]\d{2}:\d{2}$/.test(fedAt) ? fedAt : `${fedAt}Z`;
  return localDate(new Date(value));
}

export default function DietScreen() {
  const { petId, date } = useLocalSearchParams<{ petId: string; date?: string }>();
  const [day, setDay] = useState(date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : localDate());
  const [daily, setDaily] = useState<DailyView | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [foodType, setFoodType] = useState<string>('dry');
  const [amountText, setAmountText] = useState('');
  const [hours, setHours] = useState(0);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback((target: string) => {
    api.authorized<DailyView>(`/pets/${petId}/diet?date=${target}&tz_offset_minutes=${tzOffsetMinutes()}`)
      .then(data => { setDaily(data); setLoadFailed(false); })
      .catch(() => setLoadFailed(true));
  }, [petId]);
  useEffect(() => { load(day); }, [day, load]);

  // 快录三步：进入页面 → 输入克数 → 点「记一笔」（类型默认干粮、时间默认现在）。
  const submit = async () => {
    const parsed = parseAmount(amountText);
    if (!parsed.ok) { setMessage(parsed.message); return; }
    setBusy(true); setMessage(null);
    try {
      const body: Record<string, unknown> = { food_type: foodType, amount_g: parsed.value };
      if (hours > 0) body.fed_at = fedAtFor(hours);
      if (note.trim()) body.note = note.trim();
      const record = await api.authorized<DietRecord>(`/pets/${petId}/diet`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      setAmountText(''); setNote(''); setHours(0);
      const target = recordDay(record.fed_at);
      if (target !== day) setDay(target); else load(day);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : '记录失败，请稍后重试');
    } finally { setBusy(false); }
  };

  const remove = async (id: number) => {
    setBusy(true); setMessage(null);
    try {
      await api.authorized(`/pets/${petId}/diet/${id}`, { method: 'DELETE' });
      load(day);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : '删除失败，请稍后重试');
    } finally { setBusy(false); }
  };

  const atToday = day >= localDate();
  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>饮食记录</Text>
      <View style={styles.dayNav}>
        <Pressable accessibilityRole="button" accessibilityLabel="前一天" style={styles.dayButton} onPress={() => setDay(shiftDay(day, -1))}>
          <Text style={styles.dayButtonText}>‹ 前一天</Text>
        </Pressable>
        <Text style={styles.dayLabel}>{dayLabel(day)} · {day}</Text>
        <Pressable accessibilityRole="button" accessibilityLabel="后一天" accessibilityState={{ disabled: atToday }}
          style={[styles.dayButton, atToday && styles.disabled]} onPress={() => { if (!atToday) setDay(shiftDay(day, 1)); }}>
          <Text style={styles.dayButtonText}>后一天 ›</Text>
        </Pressable>
      </View>
      {daily === null ? (
        loadFailed ? (
          <Pressable accessibilityRole="button" style={styles.primary} onPress={() => load(day)}><Text style={styles.primaryText}>重试</Text></Pressable>
        ) : <ActivityIndicator color={colors.brand} />
      ) : (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>当日合计</Text>
          <Text style={styles.total}>{daily.total_g}g · {daily.total_kcal} kcal · {daily.count} 笔</Text>
          <Text style={styles.subtitle}>热量仅按干粮/湿粮标准密度估算，零食与其他不计入。</Text>
          {daily.items.length === 0 ? <Text style={styles.subtitle}>这一天还没有饮食记录。</Text> : daily.items.map(item => (
            <View key={item.id} style={styles.record}>
              <View style={styles.recordText}>
                <Text style={styles.recordTitle}>{FOOD_LABELS[item.food_type] ?? item.food_type} {item.amount_g}g{item.kcal_est !== null ? ` · ${item.kcal_est} kcal` : ''}</Text>
                <Text style={styles.subtitle}>{formatClock(item.fed_at)}{item.food_name ? ` · ${item.food_name}` : ''}{item.note ? ` · ${item.note}` : ''}</Text>
              </View>
              <Pressable accessibilityRole="button" accessibilityLabel={`删除 ${FOOD_LABELS[item.food_type] ?? item.food_type} ${item.amount_g}克记录`}
                style={styles.delete} onPress={() => remove(item.id)} disabled={busy}>
                <Text style={styles.deleteText}>删除</Text>
              </Pressable>
            </View>
          ))}
        </View>
      )}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>快速记一笔</Text>
        <View style={styles.chips}>
          {FOOD_TYPES.map(type => (
            <Pressable key={type} accessibilityRole="button" accessibilityState={{ selected: foodType === type }}
              style={[styles.chip, foodType === type && styles.activeChip]} onPress={() => setFoodType(type)}>
              <Text style={styles.chipText}>{FOOD_LABELS[type]}</Text>
            </Pressable>
          ))}
        </View>
        <TextInput style={styles.input} value={amountText} onChangeText={setAmountText} keyboardType="decimal-pad"
          placeholder="克数，如 50" placeholderTextColor={colors.secondary} accessibilityLabel="喂食克数" maxLength={7} />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
          {BACKDATE_OPTIONS.map(option => (
            <Pressable key={option.hours} accessibilityRole="button" accessibilityState={{ selected: hours === option.hours }}
              style={[styles.chip, hours === option.hours && styles.activeChip]} onPress={() => setHours(option.hours)}>
              <Text style={styles.chipText}>{option.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
        <TextInput style={styles.input} value={note} onChangeText={setNote} placeholder="备注（可选，如 换了新粮）"
          placeholderTextColor={colors.secondary} accessibilityLabel="备注" maxLength={255} />
        <Pressable accessibilityRole="button" style={[styles.primary, busy && styles.disabled]} onPress={submit} disabled={busy}>
          <Text style={styles.primaryText}>{busy ? '记录中…' : '记一笔'}</Text>
        </Pressable>
        {message ? <Text accessibilityLiveRegion="polite" style={styles.message}>{message}</Text> : null}
      </View>
      <Link href={`/feeding/${petId}`} style={styles.link}>查看喂养参考（RER/DER）</Link>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  subtitle: { fontSize: 12, lineHeight: 18, color: colors.secondary, marginTop: 2 },
  dayNav: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  dayButton: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 10, borderRadius: 12, backgroundColor: colors.surface },
  dayButtonText: { fontSize: 13, fontWeight: '600', color: colors.text },
  dayLabel: { fontSize: 14, fontWeight: '700', color: colors.text },
  disabled: { opacity: 0.45 },
  card: { padding: 16, borderRadius: 18, backgroundColor: colors.surface, gap: 8 },
  cardTitle: { fontSize: 15, fontWeight: '600', color: colors.text },
  total: { fontSize: 20, fontWeight: '700', color: colors.text },
  record: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: colors.border },
  recordText: { flex: 1 },
  recordTitle: { fontSize: 14, fontWeight: '600', color: colors.text },
  delete: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 10 },
  deleteText: { fontSize: 13, color: '#B3261E', textDecorationLine: 'underline' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 14, borderRadius: 12, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border },
  activeChip: { backgroundColor: colors.soft, borderColor: colors.brand },
  chipText: { fontSize: 13, fontWeight: '600', color: colors.text },
  input: { minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, paddingHorizontal: 14, fontSize: 15, color: colors.text },
  primary: { minHeight: 48, borderRadius: 14, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: colors.onBrand, fontWeight: '700', fontSize: 15 },
  message: { fontSize: 13, color: '#B3261E' },
  link: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 18, borderRadius: 12, backgroundColor: colors.soft, color: colors.text, fontWeight: '600', overflow: 'hidden' },
});

// 体重录入与趋势（F08）：0.1–30kg 精度 0.01；同日多次全部保留；
// 录入后档案「最新体重」与喂养参考即时更新（AC-08-1）；7 天 ±10% 骤变提示跳初筛（AC-08-2）。
import { Link, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { TrendChart, type TrendPoint } from '../../components/TrendChart';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/health';
import { alertText, BACKDATE_OPTIONS, measuredAtFor, parseWeight, SCREENING_SUGGESTION, type WeightRecord, type WeightTrendAlert } from '../../lib/weight';
import { colors } from '../../theme';

interface WeightsResponse {
  records: WeightRecord[];
  count: number;
  trend: { window_days: number; points: TrendPoint[]; alert: WeightTrendAlert | null };
}

export default function WeightScreen() {
  const { petId } = useLocalSearchParams<{ petId: string }>();
  const [data, setData] = useState<WeightsResponse | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [weightText, setWeightText] = useState('');
  const [hours, setHours] = useState(0);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.authorized<WeightsResponse>(`/pets/${petId}/weights?limit=50`)
      .then(result => { setData(result); setLoadFailed(false); })
      .catch(() => setLoadFailed(true));
  }, [petId]);
  useEffect(() => { load(); }, [load]);
  const submit = useCallback(() => {
    const parsed = parseWeight(weightText);
    if (!parsed.ok) { setMessage(parsed.message); return; }
    setBusy(true);
    setMessage('');
    api.authorized<WeightRecord>(`/pets/${petId}/weights`, {
      method: 'POST',
      body: JSON.stringify({ weight_kg: parsed.value, measured_at: measuredAtFor(hours) }),
    }).then(() => {
      setWeightText('');
      setHours(0);
      setMessage('已记录，档案与喂养参考已同步更新。');
      load();
    }).catch(() => setMessage('保存失败，请重试。'))
      .finally(() => setBusy(false));
  }, [petId, weightText, hours, load]);
  const alert = data?.trend.alert ?? null;
  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>体重记录</Text>
      <Text style={styles.subtitle}>0.1–30kg，精度 0.01kg；同一天多次测量全部保留。</Text>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>记一笔</Text>
        <TextInput value={weightText} onChangeText={setWeightText} keyboardType="decimal-pad"
          placeholder="体重（kg），如 4.25" placeholderTextColor={colors.secondary}
          style={styles.input} accessibilityLabel="体重公斤数" />
        <View style={styles.chips}>
          {BACKDATE_OPTIONS.map(option => (
            <Pressable key={option.hours} accessibilityRole="button"
              accessibilityState={{ selected: hours === option.hours }}
              onPress={() => setHours(option.hours)}
              style={[styles.chip, hours === option.hours && styles.activeChip]}>
              <Text style={styles.chipText}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
        <Pressable accessibilityRole="button" style={[styles.primary, busy && styles.disabled]} onPress={submit} disabled={busy}>
          <Text style={styles.primaryText}>{busy ? '保存中…' : '记录'}</Text>
        </Pressable>
        {message ? <Text accessibilityLiveRegion="polite" style={styles.message}>{message}</Text> : null}
      </View>
      {alert ? (
        <View style={styles.alertCard}>
          <Text style={styles.alertTitle}>{alertText(alert)}</Text>
          <Text style={styles.subtitle}>{SCREENING_SUGGESTION}，排查潜在健康问题。</Text>
          <Link href={`/screening/${petId}`} style={styles.alertButton} accessibilityRole="button">去做初筛</Link>
        </View>
      ) : null}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>近 90 天趋势</Text>
        {data === null ? (
          loadFailed ? (
            <Pressable accessibilityRole="button" style={styles.primary} onPress={load}><Text style={styles.primaryText}>重试</Text></Pressable>
          ) : <ActivityIndicator color={colors.brand} />
        ) : <TrendChart points={data.trend.points} />}
      </View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>历史记录</Text>
        {data && data.records.length > 0 ? data.records.map(record => (
          <View key={record.id} style={styles.record}>
            <Text style={styles.recordValue}>{record.weight_kg} kg</Text>
            <Text style={styles.subtitle}>{formatDateTime(record.measured_at)}</Text>
          </View>
        )) : <Text style={styles.subtitle}>暂无记录。</Text>}
      </View>
      <Link href={`/feeding/${petId}`} style={styles.link} accessibilityRole="button">查看喂养参考（按最新体重计算）</Link>
      <Link href={`/timeline/${petId}`} style={styles.link} accessibilityRole="button">返回健康时间线</Link>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  subtitle: { fontSize: 13, lineHeight: 20, color: colors.secondary, marginTop: 4 },
  card: { padding: 20, borderRadius: 20, backgroundColor: colors.surface, gap: 10 },
  cardTitle: { fontSize: 15, fontWeight: '600', color: colors.text },
  input: { minHeight: 48, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 14, fontSize: 16, color: colors.text, backgroundColor: '#FFFFFF' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 36, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 10, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: colors.border },
  activeChip: { backgroundColor: colors.soft, borderColor: colors.brand },
  chipText: { fontSize: 13, color: colors.text },
  primary: { minHeight: 48, borderRadius: 14, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  disabled: { opacity: 0.6 },
  primaryText: { color: colors.onBrand, fontWeight: '700', fontSize: 15 },
  message: { fontSize: 13, lineHeight: 20, color: colors.text },
  alertCard: { padding: 20, borderRadius: 20, backgroundColor: '#FDECEA', borderWidth: 1, borderColor: '#C0392B', gap: 6 },
  alertTitle: { fontSize: 16, fontWeight: '700', color: '#C0392B' },
  alertButton: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 18, borderRadius: 12, backgroundColor: '#C0392B', color: '#FFFFFF', fontWeight: '700', overflow: 'hidden', marginTop: 4 },
  record: { paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.border },
  recordValue: { fontSize: 16, fontWeight: '700', color: colors.text },
  link: { minHeight: 44, justifyContent: 'center', color: colors.text, fontWeight: '600', textDecorationLine: 'underline' },
});

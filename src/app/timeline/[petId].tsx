import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { STATE_LABELS, stateTone } from '../../lib/screening';
import { formatClock, groupByLocalDay, screeningTimeline, type DayGroup } from '../../lib/timeline';
import { colors } from '../../theme';

const TONE_COLORS = { ok: '#2E7D32', watch: '#B26A00', vet: '#B26A00', urgent: '#B3261E' } as const;

export default function TimelineScreen() {
  const { petId } = useLocalSearchParams<{ petId: string }>();
  const router = useRouter();
  const [groups, setGroups] = useState<DayGroup[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const load = useCallback(() => {
    // T11 仅初筛记录；饮食（T12）与体重（T13）交付后在此混排。
    api.authorized<{ items: { screening_id: number; state: string; redline_hit: boolean; created_at: string }[] }>(`/pets/${petId}/screenings?limit=50`)
      .then(result => { setGroups(groupByLocalDay(screeningTimeline(result.items), new Date())); setLoadFailed(false); })
      .catch(() => setLoadFailed(true));
  }, [petId]);
  useEffect(() => { load(); }, [load]);
  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>健康时间线</Text>
      <Text style={styles.subtitle}>初筛记录按日倒序；饮食与体重记录将在后续版本加入。</Text>
      {groups === null ? (
        loadFailed ? (
          <Pressable accessibilityRole="button" style={styles.primary} onPress={load}><Text style={styles.primaryText}>重试</Text></Pressable>
        ) : <ActivityIndicator color={colors.brand} />
      ) : groups.length === 0 ? (
        <Text style={styles.subtitle}>暂无健康记录，先做一次初筛吧。</Text>
      ) : groups.map(group => (
        <View key={group.day} style={styles.dayBlock}>
          <Text style={styles.dayLabel}>{group.label}</Text>
          {group.items.map(item => item.kind === 'screening' ? (
            <Pressable key={`s-${item.id}`} accessibilityRole="button" style={styles.card} onPress={() => router.push(item.route)}>
              <View style={styles.row}>
                <Text style={[styles.state, { color: TONE_COLORS[stateTone(item.state)] }]}>{STATE_LABELS[item.state] ?? item.state}</Text>
                <Text style={styles.clock}>{formatClock(item.createdAt)}</Text>
              </View>
              <Text style={styles.subtitle}>初筛{item.redlineHit ? ' · 命中紧急信号' : ''} · 点击查看完整结果</Text>
            </Pressable>
          ) : (
            <Pressable key={`${item.kind}-${item.id}`} accessibilityRole="button" style={styles.card} onPress={() => router.push(item.route)}>
              <Text style={styles.state}>{item.kind === 'diet' ? '饮食' : '体重'} · {item.title}</Text>
              <Text style={styles.clock}>{formatClock(item.createdAt)}</Text>
            </Pressable>
          ))}
        </View>
      ))}
      <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => router.back()}>
        <Text style={styles.secondaryText}>返回</Text>
      </Pressable>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  subtitle: { fontSize: 13, lineHeight: 20, color: colors.secondary, marginTop: 4 },
  dayBlock: { gap: 8 },
  dayLabel: { fontSize: 14, fontWeight: '700', color: colors.text, marginTop: 8 },
  card: { padding: 16, borderRadius: 18, backgroundColor: colors.surface, gap: 4 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  state: { fontSize: 16, fontWeight: '700' },
  clock: { fontSize: 13, color: colors.secondary },
  primary: { minHeight: 48, borderRadius: 14, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: colors.onBrand, fontWeight: '700', fontSize: 15 },
  secondary: { minHeight: 44, borderRadius: 12, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { color: colors.text, fontWeight: '600', fontSize: 14 },
});

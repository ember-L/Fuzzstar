import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import { Screen } from '../../../components/Screen';
import { api } from '../../../lib/api';
import { STATE_LABELS, stateTone } from '../../../lib/screening';
import { colors } from '../../../theme';

interface HistoryItem { screening_id: number; state: string; redline_hit: boolean; created_at: string }
const TONE_COLORS = { ok: '#2E7D32', watch: '#B26A00', vet: '#B26A00', urgent: '#B3261E' } as const;

function formatTime(iso: string) {
  const value = /Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`;
  return new Date(value).toLocaleString();
}

export default function ScreeningHistoryScreen() {
  const { petId } = useLocalSearchParams<{ petId: string }>();
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const load = useCallback(() => {
    api.authorized<{ items: HistoryItem[] }>(`/pets/${petId}/screenings`).then(result => { setItems(result.items); setLoadFailed(false); }).catch(() => setLoadFailed(true));
  }, [petId]);
  useEffect(() => { load(); }, [load]);
  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>初筛历史</Text>
      {items === null ? (
        loadFailed ? (
          <Pressable accessibilityRole="button" style={styles.primary} onPress={load}><Text style={styles.primaryText}>重试</Text></Pressable>
        ) : <ActivityIndicator color={colors.brand} />
      ) : items.length === 0 ? (
        <Text style={styles.subtitle}>暂无初筛记录。</Text>
      ) : items.map(item => (
        <Pressable key={item.screening_id} accessibilityRole="button" style={styles.card}
          onPress={() => router.push(`/screening/result/${item.screening_id}`)}>
          <Text style={[styles.state, { color: TONE_COLORS[stateTone(item.state)] }]}>{STATE_LABELS[item.state] ?? item.state}</Text>
          <Text style={styles.subtitle}>{formatTime(item.created_at)}{item.redline_hit ? ' · 命中紧急信号' : ''}</Text>
        </Pressable>
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
  card: { padding: 16, borderRadius: 18, backgroundColor: colors.surface, gap: 4 },
  state: { fontSize: 16, fontWeight: '700' },
  primary: { minHeight: 48, borderRadius: 14, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: colors.onBrand, fontWeight: '700', fontSize: 15 },
  secondary: { minHeight: 44, borderRadius: 12, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { color: colors.text, fontWeight: '600', fontSize: 14 },
});

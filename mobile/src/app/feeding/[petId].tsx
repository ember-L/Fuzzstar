import { Link, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { colors } from '../../theme';

const STAGE_LABELS: Record<string, string> = {
  kitten_under_4m: '幼猫（<4 月龄）',
  kitten_4_12m: '幼猫（4–12 月龄）',
  adult_neutered: '成年 · 已绝育',
  adult_intact: '成年 · 未绝育',
  senior: '老年（≥11 岁）',
};

interface Reference {
  has_weight: boolean;
  guidance?: string;
  disclaimer: string;
  weight_kg?: number;
  measured_at?: string;
  life_stage?: string;
  coefficient?: number;
  rer_kcal?: number;
  der_kcal?: number;
  dry_g?: number;
  wet_g?: number;
  dry_g_range?: [number, number];
  wet_g_range?: [number, number];
}

export default function FeedingScreen() {
  const { petId } = useLocalSearchParams<{ petId: string }>();
  const [reference, setReference] = useState<Reference | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const load = useCallback(() => {
    api.authorized<Reference>(`/pets/${petId}/feeding-reference`)
      .then(data => { setReference(data); setLoadFailed(false); })
      .catch(() => setLoadFailed(true));
  }, [petId]);
  useEffect(() => { load(); }, [load]);
  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>喂养参考</Text>
      <Text style={styles.subtitle}>按公开营养学公式（RER/DER）换算，随最新体重与档案更新。</Text>
      {reference === null ? (
        loadFailed ? (
          <Pressable accessibilityRole="button" style={styles.primary} onPress={load}><Text style={styles.primaryText}>重试</Text></Pressable>
        ) : <ActivityIndicator color={colors.brand} />
      ) : !reference.has_weight ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>先记录体重</Text>
          <Text style={styles.body}>{reference.guidance}</Text>
        </View>
      ) : (
        <>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>计算依据</Text>
            <Text style={styles.body}>最新体重 {reference.weight_kg} kg{reference.measured_at ? `（${reference.measured_at.slice(0, 10)} 测量）` : ''}</Text>
            <Text style={styles.body}>生命阶段：{STAGE_LABELS[reference.life_stage ?? ''] ?? reference.life_stage} · 系数 ×{reference.coefficient}</Text>
            <Text style={styles.body}>静息能量 RER：{reference.rer_kcal} kcal/日</Text>
            <Text style={styles.total}>每日能量参考 DER：{reference.der_kcal} kcal</Text>
          </View>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>换算喂食量（±10% 区间）</Text>
            <Text style={styles.body}>干粮：{reference.dry_g_range?.[0]}–{reference.dry_g_range?.[1]} g/日（中心 {reference.dry_g} g）</Text>
            <Text style={styles.body}>湿粮：{reference.wet_g_range?.[0]}–{reference.wet_g_range?.[1]} g/日（中心 {reference.wet_g} g）</Text>
            <Text style={styles.subtitle}>干粮按 3.8 kcal/g、湿粮按 0.9 kcal/g 标准密度估算；实际请按粮食包装代谢能调整。</Text>
          </View>
        </>
      )}
      {reference ? <Text style={styles.disclaimer}>{reference.disclaimer}</Text> : null}
      <Link href={`/diet/${petId}`} style={styles.link}>返回饮食记录</Link>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  subtitle: { fontSize: 12, lineHeight: 18, color: colors.secondary, marginTop: 2 },
  card: { padding: 16, borderRadius: 18, backgroundColor: colors.surface, gap: 6 },
  cardTitle: { fontSize: 15, fontWeight: '600', color: colors.text },
  body: { fontSize: 14, lineHeight: 22, color: colors.text },
  total: { fontSize: 19, fontWeight: '700', color: colors.text, marginTop: 4 },
  disclaimer: { fontSize: 12, lineHeight: 18, color: colors.secondary, fontStyle: 'italic' },
  primary: { minHeight: 48, borderRadius: 14, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: colors.onBrand, fontWeight: '700', fontSize: 15 },
  link: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 18, borderRadius: 12, backgroundColor: colors.soft, color: colors.text, fontWeight: '600', overflow: 'hidden' },
});

import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { AvatarStage, type Submission } from '../../components/AvatarStage';
import { PhotoUpload } from '../../components/PhotoUpload';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { formatDateTime, isUrgent, scoreDisplay, stateLabel, totalEffective, type HealthSummary } from '../../lib/health';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

const STATE_COLORS: Record<string, string> = {
  normal: '#3D9A50', observe: '#C77E1F', vet: '#D05A28', urgent: '#C0392B',
};
const STATE_HINTS: Record<string, string> = {
  normal: '状态良好，继续保持。',
  observe: '建议观察精神与食欲变化，按时复查。',
  vet: '建议尽快安排就医检查。',
};

export default function HomeScreen() {
  const [pets, setPets] = useState<{ id: number; name: string }[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [loadError, setLoadError] = useState(false);
  const [submission, setSubmission] = useState<(Submission & { petId: number }) | undefined>();
  const [health, setHealth] = useState<HealthSummary | null>(null);
  const [showDeductions, setShowDeductions] = useState(false);
  const selected = pets.find(pet => pet.id === selectedId) ?? pets[0];
  useFocusEffect(useCallback(() => {
    let active = true;
    api.authorized<{ id: number; name: string }[]>('/pets').then(items => {
      if (active) { setPets(items); setLoadError(false); }
    }).catch(error => {
      if (active) {
        setPets([]);
        setLoadError(!(error instanceof ApiError && (error.status === 401 || error.status === 403)));
      }
    });
    return () => { active = false; setPets([]); setLoadError(false); };
  }, []));
  // 健康聚合随焦点与切猫重拉（AC-02-4 / AC-04-1 刷新一致性）。
  const selectedPetId = selected?.id;
  useFocusEffect(useCallback(() => {
    setShowDeductions(false);
    if (!selectedPetId) { setHealth(null); return; }
    let active = true;
    api.authorized<HealthSummary>('/pets/' + selectedPetId + '/health')
      .then(data => { if (active) setHealth(data); })
      .catch(() => { if (active) setHealth(null); });
    return () => { active = false; };
  }, [selectedPetId]));
  const urgent = health !== null && isUrgent(health.state);
  const stateColor = health ? STATE_COLORS[health.state] ?? colors.text : colors.text;
  const hint = health
    ? (urgent && health.urgent_card ? health.urgent_card.subtitle : STATE_HINTS[health.state] ?? '')
    : (selected ? '尚无健康评估记录。' : '创建猫咪档案后，可以查看健康状态。');
  return (
    <Screen>
      <View>
        <Text accessibilityRole="header" style={styles.title}>你好，欢迎来到绒星</Text>
        <Text style={styles.subtitle}>星光护绒，健康相伴</Text>
      </View>
      {pets.length > 0 ? (
        <View style={styles.selector}>
          {pets.map(pet => (
            <Pressable key={pet.id} accessibilityRole="button" accessibilityState={{ selected: selected?.id === pet.id }}
              onPress={() => setSelectedId(pet.id)} style={[styles.pet, selected?.id === pet.id && styles.activePet]}>
              <Text style={styles.cardTitle}>{selected?.id === pet.id ? '✓ ' : ''}{pet.name}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      <View style={styles.hero}>
        <View style={styles.heroText}>
          <Text style={styles.heroTitle}>用爱守护{ '\n' }它的每一天</Text>
          <Text style={styles.subtitle}>健康的陪伴{ '\n' }从点滴开始</Text>
        </View>
        {selected ? (
          <AvatarStage key={selected.id} pet={selected}
            health={health ? { state: health.state } : null}
            submission={submission?.petId === selected.id ? submission : undefined} />
        ) : (
          <Image source={require('../../../assets/figma/59f10c90466cfa3aa84c0f88478dccedc8f69565.png')} style={styles.cat} accessibilityLabel="绒星猫咪示意图" />
        )}
      </View>
      <View style={[styles.card, urgent && styles.urgentCard]}>
        <Text style={styles.cardTitle}>{selected ? selected.name + '的健康状态' : '健康状态'}</Text>
        <Text style={[styles.status, { color: stateColor }]}>
          {health ? stateLabel(health.state) + ' · ' + scoreDisplay(health.score) : '未评估  --'}
        </Text>
        <Text style={styles.subtitle}>{hint}</Text>
        {urgent && selected ? (
          <Link href={'/screening/' + selected.id} style={styles.vetButton} accessibilityRole="button">立即就医</Link>
        ) : null}
        {health && health.deductions.length > 0 ? (
          <Pressable onPress={() => setShowDeductions(value => !value)} accessibilityRole="button" style={styles.detailToggle}>
            <Text style={styles.detailToggleText}>
              {showDeductions ? '收起扣分明细' : '扣分明细（生效 −' + totalEffective(health.deductions) + ' 分）'}
            </Text>
          </Pressable>
        ) : null}
        {showDeductions && health ? health.deductions.map(item => (
          <View key={item.id} style={styles.deduction}>
            <Text style={styles.deductionTitle}>
              {(item.symptoms.length > 0 ? item.symptoms.join('、') : stateLabel(item.severity)) + '：−' + item.score_delta + ' 分'}
              {item.decayed ? ' · 已衰减，计 0' : ''}
            </Text>
            <Text style={styles.subtitle}>{formatDateTime(item.created_at) + ' 生效 · 规则 ' + (item.rules_version ?? '—')}</Text>
          </View>
        )) : null}
      </View>
      <Text accessibilityRole="header" style={styles.section}>今日概览</Text>
      <View style={styles.row}>
        <View style={styles.summary}>
          <Text style={styles.summaryTitle}>今日饮食</Text>
          <Text style={styles.subtitle}>暂无记录</Text>
        </View>
        <View style={styles.summary}>
          <Text style={styles.summaryTitle}>最新体重</Text>
          <Text style={styles.subtitle}>暂无记录</Text>
        </View>
        {selected ? (
          <Link href={'/screening/history/' + selected.id} style={styles.summary}>
            <Text style={styles.summaryTitle}>最近初筛</Text>
            <Text style={styles.subtitle}>
              {health?.latest_screening ? formatDateTime(health.latest_screening.created_at) : '暂无记录'}
            </Text>
          </Link>
        ) : (
          <View style={styles.summary}>
            <Text style={styles.summaryTitle}>最近初筛</Text>
            <Text style={styles.subtitle}>暂无记录</Text>
          </View>
        )}
      </View>
      {selected ? <Link href="/chat" style={styles.chatLink}>和我聊聊</Link> : null}
      {selected ? <PhotoUpload key={selected.id} pet={selected}
        onSubmitted={next => setSubmission({ petId: selected.id, ...next })} /> : null}
      {loadError ? <Text accessibilityLiveRegion="polite" style={styles.note}>暂时无法加载猫咪档案。</Text> : null}
      {!selected ? <Link href="/profile" style={styles.profileLink}>前往「我的」管理猫咪档案</Link> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  subtitle: { fontSize: 13, lineHeight: 20, color: colors.secondary, marginTop: 6 },
  hero: { minHeight: 195, borderRadius: 22, backgroundColor: '#FFEDD7', flexDirection: 'row', overflow: 'hidden' },
  heroText: { flex: 1, justifyContent: 'center', paddingLeft: 20, zIndex: 1 },
  heroTitle: { fontSize: 21, lineHeight: 30, fontWeight: '700', color: colors.text, marginBottom: 12 },
  cat: { width: '47%', maxWidth: 165, height: 195, alignSelf: 'flex-end', resizeMode: 'contain' },
  card: { padding: 20, borderRadius: 20, backgroundColor: colors.surface, gap: 5 },
  urgentCard: { backgroundColor: '#FDECEA', borderWidth: 1, borderColor: '#C0392B' },
  cardTitle: { fontSize: 15, fontWeight: '600', color: colors.text },
  status: { fontSize: 23, fontWeight: '700', color: colors.text },
  vetButton: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 18, borderRadius: 12, backgroundColor: '#C0392B', color: '#FFFFFF', fontWeight: '700', overflow: 'hidden', marginTop: 6 },
  detailToggle: { minHeight: 44, justifyContent: 'center' },
  detailToggleText: { fontSize: 13, fontWeight: '600', color: colors.text, textDecorationLine: 'underline' },
  deduction: { paddingTop: 8, borderTopWidth: 1, borderTopColor: colors.border },
  deductionTitle: { fontSize: 13, fontWeight: '600', color: colors.text },
  section: { fontSize: 18, fontWeight: '700', color: colors.text, marginTop: 2 },
  row: { flexDirection: 'row', gap: 10 },
  summary: { flex: 1, minHeight: 92, padding: 12, alignItems: 'center', justifyContent: 'center', borderRadius: 16, backgroundColor: colors.surface },
  summaryTitle: { fontSize: 12, fontWeight: '600', color: colors.text },
  chatLink: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 18, borderRadius: 12, backgroundColor: colors.soft, color: colors.text, fontWeight: '600', overflow: 'hidden' },
  selector: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  pet: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.surface },
  activePet: { backgroundColor: colors.soft },
  profileLink: { minHeight: 44, color: colors.text, textDecorationLine: 'underline', paddingVertical: 12 },
  note: { color: colors.secondary, fontSize: 13, lineHeight: 20 },
});

import { Link, useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { AvatarStage, type Submission } from '../../components/AvatarStage';
import { GifExport } from '../../components/GifExport';
import { PhotoUpload } from '../../components/PhotoUpload';
import { Screen } from '../../components/Screen';
import { Icon } from '../../components/ui/Icon';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { api } from '../../lib/api';
import { emotionBus } from '../../lib/chat-emotion';
import { tzOffsetMinutes } from '../../lib/diet';
import { formatDateTime, isUrgent, stateLabel, totalEffective, type HealthSummary } from '../../lib/health';
import { canUse, type QuotaSnapshot } from '../../lib/quota';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

// 健康状态→语义色（v2 Foundations：success/warning/danger）
const STATE_STYLE: Record<string, { bg: string; fg: string }> = {
  normal: { bg: colors.successBg, fg: colors.success },
  observe: { bg: colors.warningBg, fg: colors.warning },
  vet: { bg: colors.dangerBg, fg: colors.danger },
  urgent: { bg: colors.dangerBg, fg: colors.danger },
};
const STATE_HINTS: Record<string, string> = {
  normal: '状态良好，继续保持。',
  observe: '建议观察精神与食欲变化，按时复查。',
  vet: '建议尽快安排就医检查。',
};

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 11) return '早上好';
  if (hour < 18) return '下午好';
  return '晚上好';
}

export default function HomeScreen() {
  const router = useRouter();
  const [pets, setPets] = useState<{ id: number; name: string }[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [loadError, setLoadError] = useState(false);
  const [submission, setSubmission] = useState<(Submission & { petId: number }) | undefined>();
  const [health, setHealth] = useState<HealthSummary | null>(null);
  const [showDeductions, setShowDeductions] = useState(false);
  const [emotionEvent, setEmotionEvent] = useState<{ id: string; petId: number; emotion: string } | null>(null);
  const [quota, setQuota] = useState<QuotaSnapshot>();
  // F09-5：聊聊页回复情绪→仅当前选中猫的分身播一次对应动作后回待机。
  useEffect(() => emotionBus.subscribe(event => setEmotionEvent({ id: String(event.id), petId: event.petId, emotion: event.emotion })), []);
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
    api.authorized<QuotaSnapshot>('/quota').then(snapshot => { if (active) setQuota(snapshot); }).catch(() => {});
    return () => { active = false; setPets([]); setLoadError(false); };
  }, []));
  // 健康聚合随焦点与切猫重拉（AC-02-4 / AC-04-1 刷新一致性）。
  const selectedPetId = selected?.id;
  useFocusEffect(useCallback(() => {
    setShowDeductions(false);
    if (!selectedPetId) { setHealth(null); return; }
    let active = true;
    api.authorized<HealthSummary>('/pets/' + selectedPetId + '/health?tz_offset_minutes=' + tzOffsetMinutes())
      .then(data => { if (active) setHealth(data); })
      .catch(() => { if (active) setHealth(null); });
    return () => { active = false; };
  }, [selectedPetId]));
  const urgent = health !== null && isUrgent(health.state);
  const stateStyle = health ? STATE_STYLE[health.state] ?? { bg: colors.neutralPillBg, fg: colors.disabledText } : { bg: colors.neutralPillBg, fg: colors.disabledText };
  const hint = health
    ? (urgent && health.urgent_card ? health.urgent_card.subtitle : STATE_HINTS[health.state] ?? '')
    : (selected ? `还没有为${selected.name}做过初筛，花 1 分钟了解它的状态` : '创建猫咪档案后，可以查看健康状态。');
  const cyclePet = () => {
    if (pets.length < 2 || !selected) return;
    const index = pets.findIndex(pet => pet.id === selected.id);
    setSelectedId(pets[(index + 1) % pets.length].id);
  };
  return (
    <Screen>
      {/* 问候＋切换猫咪（画板 22:309 头部） */}
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text accessibilityRole="header" style={styles.greeting}>{greeting()}</Text>
          <Text style={styles.subtitle}>{selected ? `${selected.name}今天也需要你的留意` : '星光护绒，健康相伴'}</Text>
        </View>
        {selected ? (
          <View style={styles.headerPet}>
            <Image source={require('../../../assets/figma/cat-avatar.png')} style={styles.headerAvatar} accessibilityLabel={`${selected.name}的头像`} />
            <Pressable accessibilityRole="button" accessibilityLabel="切换猫咪" onPress={cyclePet} style={styles.switchPill}>
              <Text style={styles.switchText} numberOfLines={1}>{selected.name} ⌄</Text>
            </Pressable>
          </View>
        ) : null}
      </View>
      {pets.length > 1 ? (
        <View style={styles.selector}>
          {pets.map(pet => (
            <Pressable key={pet.id} accessibilityRole="button" accessibilityState={{ selected: selected?.id === pet.id }}
              onPress={() => setSelectedId(pet.id)} style={[styles.pet, selected?.id === pet.id && styles.activePet]}>
              <Text style={styles.petText}>{pet.name}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      {loadError ? <Text style={styles.note}>猫咪列表加载失败，请稍后重试。</Text> : null}
      {selected ? (
        <>
          {/* 品牌插画位：左文案＋右分身舞台（无分身时静态底图兜底，即画板视觉） */}
          <View style={styles.hero}>
            <Text style={styles.sparkle}>✦</Text>
            <View style={styles.heroText}>
              <Text style={styles.heroTitle}>{'用爱守护\n它的每一天'}</Text>
              <Text style={styles.heroSubtitle}>{'健康的陪伴\n从点滴开始'}</Text>
              <Text style={styles.heroTag}>·  陪伴每一天</Text>
            </View>
            <AvatarStage key={selected.id} pet={selected}
              submission={submission?.petId === selected.id ? submission : undefined}
              health={health ? { state: health.state } : null}
              emotionEvent={emotionEvent?.petId === selected.id ? { id: emotionEvent.id, emotion: emotionEvent.emotion } : null} />
          </View>
          {/* 健康状态卡片 */}
          <View style={[styles.healthCard, urgent && styles.healthCardUrgent]}>
            <Text style={styles.healthLabel}>健康状态</Text>
            <View style={styles.healthRow}>
              <Text style={[styles.score, urgent && { color: colors.danger }]}>{health && health.score !== null ? String(health.score) : '——'}</Text>
              <View style={[styles.statePill, { backgroundColor: stateStyle.bg }]}>
                <Text style={[styles.statePillText, { color: stateStyle.fg }]}>{health ? stateLabel(health.state) : '未评估'}</Text>
              </View>
            </View>
            <Text style={styles.healthHint}>{hint}</Text>
            {health && health.deductions.length > 0 ? (
              <View style={styles.deductions}>
                <Pressable accessibilityRole="button" onPress={() => setShowDeductions(value => !value)}>
                  <Text style={styles.deductionToggle}>{showDeductions ? '收起扣分明细 ▴' : `扣分明细（${health.deductions.length} 项）▾`}</Text>
                </Pressable>
                {showDeductions ? health.deductions.map(item => (
                  <View key={item.id} style={styles.deductionItem}>
                    <Text style={styles.deductionLine}>
                      {(item.symptoms.length > 0 ? item.symptoms.join('、') : stateLabel(item.severity)) + '：−' + item.score_delta + ' 分'}
                      {item.decayed ? ' · 已衰减，计 0' : ''}
                    </Text>
                    <Text style={styles.deductionMeta}>{formatDateTime(item.created_at) + ' 生效 · 规则 ' + (item.rules_version ?? '—')}</Text>
                  </View>
                )) : null}
                {showDeductions ? <Text style={styles.deductionTotal}>当前有效扣分合计：{totalEffective(health.deductions)} 分</Text> : null}
              </View>
            ) : null}
            {urgent && health?.urgent_card ? (
              <Link href={`/screening/${selected.id}`} accessibilityRole="button" style={styles.urgentLink}>
                <Text style={styles.urgentLinkText}>{health.urgent_card.title} ›</Text>
              </Link>
            ) : null}
            {!urgent ? (
              <Link href={`/screening/${selected.id}`} accessibilityRole="button" style={styles.ctaLink}>
                <Text style={styles.ctaLinkText}>{health?.latest_screening ? '再做一次初筛' : '开始健康初筛'}</Text>
              </Link>
            ) : null}
          </View>
          {/* 今日概览 */}
          <SectionHeader title="今日概览" actionLabel="查看全部  ›" onAction={() => router.push(`/timeline/${selected.id}`)} />
          <View style={styles.tiles}>
            <Link href={`/diet/${selected.id}`} accessibilityRole="button" style={styles.tile}>
              <Icon name="food" size={22} color={colors.mutedIcon} />
              <Text style={styles.tileLabel}>今日饮食</Text>
              <Text style={styles.tileValue}>{health?.diet_today && health.diet_today.count > 0 ? `${health.diet_today.total_g}g · ${health.diet_today.total_kcal}kcal` : '暂无记录'}</Text>
            </Link>
            <Link href={`/weight/${selected.id}`} accessibilityRole="button" style={styles.tile}>
              <Icon name="scale" size={22} color={colors.mutedIcon} />
              <Text style={styles.tileLabel}>最新体重</Text>
              <Text style={styles.tileValue}>{health?.latest_weight ? `${health.latest_weight.weight_kg} kg` : '暂无记录'}</Text>
            </Link>
            <Link href={`/screening/history/${selected.id}`} accessibilityRole="button" style={styles.tile}>
              <Icon name="file" size={22} color={colors.mutedIcon} />
              <Text style={styles.tileLabel}>最近初筛</Text>
              <Text style={styles.tileValue}>{health?.latest_screening ? stateLabel(health.latest_screening.state) : '暂无记录'}</Text>
            </Link>
          </View>
          {/* 快捷操作 */}
          <SectionHeader title="快捷操作" />
          <View style={styles.tiles}>
            <Link href={`/diet/${selected.id}`} accessibilityRole="button" style={styles.quick}>
              <Icon name="food" size={17} color={colors.text} />
              <Text style={styles.quickLabel}>记录饮食</Text>
            </Link>
            <Link href={`/weight/${selected.id}`} accessibilityRole="button" style={styles.quick}>
              <Icon name="scale" size={17} color={colors.text} />
              <Text style={styles.quickLabel}>记录体重</Text>
            </Link>
            <Link href="/(tabs)/chat" accessibilityRole="button" style={[styles.quick, styles.quickChat]}>
              <Icon name="chat" size={17} color={colors.accent} />
              <Text style={[styles.quickLabel, { color: colors.accent }]}>和我聊聊</Text>
            </Link>
          </View>
          {/* 分身上传与 GIF 分享（设计稿未覆盖的功能区，沿用既有组件） */}
          <SectionHeader title="分身与分享" />
          <PhotoUpload key={selected.id} pet={selected} quotaExhausted={!canUse(quota, 'avatar_gen')}
            onSubmitted={next => setSubmission({ petId: selected.id, ...next })} />
          <GifExport key={`gif-${selected.id}`} pet={selected} />
          <Link href={`/timeline/${selected.id}`} style={styles.profileLink}>健康时间线（初筛 · 饮食 · 体重）</Link>
        </>
      ) : (
        <View style={styles.empty}>
          <Text style={styles.note}>{loadError ? '暂时无法读取猫咪档案。' : '还没有猫咪档案。创建第一只猫咪后，这里会显示它的健康状态。'}</Text>
          <Link href="/(tabs)/profile" style={styles.profileLink}>前往「我的」创建档案</Link>
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  headerText: { flex: 1, gap: 2 },
  greeting: { fontSize: 25, lineHeight: 35, fontWeight: '600', color: colors.onBrand },
  subtitle: { fontSize: 13, color: colors.secondary },
  headerPet: { alignItems: 'center', gap: 4 },
  headerAvatar: { width: 40, height: 40, borderRadius: 20 },
  switchPill: { height: 31, borderRadius: 16, backgroundColor: colors.brandSoft, paddingHorizontal: 10, alignItems: 'center', justifyContent: 'center', maxWidth: 96 },
  switchText: { fontSize: 12, fontWeight: '500', color: colors.text },
  selector: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  pet: { minHeight: 36, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.surfaceRaised },
  activePet: { backgroundColor: colors.brandSoft },
  petText: { color: colors.text, fontWeight: '600', fontSize: 13 },
  hero: { flexDirection: 'row', backgroundColor: colors.heroBg, borderRadius: 22, padding: 16, minHeight: 195, overflow: 'hidden' },
  sparkle: { position: 'absolute', top: 28, right: 14, fontSize: 17, color: colors.sparkle, zIndex: 1 },
  heroText: { flex: 1, justifyContent: 'center', gap: 10, paddingVertical: 8 },
  heroTitle: { fontSize: 20, lineHeight: 28, fontWeight: '600', color: colors.text },
  heroSubtitle: { fontSize: 13, lineHeight: 18, color: colors.secondary },
  heroTag: { fontSize: 11, fontWeight: '500', color: colors.accent, marginTop: 12 },
  healthCard: { backgroundColor: colors.surfaceRaised, borderRadius: 20, padding: 16, gap: 8 },
  healthCardUrgent: { backgroundColor: colors.dangerBg },
  healthLabel: { fontSize: 15, fontWeight: '600', color: colors.text },
  healthRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  score: { fontSize: 25, lineHeight: 35, fontWeight: '600', color: colors.text },
  statePill: { height: 26, borderRadius: 13, paddingHorizontal: 12, alignItems: 'center', justifyContent: 'center' },
  statePillText: { fontSize: 12, fontWeight: '500' },
  healthHint: { fontSize: 12, lineHeight: 17, color: colors.secondary },
  deductions: { gap: 4 },
  deductionToggle: { color: colors.accent, fontWeight: '600', fontSize: 12 },
  deductionItem: { gap: 1 },
  deductionLine: { color: colors.text, fontSize: 11, lineHeight: 16 },
  deductionMeta: { color: colors.secondary, fontSize: 10, lineHeight: 14 },
  deductionTotal: { color: colors.text, fontSize: 11, fontWeight: '600' },
  ctaLink: { height: 48, borderRadius: 24, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  ctaLinkText: { fontSize: 16, fontWeight: '600', color: colors.onBrand },
  urgentLink: { height: 48, borderRadius: 24, backgroundColor: colors.danger, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  urgentLinkText: { fontSize: 16, fontWeight: '600', color: '#FFFFFF' },
  tiles: { flexDirection: 'row', gap: 12 },
  tile: { flex: 1, minHeight: 94, borderRadius: 16, backgroundColor: colors.surfaceRaised, alignItems: 'center', justifyContent: 'center', gap: 6, padding: 8 },
  tileLabel: { fontSize: 12, fontWeight: '500', color: colors.text },
  tileValue: { fontSize: 12, color: colors.secondary, textAlign: 'center' },
  quick: { flex: 1, height: 52, borderRadius: 16, backgroundColor: colors.surfaceRaised, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6 },
  quickChat: { backgroundColor: colors.brandSoft },
  quickLabel: { fontSize: 13, fontWeight: '500', color: colors.text },
  empty: { gap: 8 },
  profileLink: { minHeight: 44, color: colors.accent, textDecorationLine: 'underline', paddingVertical: 12, fontSize: 13 },
  note: { color: colors.secondary, fontSize: 13, lineHeight: 20 },
});

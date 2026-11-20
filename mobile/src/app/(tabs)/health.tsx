import { Link, useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { EntryRow } from '../../components/ui/EntryRow';
import { Icon } from '../../components/ui/Icon';
import { api } from '../../lib/api';
import { getPermissionState } from '../../lib/notifications';
import { QUOTA_EXHAUSTED_HINT, canUse, type QuotaSnapshot } from '../../lib/quota';
import { DISCLAIMER } from '../../lib/screening';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

// 健康页（Figma 23:393）：猫咪选择卡＋初筛入口（brand 底）＋紧急症状＋健康记录。
export default function HealthScreen() {
  const router = useRouter();
  const [pets, setPets] = useState<{ id: number; name: string }[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [loadError, setLoadError] = useState(false);
  const [notifyDenied, setNotifyDenied] = useState(false);
  const [quota, setQuota] = useState<QuotaSnapshot>();
  useFocusEffect(useCallback(() => {
    let active = true;
    getPermissionState().then(state => { if (active) setNotifyDenied(state === 'denied'); }).catch(() => {});
    api.authorized<QuotaSnapshot>('/quota').then(snapshot => { if (active) setQuota(snapshot); }).catch(() => {});
    api.authorized<{ id: number; name: string }[]>('/pets').then(items => {
      if (active) { setPets(items); setLoadError(false); }
    }).catch(error => {
      if (active) {
        setPets([]);
        setLoadError(!(error instanceof ApiError && (error.status === 401 || error.status === 403)));
      }
    });
    return () => { active = false; };
  }, []));
  const selected = pets.find(pet => pet.id === selectedId) ?? pets[0];
  const cyclePet = () => {
    if (pets.length < 2 || !selected) return;
    const index = pets.findIndex(pet => pet.id === selected.id);
    setSelectedId(pets[(index + 1) % pets.length].id);
  };
  const screeningAllowed = canUse(quota, 'screening');
  return (
    <Screen>
      <View style={styles.head}>
        <Text accessibilityRole="header" style={styles.title}>健康</Text>
        <Text style={styles.subtitle}>{selected ? `关心${selected.name}，从了解开始` : '关心它，从了解开始'}</Text>
      </View>
      {notifyDenied ? (
        <View style={styles.banner}>
          <Text style={styles.bannerText}>通知权限未开启，observe 复查提醒将以应用内横幅呈现，不影响功能。</Text>
          <Link href="/(tabs)/profile" style={styles.link}>前往「我的」重新授权</Link>
        </View>
      ) : null}
      {selected ? (
        <>
          {/* 猫咪选择卡 */}
          <Pressable accessibilityRole="button" accessibilityLabel={`当前猫咪 ${selected.name}，点按切换`}
            onPress={cyclePet} style={({ pressed }) => [styles.petCard, pressed && styles.pressed]}>
            <Image source={require('../../../assets/figma/cat-avatar.png')} style={styles.petAvatar} />
            <View style={styles.petTexts}>
              <Text style={styles.petName}>{selected.name}</Text>
              <Text style={styles.petTag}>当前猫咪</Text>
            </View>
            <Text style={styles.chevron}>›</Text>
          </Pressable>
          {pets.length > 1 ? (
            <View style={styles.selector}>
              {pets.map(pet => (
                <Pressable key={pet.id} accessibilityRole="button" accessibilityState={{ selected: selected.id === pet.id }}
                  onPress={() => setSelectedId(pet.id)} style={[styles.chip, selected.id === pet.id && styles.chipActive]}>
                  <Text style={styles.chipText}>{pet.name}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
          {/* 健康初筛入口（brand 底） */}
          <Pressable accessibilityRole="button" accessibilityState={{ disabled: !screeningAllowed }}
            disabled={!screeningAllowed} onPress={() => router.push(`/screening/${selected.id}`)}
            style={({ pressed }) => [styles.screeningEntry, pressed && screeningAllowed && styles.pressed, !screeningAllowed && styles.dim]}>
            <Icon name="heart" size={22} color={colors.onBrand} />
            <View style={styles.entryTexts}>
              <Text style={styles.screeningTitle}>健康初筛</Text>
              <Text style={styles.screeningSubtitle}>{`花 1 分钟，了解${selected.name}的状态`}</Text>
            </View>
            <Text style={[styles.chevron, { color: colors.onBrand }]}>›</Text>
          </Pressable>
          {!screeningAllowed ? <Text style={styles.quotaHint}>{QUOTA_EXHAUSTED_HINT}（紧急信号不受配额限制，可直接描述症状提交。）</Text> : null}
          {/* 紧急症状入口 */}
          <EntryRow icon="alert" iconColor={colors.danger} backgroundColor={colors.dangerBg}
            title="出现紧急症状？" subtitle="请及时联系专业兽医"
            onPress={() => router.push(`/screening/${selected.id}`)} style={styles.emergency} />
          {/* 健康记录入口 */}
          <EntryRow icon="clock" title="健康记录历史" onPress={() => router.push(`/screening/history/${selected.id}`)} />
        </>
      ) : (
        <View style={styles.empty}>
          <Image source={require('../../../assets/figma/cat-avatar.png')} style={styles.emptyAvatar} />
          <Text style={styles.emptyTitle}>还没有健康记录</Text>
          <Text style={styles.emptyNote}>每一次记录，都是对它的关心</Text>
          <Link href="/(tabs)/profile" style={styles.link}>{loadError ? '暂时无法加载猫咪档案，请稍后重试' : '前往「我的」创建猫咪档案'}</Link>
        </View>
      )}
      <Text style={styles.disclaimer}>{DISCLAIMER}</Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  head: { alignItems: 'center', gap: 4, marginTop: 4 },
  title: { fontSize: 20, lineHeight: 28, fontWeight: '600', color: colors.text },
  subtitle: { fontSize: 13, color: colors.secondary },
  banner: { padding: 12, borderRadius: 12, backgroundColor: colors.brandSoft, gap: 4 },
  bannerText: { fontSize: 13, lineHeight: 20, color: colors.text },
  link: { minHeight: 44, color: colors.accent, textDecorationLine: 'underline', paddingVertical: 12, fontSize: 13 },
  petCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.surfaceRaised, borderRadius: 16, padding: 13, minHeight: 70 },
  pressed: { opacity: 0.85 },
  petAvatar: { width: 44, height: 44, borderRadius: 22 },
  petTexts: { flex: 1, gap: 2 },
  petName: { fontSize: 17, fontWeight: '600', color: colors.text },
  petTag: { fontSize: 11, color: colors.secondary },
  chevron: { fontSize: 25, lineHeight: 30, color: colors.chevron },
  selector: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 32, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.surfaceRaised },
  chipActive: { backgroundColor: colors.brandSoft },
  chipText: { color: colors.text, fontWeight: '600', fontSize: 12 },
  screeningEntry: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.brand, borderRadius: 20, padding: 16, minHeight: 92 },
  dim: { opacity: 0.6 },
  entryTexts: { flex: 1, gap: 4 },
  screeningTitle: { fontSize: 18, fontWeight: '600', color: colors.onBrand },
  screeningSubtitle: { fontSize: 12, color: colors.onBrand },
  quotaHint: { fontSize: 12, lineHeight: 18, color: colors.secondary },
  emergency: { minHeight: 80, borderRadius: 20 },
  empty: { alignItems: 'center', gap: 8, paddingVertical: 32 },
  emptyAvatar: { width: 64, height: 64, borderRadius: 32 },
  emptyTitle: { fontSize: 15, fontWeight: '500', color: colors.secondary },
  emptyNote: { fontSize: 12, color: colors.timestamp },
  disclaimer: { fontSize: 12, lineHeight: 18, color: colors.secondary },
});

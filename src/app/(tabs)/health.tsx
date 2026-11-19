import { Link, useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { getPermissionState } from '../../lib/notifications';
import { QUOTA_EXHAUSTED_HINT, canUse, type QuotaSnapshot } from '../../lib/quota';
import { DISCLAIMER } from '../../lib/screening';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

export default function HealthScreen() {
  const router = useRouter();
  const [pets, setPets] = useState<{ id: number; name: string }[]>([]);
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
  return (
    <Screen>
      <View>
        <Text accessibilityRole="header" style={styles.title}>健康初筛</Text>
        <Text style={styles.subtitle}>回答精神、食欲与症状问题，规则引擎即时给出观察／就医建议；紧急信号直接提示立即就医。</Text>
      </View>
      {notifyDenied ? (
        <View style={styles.banner}>
          <Text style={styles.bannerText}>通知权限未开启，observe 复查提醒将以应用内横幅呈现，不影响功能。</Text>
          <Link href="/profile" style={styles.link}>前往「我的」重新授权</Link>
        </View>
      ) : null}
      {pets.map(pet => (
        <View key={pet.id} style={styles.card}>
          <Text style={styles.cardTitle}>{pet.name}</Text>
          <View style={styles.row}>
            <Pressable accessibilityRole="button" accessibilityState={{ disabled: !canUse(quota, 'screening') }}
              disabled={!canUse(quota, 'screening')} style={[styles.primary, !canUse(quota, 'screening') && styles.dim]}
              onPress={() => router.push(`/screening/${pet.id}`)}>
              <Text style={styles.primaryText}>开始初筛</Text>
            </Pressable>
            <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => router.push(`/screening/history/${pet.id}`)}>
              <Text style={styles.secondaryText}>历史记录</Text>
            </Pressable>
          </View>
          {!canUse(quota, 'screening') ? <Text style={styles.subtitle}>{QUOTA_EXHAUSTED_HINT}（紧急信号不受配额限制，可直接描述症状提交。）</Text> : null}
          <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => router.push(`/timeline/${pet.id}`)}>
            <Text style={styles.secondaryText}>健康时间线</Text>
          </Pressable>
        </View>
      ))}
      {loadError ? <Text accessibilityLiveRegion="polite" style={styles.subtitle}>暂时无法加载猫咪档案。</Text> : null}
      {pets.length === 0 && !loadError ? <Link href="/profile" style={styles.link}>前往「我的」创建猫咪档案</Link> : null}
      <Text style={styles.disclaimer}>{DISCLAIMER}</Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  subtitle: { fontSize: 13, lineHeight: 20, color: colors.secondary, marginTop: 6 },
  card: { padding: 16, borderRadius: 18, backgroundColor: colors.surface, gap: 12 },
  cardTitle: { fontSize: 16, fontWeight: '600', color: colors.text },
  row: { flexDirection: 'row', gap: 10 },
  primary: { flex: 1, minHeight: 44, borderRadius: 12, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: colors.onBrand, fontWeight: '700', fontSize: 14 },
  secondary: { flex: 1, minHeight: 44, borderRadius: 12, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { color: colors.text, fontWeight: '600', fontSize: 14 },
  link: { minHeight: 44, color: colors.text, textDecorationLine: 'underline', paddingVertical: 12 },
  banner: { padding: 12, borderRadius: 12, backgroundColor: colors.soft, gap: 4 },
  bannerText: { fontSize: 13, lineHeight: 20, color: colors.text },
  disclaimer: { fontSize: 12, lineHeight: 18, color: colors.secondary },
  dim: { opacity: 0.6 },
});

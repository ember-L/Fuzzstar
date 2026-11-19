import { Link, useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { DISCLAIMER } from '../../lib/screening';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

export default function HealthScreen() {
  const router = useRouter();
  const [pets, setPets] = useState<{ id: number; name: string }[]>([]);
  const [loadError, setLoadError] = useState(false);
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
    return () => { active = false; };
  }, []));
  return (
    <Screen>
      <View>
        <Text accessibilityRole="header" style={styles.title}>健康初筛</Text>
        <Text style={styles.subtitle}>回答精神、食欲与症状问题，规则引擎即时给出观察／就医建议；紧急信号直接提示立即就医。</Text>
      </View>
      {pets.map(pet => (
        <View key={pet.id} style={styles.card}>
          <Text style={styles.cardTitle}>{pet.name}</Text>
          <View style={styles.row}>
            <Pressable accessibilityRole="button" style={styles.primary} onPress={() => router.push(`/screening/${pet.id}`)}>
              <Text style={styles.primaryText}>开始初筛</Text>
            </Pressable>
            <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => router.push(`/screening/history/${pet.id}`)}>
              <Text style={styles.secondaryText}>历史记录</Text>
            </Pressable>
          </View>
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
  disclaimer: { fontSize: 12, lineHeight: 18, color: colors.secondary },
});

import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { PhotoUpload } from '../../components/PhotoUpload';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

export default function HomeScreen() {
  const [pets, setPets] = useState<{ id: number; name: string }[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [loadError, setLoadError] = useState(false);
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
        <Image source={require('../../../assets/figma/59f10c90466cfa3aa84c0f88478dccedc8f69565.png')} style={styles.cat} accessibilityLabel="绒星猫咪示意图" />
      </View>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{selected ? `${selected.name}的健康状态` : '健康状态'}</Text>
        <Text style={styles.status}>未评估  --</Text>
        <Text style={styles.subtitle}>{selected ? '尚无健康评估记录。' : '创建猫咪档案后，可以查看健康状态。'}</Text>
      </View>
      <Text accessibilityRole="header" style={styles.section}>今日概览</Text>
      <View style={styles.row}>
        {['今日饮食', '最新体重', '最近初筛'].map((label) => (
          <View key={label} style={styles.summary}>
            <Text style={styles.summaryTitle}>{label}</Text>
            <Text style={styles.subtitle}>暂无记录</Text>
          </View>
        ))}
      </View>
      {selected ? <PhotoUpload key={selected.id} pet={selected} /> : null}
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
  cardTitle: { fontSize: 15, fontWeight: '600', color: colors.text },
  status: { fontSize: 23, fontWeight: '700', color: colors.text },
  section: { fontSize: 18, fontWeight: '700', color: colors.text, marginTop: 2 },
  row: { flexDirection: 'row', gap: 10 },
  summary: { flex: 1, minHeight: 92, padding: 12, alignItems: 'center', justifyContent: 'center', borderRadius: 16, backgroundColor: colors.surface },
  summaryTitle: { fontSize: 12, fontWeight: '600', color: colors.text },
  selector: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  pet: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.surface },
  activePet: { backgroundColor: colors.soft },
  profileLink: { minHeight: 44, color: colors.text, textDecorationLine: 'underline', paddingVertical: 12 },
  note: { color: colors.secondary, fontSize: 13, lineHeight: 20 },
});

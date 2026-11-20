import { StyleSheet, Text, View } from 'react-native';
import { Screen } from './Screen';
import { colors } from '../theme';

export function ComingSoon({ title, description }: { title: string; description: string }) {
  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>{title}</Text>
      <View style={styles.card}>
        <Text style={styles.heading}>功能建设中</Text>
        <Text style={styles.description}>{description}</Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  card: { borderRadius: 20, padding: 24, backgroundColor: colors.surface },
  heading: { fontSize: 18, fontWeight: '600', color: colors.text },
  description: { fontSize: 14, lineHeight: 22, color: colors.secondary, marginTop: 10 },
});

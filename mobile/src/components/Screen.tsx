import { ReactNode } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme';

export function Screen({ children }: { children: ReactNode }) {
  return (
    <SafeAreaView edges={['top']} style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>{children}</ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  // 画板基准 390 宽、左右边距 16；宽屏居中限宽保持可读
  content: { width: '100%', maxWidth: 560, alignSelf: 'center', padding: 16, paddingBottom: 32, gap: 12 },
});

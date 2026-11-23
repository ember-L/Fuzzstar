import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { colors } from '../../theme';

// 画板小节标题：Semibold 17 ＋右侧 Regular 12 操作（如「查看全部 ›」）
export function SectionHeader({ title, actionLabel, onAction, style }: {
  title: string; actionLabel?: string; onAction?: () => void; style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.row, style]}>
      <Text style={styles.title}>{title}</Text>
      {actionLabel ? (
        <Pressable accessibilityRole="button" onPress={onAction} hitSlop={8}>
          <Text style={styles.action}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 },
  title: { fontSize: 17, fontWeight: '600', color: colors.text },
  action: { fontSize: 12, color: colors.secondary },
});

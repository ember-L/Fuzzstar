import { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { colors } from '../../theme';

// Card / Health · Reminder · Chat（圆角 20，内边距 24；标题/辅助信息/操作入口层级）
export function Card({ label, title, description, action, onPress, children, style }: {
  label?: string; title?: string; description?: string; action?: string;
  onPress?: () => void; children?: ReactNode; style?: StyleProp<ViewStyle>;
}) {
  const body = (
    <View style={[styles.card, style]}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      {title ? <Text style={styles.title}>{title}</Text> : null}
      {description ? <Text style={styles.description}>{description}</Text> : null}
      {children}
      {action ? <Text style={styles.action}>{`${action}   →`}</Text> : null}
    </View>
  );
  if (!onPress) return body;
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => pressed && styles.pressed}>
      {body}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceRaised, borderRadius: 20, padding: 24, gap: 8 },
  pressed: { opacity: 0.85 },
  label: { fontSize: 14, color: colors.secondary },
  title: { fontSize: 25, lineHeight: 35, fontWeight: '600', color: colors.text },
  description: { fontSize: 15, lineHeight: 21, color: colors.secondary },
  action: { fontSize: 16, fontWeight: '600', color: colors.accent, marginTop: 8 },
});

import { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { colors } from '../../theme';
import { Icon, type IconName } from './Icon';

// 入口行：图标＋标题/副标题＋右侧 ›（健康页/我的页列表）
export function EntryRow({ icon, iconColor = colors.accent, title, subtitle, onPress, trailing, style, backgroundColor }: {
  icon?: IconName; iconColor?: string; title: string; subtitle?: string;
  onPress?: () => void; trailing?: ReactNode; style?: StyleProp<ViewStyle>; backgroundColor?: string;
}) {
  const titleColor = backgroundColor === colors.dangerBg ? colors.danger : colors.text;
  const body = (
    <View style={[styles.row, backgroundColor ? { backgroundColor } : null, style]}>
      {icon ? <Icon name={icon} size={22} color={iconColor} /> : null}
      <View style={styles.texts}>
        <Text style={[styles.title, { color: titleColor }]}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
      {trailing ?? <Text style={[styles.chevron, backgroundColor === colors.dangerBg ? { color: colors.danger } : null]}>›</Text>}
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
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surfaceRaised, borderRadius: 16,
    paddingHorizontal: 14, paddingVertical: 14,
  },
  pressed: { opacity: 0.85 },
  texts: { flex: 1, gap: 2 },
  title: { fontSize: 15, fontWeight: '600', color: colors.text },
  subtitle: { fontSize: 12, color: colors.secondary },
  chevron: { fontSize: 25, lineHeight: 30, color: colors.chevron },
});

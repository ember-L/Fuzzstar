import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { colors } from '../../theme';

export type StatusVariant = 'success' | 'warning' | 'danger' | 'neutral';

const VARIANTS: Record<StatusVariant, { bg: string; fg: string; symbol: string }> = {
  success: { bg: colors.successBg, fg: colors.success, symbol: '✓' },
  warning: { bg: colors.warningBg, fg: colors.warning, symbol: '!' },
  danger: { bg: colors.dangerBg, fg: colors.danger, symbol: '!' },
  neutral: { bg: colors.brandSoft, fg: colors.secondary, symbol: '•' },
};

// Status / Success · Warning · Danger · Neutral（高 42 圆角 21，文字＋符号＋颜色共同表达）
export function StatusPill({ variant, label, style }: {
  variant: StatusVariant; label: string; style?: StyleProp<ViewStyle>;
}) {
  const v = VARIANTS[variant];
  return (
    <View accessibilityRole="text" style={[styles.base, { backgroundColor: v.bg }, style]}>
      <Text style={[styles.label, { color: v.fg }]}>{`${v.symbol}  ${label}`}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  base: { height: 42, borderRadius: 21, paddingHorizontal: 20, alignItems: 'center', justifyContent: 'center', alignSelf: 'flex-start' },
  label: { fontSize: 14, fontWeight: '500' },
});

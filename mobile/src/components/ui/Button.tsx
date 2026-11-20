import { ActivityIndicator, Pressable, StyleSheet, Text, type StyleProp, type ViewStyle } from 'react-native';
import { colors } from '../../theme';

// Button / Primary · Secondary · Pressed · Disabled（组件规范 21:116，高 48 圆角 24）
export function Button({ title, onPress, variant = 'primary', disabled = false, busy = false, style }: {
  title: string; onPress?: () => void; variant?: 'primary' | 'secondary';
  disabled?: boolean; busy?: boolean; style?: StyleProp<ViewStyle>;
}) {
  const inactive = disabled || busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        variant === 'primary' ? styles.primary : styles.secondary,
        pressed && !inactive && (variant === 'primary' ? styles.primaryPressed : styles.secondaryPressed),
        inactive && styles.disabled,
        style,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={variant === 'primary' ? colors.onBrand : colors.accent} />
      ) : (
        <Text style={[styles.label, inactive ? styles.disabledLabel : variant === 'primary' ? styles.primaryLabel : styles.secondaryLabel]}>
          {title}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: { height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },
  primary: { backgroundColor: colors.brand },
  primaryPressed: { backgroundColor: colors.brandPressed },
  secondary: { backgroundColor: colors.brandSoft },
  secondaryPressed: { backgroundColor: '#F5E3CB' },
  disabled: { backgroundColor: colors.disabledBg },
  label: { fontSize: 16, fontWeight: '600' },
  primaryLabel: { color: colors.onBrand },
  secondaryLabel: { color: colors.accent },
  disabledLabel: { color: colors.disabledText },
});

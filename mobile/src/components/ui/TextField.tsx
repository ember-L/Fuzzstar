import { StyleSheet, TextInput } from 'react-native';
import type { ComponentProps } from 'react';
import { colors } from '../../theme';

// Input / Default（高 56 圆角 16，占位符 #796B60）；React 19 直接透传 ref 等 props。
export function TextField({ style, ...props }: ComponentProps<typeof TextInput>) {
  return (
    <TextInput
      placeholderTextColor={colors.disabledText}
      style={[styles.input, style]}
      {...props}
    />
  );
}

const styles = StyleSheet.create({
  input: {
    height: 56, borderRadius: 16, backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 20, fontSize: 16, color: colors.text,
  },
});

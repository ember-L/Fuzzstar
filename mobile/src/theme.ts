// 绒星 v2 / Foundations（Figma 变量集合 18:2）＋画板专用强调色。
// 旧键名（surface/soft/secondary）保留为别名，避免破坏既有页面。
export const colors = {
  background: '#FFFFFF',
  surface: '#FAF8F6',
  surfaceRaised: '#FAF8F6',
  soft: '#FFF0DF',
  brand: '#FEAE36',
  brandPressed: '#EE941D',
  brandAccent: '#FF9F24',
  brandSoft: '#FFF0DF',
  onBrand: '#4B2617',
  text: '#743A10',
  secondary: '#805535',
  textSecondary: '#805535',
  border: '#D9BFA5',
  borderStrong: '#89552F',
  success: '#166534',
  successBg: '#EDF8EE',
  warning: '#8A4B00',
  warningBg: '#FFF4D8',
  danger: '#B42318',
  dangerBg: '#FFF1F0',
  focus: '#315CBE',
  disabledBg: '#E9DED2',
  disabledText: '#796B60',
  // 画板专用（不在变量集合内）
  accent: '#A34400',
  heroBg: '#FFEDD7',
  sparkle: '#ED7413',
  neutralPillBg: '#F3EEE9',
  mutedIcon: '#C6A894',
  chevron: '#B59B88',
  timestamp: '#A78976',
  assistantBubble: '#FFE2B6',
};

// space/1..8（v2：4/8/12/16/20/24/32/40）
export const spacing = { s1: 4, s2: 8, s3: 12, s4: 16, s5: 20, s6: 24, s7: 32, s8: 40 };

// radius/sm md lg xl pill
export const radius = { sm: 8, md: 12, lg: 20, xl: 24, pill: 999 };

// v2 文字样式（PingFang SC；RN 用系统字体＋字重，中文在 iOS 自动落 PingFang SC）
export const typography = {
  pageTitle: { fontSize: 24, lineHeight: 32, fontWeight: '600' },
  sectionTitle: { fontSize: 20, lineHeight: 28, fontWeight: '600' },
  emphasis: { fontSize: 18, lineHeight: 26, fontWeight: '600' },
  body: { fontSize: 16, lineHeight: 24, fontWeight: '400' },
  caption: { fontSize: 14, lineHeight: 21, fontWeight: '400' },
  label: { fontSize: 12, lineHeight: 18, fontWeight: '500' },
} as const;

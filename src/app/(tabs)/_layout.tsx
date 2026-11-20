import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Tabs } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors } from '../../theme';
import { Icon, type IconName } from '../../components/ui/Icon';

const TAB_ICONS: Record<string, IconName> = { index: 'home', health: 'health', chat: 'chat', profile: 'user' };

// 底部导航（画板：白底，图标 24，标签 11；选中 #A34400 Semibold，未选中 #805535 Regular）
// 结构化 props（与 expo-router 传入的 BottomTabBarProps 兼容，避免直接依赖包解析）
interface TabBarProps {
  state: { routes: { key: string; name: string }[]; index: number };
  descriptors: Record<string, { options: { title?: string } }>;
  navigateToTab: (routeKey: string) => void;
}

function DesignTabBar({ state, descriptors, navigateToTab }: TabBarProps) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 10) }]}>
      {state.routes.map((route, index) => {
        const focused = state.index === index;
        const options = descriptors[route.key].options;
        const label = (options.title ?? route.name) as string;
        const color = focused ? colors.accent : colors.secondary;
        return (
          <Pressable
            key={route.key}
            accessibilityRole="button"
            accessibilityState={{ selected: focused }}
            accessibilityLabel={label}
            onPress={() => navigateToTab(route.key)}
            style={styles.item}
          >
            <Icon name={TAB_ICONS[route.name] ?? 'home'} size={24} color={color} />
            <Text style={[styles.label, { color, fontWeight: focused ? '600' : '400' }]}>{label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function TabLayout() {
  return (
    <Tabs tabBar={(props) => <DesignTabBar {...props} />} screenOptions={{ headerShown: false }}>
      <Tabs.Screen name="index" options={{ title: '首页' }} />
      <Tabs.Screen name="health" options={{ title: '健康' }} />
      <Tabs.Screen name="chat" options={{ title: '聊聊' }} />
      <Tabs.Screen name="profile" options={{ title: '我的' }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', backgroundColor: colors.background, paddingTop: 12 },
  item: { flex: 1, alignItems: 'center', gap: 6 },
  label: { fontSize: 11 },
});

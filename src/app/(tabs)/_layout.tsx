import { Ionicons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import { colors } from '../../theme';

export default function TabLayout() {
  return (
    <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: '#A34400', tabBarInactiveTintColor: colors.secondary, tabBarStyle: { borderTopColor: colors.border } }}>
      <Tabs.Screen name="index" options={{ title: '首页', tabBarIcon: ({ focused, size }) => <Ionicons name="home-outline" size={size} color={focused ? "#A34400" : colors.secondary} /> }} />
      <Tabs.Screen name="health" options={{ title: '健康', tabBarIcon: ({ focused, size }) => <Ionicons name="heart-outline" size={size} color={focused ? "#A34400" : colors.secondary} /> }} />
      <Tabs.Screen name="chat" options={{ title: '聊聊', tabBarIcon: ({ focused, size }) => <Ionicons name="chatbubble-ellipses-outline" size={size} color={focused ? "#A34400" : colors.secondary} /> }} />
      <Tabs.Screen name="profile" options={{ title: '我的', tabBarIcon: ({ focused, size }) => <Ionicons name="person-outline" size={size} color={focused ? "#A34400" : colors.secondary} /> }} />
    </Tabs>
  );
}

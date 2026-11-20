import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { createSessionClient } from './session';

const url = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '');
const key = 'rongxing.refresh';
let browserToken: string | null = null;

export const api = createSessionClient((path, init) => {
  if (!url) throw new Error('请先配置绒星 API 地址');
  if (!__DEV__ && !url.startsWith('https://')) throw new Error('发布环境需要 HTTPS API 地址');
  return fetch(`${url}${path}`, init);
}, {
  read: () => Platform.OS === 'web' ? Promise.resolve(browserToken) : SecureStore.getItemAsync(key),
  async write(token) {
    if (Platform.OS === 'web') browserToken = token;
    else if (token) await SecureStore.setItemAsync(key, token);
    else await SecureStore.deleteItemAsync(key);
  },
});

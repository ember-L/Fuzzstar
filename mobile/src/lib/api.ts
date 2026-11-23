import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { ApiError, createSessionClient } from './session';

// 开发环境允许零配置：Web 用当前页面主机，Expo Go/模拟器用 Metro 主机。
// 生产环境仍必须显式提供 EXPO_PUBLIC_API_URL，并强制 HTTPS。
function developmentUrl(): string | undefined {
  if (!__DEV__) return undefined;
  if (Platform.OS === 'web') {
    const host = typeof window === 'undefined' || window.location.hostname === 'localhost'
      ? '127.0.0.1'
      : window.location.hostname;
    return 'http://' + host + ':8000/api/v1';
  }
  const host = Constants.expoConfig?.hostUri?.split(':')[0];
  return host ? 'http://' + (host === 'localhost' ? '127.0.0.1' : host) + ':8000/api/v1' : undefined;
}

const configured = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '');
const url = configured || developmentUrl();
const key = 'rongxing.refresh';
let browserToken: string | null = null;

export const api = createSessionClient((path, init) => {
  if (!url) throw new ApiError(0, 'API_NOT_CONFIGURED', '请先配置绒星 API 地址');
  if (!__DEV__ && !url.startsWith('https://')) throw new ApiError(0, 'API_NOT_CONFIGURED', '发布环境需要 HTTPS API 地址');
  return fetch(`${url}${path}`, init);
}, {
  read: () => Platform.OS === 'web' ? Promise.resolve(browserToken) : SecureStore.getItemAsync(key),
  async write(token) {
    if (Platform.OS === 'web') browserToken = token;
    else if (token) await SecureStore.setItemAsync(key, token);
    else await SecureStore.deleteItemAsync(key);
  },
});

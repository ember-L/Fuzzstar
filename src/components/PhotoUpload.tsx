import { fetch as sendUpload } from 'expo/fetch';
import { File } from 'expo-file-system';
import { launchImageLibraryAsync } from 'expo-image-picker';
import { useEffect, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '../lib/api';
import { PhotoUploadError, uploadPhoto } from '../lib/photo-upload';
import { ApiError } from '../lib/session';
import { colors } from '../theme';

export function PhotoUpload({ pet }: { pet: { id: number; name: string } }) {
  const [photo, setPhoto] = useState<{ file: Blob; name: string }>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const operation = useRef<AbortController | null>(null);
  useEffect(() => () => {
    operation.current?.abort();
    operation.current = null;
  }, []);

  async function pick() {
    if (operation.current) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    try {
      const result = await launchImageLibraryAsync({ mediaTypes: ['images'], quality: 1 });
      if (result.canceled) return;
      const asset = result.assets[0];
      if (Platform.OS === 'web') URL.revokeObjectURL(asset.uri);
      if (controller.signal.aborted) return;
      const file = asset.file ?? new File(asset.uri);
      setPhoto({ file, name: asset.fileName || '已选照片' });
      setMessage('');
    } catch {
      if (!controller.signal.aborted) {
        setPhoto(undefined);
        setMessage('无法读取照片，请重新选择 JPG、PNG 或 HEIC 文件。');
      }
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(false);
      }
    }
  }

  async function submit() {
    if (!photo || operation.current) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setMessage('正在上传并验证照片…');
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 60_000);
    try {
      await uploadPhoto(pet.id, photo.file, api.authorized, sendUpload, controller.signal);
      setPhoto(undefined);
      setMessage('照片已验证。');
    } catch (error) {
      if (operation.current !== controller) return;
      if (timedOut) setMessage('上传或验证超时，请重试。');
      else setMessage(error instanceof ApiError || error instanceof PhotoUploadError ? error.message : '无法上传照片，请重试。');
    } finally {
      clearTimeout(timer);
      if (operation.current === controller) {
        operation.current = null;
        setBusy(false);
      }
    }
  }

  return (
    <View style={styles.card}>
      <Text accessibilityRole="header" style={styles.title}>给{pet.name}上传照片</Text>
      <Text style={styles.note}>JPG、PNG 或 HEIC，单张不超过 10 MiB。此处只上传和验证照片，不生成分身。</Text>
      {photo ? <Text style={styles.note}>待上传：{photo.name}</Text> : null}
      <View style={styles.actions}>
        <Pressable accessibilityRole="button" accessibilityState={{ disabled: busy }} disabled={busy}
          onPress={pick} style={[styles.button, busy && styles.disabled]}>
          <Text style={styles.title}>{photo ? '重新选择' : '选择照片'}</Text>
        </Pressable>
        {photo ? <Pressable accessibilityRole="button" accessibilityState={{ disabled: busy }} disabled={busy}
          onPress={submit} style={[styles.button, styles.primary, busy && styles.disabled]}>
          <Text style={styles.title}>确认上传</Text>
        </Pressable> : null}
      </View>
      {message ? <Text accessibilityLiveRegion="polite" style={styles.note}>{message}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: 20, borderRadius: 20, backgroundColor: colors.surface, gap: 8 },
  title: { fontSize: 15, fontWeight: '600', color: colors.onBrand },
  note: { fontSize: 13, lineHeight: 20, color: colors.secondary },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  button: { minHeight: 44, paddingHorizontal: 14, justifyContent: 'center', borderRadius: 12, backgroundColor: colors.soft },
  primary: { backgroundColor: colors.brand },
  disabled: { opacity: 0.6 },
});

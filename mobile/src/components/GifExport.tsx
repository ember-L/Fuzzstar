// GIF 导出与分享（T17，FRD F13-1/2）：选动作→gif_export 任务（60s 轮询）→下载本地→
// 系统分享面板。水印「绒星 · AI 参考」由服务端烧录；仅本地分享，不上传第三方。
import * as Sharing from 'expo-sharing';
import { useEffect, useRef, useState } from 'react';
import { Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '../lib/api';
import { ACTION_LABELS, GIF_ACTIONS, GIF_SHARE_HINT, gifFileName, parseGifTask } from '../lib/gif-export';
import { ApiError } from '../lib/session';
import { pollTask, type TaskSnapshot } from '../lib/task-poller';
import { colors } from '../theme';

export function GifExport({ pet }: { pet: { id: number; name: string } }) {
  const [action, setAction] = useState<string>('idle');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const polling = useRef<AbortController | null>(null);
  useEffect(() => () => {
    polling.current?.abort();
    polling.current = null;
  }, []);

  async function exportAndShare() {
    if (busy) return;
    const controller = new AbortController();
    polling.current = controller;
    setBusy(true);
    setMessage('正在导出 GIF…');
    try {
      const submitted = await api.authorized<{ task_id: string; status: string }>(`/pets/${pet.id}/share/gif`, {
        method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }),
      });
      const outcome = await pollTask(submitted.task_id, 'gif_export', {
        fetchTask: (taskId, signal) => api.authorized<TaskSnapshot>(`/tasks/${taskId}`, { signal }),
        signal: controller.signal,
      });
      if (outcome.kind === 'aborted') return;
      if (outcome.kind === 'timeout') { setMessage('导出超时，请稍后重试。'); return; }
      const view = parseGifTask(outcome.task);
      if (view.status !== 'succeeded' || !view.downloadUrl) { setMessage('导出失败，请稍后重试。'); return; }
      if (Platform.OS === 'web') {
        await Linking.openURL(view.downloadUrl);
        setMessage('GIF 已就绪，已通过浏览器下载（web 不支持系统分享面板）。');
        return;
      }
      const FileSystem = await import('expo-file-system/legacy');
      const dir = FileSystem.documentDirectory + 'gif-export/';
      await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => { /* 已存在 */ });
      const result = await FileSystem.downloadAsync(view.downloadUrl, dir + gifFileName(pet.name, action));
      if (result.status !== 200) throw new Error('GIF download failed');
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(result.uri, { mimeType: 'image/gif', dialogTitle: '分享 GIF' });
        setMessage('GIF 已就绪，已通过系统分享面板发送。');
      } else {
        setMessage('GIF 已保存到本地：' + result.uri);
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      setMessage(error instanceof ApiError ? error.message : '导出失败，请稍后重试。');
    } finally {
      if (polling.current === controller) {
        polling.current = null;
        setBusy(false);
      }
    }
  }

  return (
    <View style={styles.card}>
      <Text accessibilityRole="header" style={styles.title}>导出 {pet.name} 的 GIF</Text>
      <View style={styles.actions}>
        {GIF_ACTIONS.map(item => (
          <Pressable key={item} accessibilityRole="radio" accessibilityState={{ checked: action === item }}
            disabled={busy} onPress={() => setAction(item)} style={[styles.chip, action === item && styles.chipActive]}>
            <Text style={styles.chipText}>{action === item ? '✓ ' : ''}{ACTION_LABELS[item]}</Text>
          </Pressable>
        ))}
      </View>
      <Pressable accessibilityRole="button" accessibilityState={{ disabled: busy }} disabled={busy}
        onPress={() => void exportAndShare()} style={[styles.button, busy && styles.disabled]}>
        <Text style={styles.buttonText}>{busy ? '导出中…' : '导出并分享 GIF'}</Text>
      </Pressable>
      <Text style={styles.note}>{GIF_SHARE_HINT}</Text>
      {message ? <Text accessibilityLiveRegion="polite" style={styles.note}>{message}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: 20, borderRadius: 20, backgroundColor: colors.surface, gap: 8 },
  title: { fontSize: 15, fontWeight: '600', color: colors.onBrand },
  note: { fontSize: 13, lineHeight: 20, color: colors.secondary },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 40, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.soft },
  chipActive: { backgroundColor: colors.brand },
  chipText: { fontSize: 13, fontWeight: '600', color: colors.text },
  button: { minHeight: 44, justifyContent: 'center', alignItems: 'center', borderRadius: 12, backgroundColor: colors.brand, padding: 10 },
  buttonText: { color: colors.onBrand, fontSize: 15, fontWeight: '600' },
  disabled: { opacity: 0.6 },
});

import { fetch as sendUpload } from 'expo/fetch';
import { File } from 'expo-file-system';
import { launchImageLibraryAsync } from 'expo-image-picker';
import { useEffect, useRef, useState } from 'react';
import { AppState, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '../lib/api';
import { PhotoUploadError, uploadPhoto } from '../lib/photo-upload';
import { ApiError } from '../lib/session';
import { pollTask, type TaskSnapshot } from '../lib/task-poller';
import { colors } from '../theme';

type Generation =
  | { phase: 'polling' | 'failed' | 'timeout'; taskId: string }
  | { phase: 'ready' | 'unusable'; taskId: string; readyCount: number }
  | { phase: 'error'; taskId: string; message: string };

export function PhotoUpload({ pet }: { pet: { id: number; name: string } }) {
  const [photo, setPhoto] = useState<{ file: Blob; name: string }>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [generation, setGeneration] = useState<Generation>();
  const [lastMediaId, setLastMediaId] = useState<string>();
  const operation = useRef<AbortController | null>(null);
  const polling = useRef<AbortController | null>(null);
  const visible = useRef(true);
  useEffect(() => {
    visible.current = AppState.currentState === 'active';
    const subscription = AppState.addEventListener('change', state => { visible.current = state === 'active'; });
    return () => {
      subscription.remove();
      operation.current?.abort();
      operation.current = null;
      polling.current?.abort();
      polling.current = null;
    };
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

  async function trackTask(taskId: string) {
    polling.current?.abort();
    const controller = new AbortController();
    polling.current = controller;
    setGeneration({ phase: 'polling', taskId });
    try {
      const outcome = await pollTask(taskId, 'avatar_batch', {
        fetchTask: (id, signal) => api.authorized<TaskSnapshot>(`/tasks/${id}`, { signal }),
        signal: controller.signal,
        isVisible: () => visible.current,
      });
      if (polling.current !== controller || outcome.kind === 'aborted') return;
      if (outcome.kind === 'timeout') { setGeneration({ phase: 'timeout', taskId }); return; }
      const task = outcome.task;
      if (task.status !== 'succeeded') { setGeneration({ phase: 'failed', taskId }); return; }
      const result = task.result as { usable?: boolean; ready_count?: number } | null;
      const readyCount = result?.ready_count ?? 0;
      setGeneration(result?.usable ? { phase: 'ready', taskId, readyCount } : { phase: 'unusable', taskId, readyCount });
    } catch (error) {
      if (polling.current !== controller) return;
      setGeneration({ phase: 'error', taskId, message: error instanceof ApiError ? error.message : '查询生成进度失败，请重试。' });
    }
  }

  async function submitAvatar(mediaId: string, signal: AbortSignal) {
    const submitted = await api.authorized<{ task_id: string; status: string }>(`/pets/${pet.id}/avatar`, {
      method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ media_id: mediaId }),
    });
    if (!/^[0-9a-f]{32}$/.test(submitted?.task_id ?? '')) throw new PhotoUploadError('未获得有效的生成任务。');
    setLastMediaId(mediaId);
    void trackTask(submitted.task_id);
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
      const mediaId = await uploadPhoto(pet.id, photo.file, api.authorized, sendUpload, controller.signal);
      setPhoto(undefined);
      setMessage('照片已验证，正在提交分身生成…');
      await submitAvatar(mediaId, controller.signal);
      setMessage('');
    } catch (error) {
      if (operation.current !== controller) return;
      if (timedOut) setMessage('上传或提交超时，请重试。');
      else setMessage(error instanceof ApiError || error instanceof PhotoUploadError ? error.message : '无法上传照片，请重试。');
    } finally {
      clearTimeout(timer);
      if (operation.current === controller) {
        operation.current = null;
        setBusy(false);
      }
    }
  }

  async function retry() {
    if (!lastMediaId || operation.current) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    try {
      await submitAvatar(lastMediaId, controller.signal);
    } catch (error) {
      if (operation.current === controller) {
        setGeneration({ phase: 'error', taskId: generation?.taskId ?? '', message: error instanceof ApiError ? error.message : '重试提交失败，请稍后再试。' });
      }
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        setBusy(false);
      }
    }
  }

  const generationText = !generation ? '' : generation.phase === 'polling' ? '分身生成中，离开页面不会中断，稍后可回来查看。'
    : generation.phase === 'ready' ? `分身已就绪（${generation.readyCount}/7 个动作）。`
    : generation.phase === 'unusable' ? `仅 ${generation.readyCount}/7 个动作就绪，暂不可用，可重试生成。`
    : generation.phase === 'failed' ? '分身生成失败，可重试。'
    : generation.phase === 'timeout' ? '生成时间较长，后台仍在继续，可稍后重试查询。'
    : generation.phase === 'error' ? generation.message : '';
  const canRetry = Boolean(lastMediaId) && generation !== undefined && generation.phase !== 'polling' && generation.phase !== 'ready';

  return (
    <View style={styles.card}>
      <Text accessibilityRole="header" style={styles.title}>给{pet.name}上传照片</Text>
      <Text style={styles.note}>JPG、PNG 或 HEIC，单张不超过 10 MiB。验证通过后自动生成 7 个动作的分身素材。</Text>
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
        {canRetry ? <Pressable accessibilityRole="button" accessibilityState={{ disabled: busy }} disabled={busy}
          onPress={retry} style={[styles.button, busy && styles.disabled]}>
          <Text style={styles.title}>重试生成</Text>
        </Pressable> : null}
      </View>
      {message ? <Text accessibilityLiveRegion="polite" style={styles.note}>{message}</Text> : null}
      {generationText ? <Text accessibilityLiveRegion="polite" style={styles.note}>{generationText}</Text> : null}
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

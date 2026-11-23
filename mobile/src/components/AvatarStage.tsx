import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, StyleSheet, Text, View } from 'react-native';
import { api } from '../lib/api';
import { type ActionMap } from '../lib/action-map';
import { loadActionMap } from '../lib/action-map-client';
import { getAssetStore } from '../lib/asset-store';
import { type AvatarView, type PlaceholderManifest } from '../lib/avatar';
import { ApiError } from '../lib/session';
import { pollTask, type TaskSnapshot } from '../lib/task-poller';
import { AvatarPlayer, type EmotionEvent, type HealthInput } from './avatar/AvatarPlayer';
import { colors } from '../theme';

export interface Submission {
  taskId: string;
  placeholder?: PlaceholderManifest;
}

// 首页分身舞台：提交后立即播放占位首帧（AC-03-1），轮询任务，播放交给 AvatarPlayer。
// health 由 T08 健康 store 接线；当前首页无健康数据时按 normal 待机。
export function AvatarStage({ pet, submission, health, emotionEvent }: {
  pet: { id: number; name: string };
  submission?: Submission;
  health?: HealthInput | null;
  emotionEvent?: EmotionEvent | null;
}) {
  const [fetched, setFetched] = useState<AvatarView | null>(null);
  const [notice, setNotice] = useState<{ taskId: string; text: string } | null>(null);
  const [map, setMap] = useState<ActionMap | null>(null);
  const polling = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      polling.current?.abort();
      polling.current = null;
    };
  }, []);

  // 动作映射：挂载/回前台/每 60s 比对版本更新（AC-04-4 免发版生效），离线用缓存。
  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const store = await getAssetStore();
        const next = await loadActionMap(signal => api.authorized('/config/action-map', { signal }), store.kv);
        if (!cancelled && next) setMap(next);
      } catch { /* 保持现有映射或 idle 待机 */ }
    };
    void refresh();
    const sub = AppState.addEventListener('change', state => { if (state === 'active') void refresh(); });
    const timer = setInterval(() => { if (AppState.currentState === 'active') void refresh(); }, 60000);
    return () => { cancelled = true; sub.remove(); clearInterval(timer); };
  }, []);

  const fetchAvatar = useCallback(async (signal?: AbortSignal): Promise<AvatarView | null> => {
    try {
      return await api.authorized<AvatarView>(`/pets/${pet.id}/avatar`, { signal });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  }, [pet.id]);

  const track = useCallback(async (taskId: string) => {
    polling.current?.abort();
    const controller = new AbortController();
    polling.current = controller;
    try {
      const outcome = await pollTask(taskId, 'avatar_batch', {
        fetchTask: (id, signal) => api.authorized<TaskSnapshot>(`/tasks/${id}`, { signal }),
        signal: controller.signal,
        isVisible: () => AppState.currentState === 'active',
      });
      if (!mounted.current || polling.current !== controller || outcome.kind === 'aborted') return;
      if (outcome.kind === 'timeout') { setNotice({ taskId, text: '生成时间较长，后台仍在继续，可稍后回来查看。' }); return; }
      if (outcome.task.status !== 'succeeded') { setNotice({ taskId, text: '分身生成失败，可在下方上传卡片重试。' }); return; }
      const view = await fetchAvatar(controller.signal);
      if (!mounted.current || polling.current !== controller) return;
      setFetched(view);
      setNotice({ taskId, text: view?.usable ? `分身已就绪（${view.ready_count}/7 个动作）。` : `仅 ${view?.ready_count ?? 0}/7 个动作就绪，暂不可用。` });
    } catch {
      if (mounted.current && polling.current === controller) setNotice({ taskId, text: '查询生成进度失败，请稍后重试。' });
    }
  }, [fetchAvatar]);

  useEffect(() => {
    const controller = new AbortController();
    fetchAvatar(controller.signal).then(view => {
      if (!mounted.current) return;
      setFetched(view);
      if (view && (view.status === 'pending' || view.status === 'running')) void track(view.task_id);
    }).catch(() => { /* 读取失败时保持静态底图兜底 */ });
    return () => controller.abort();
  }, [fetchAvatar, track]);

  useEffect(() => {
    if (submission?.placeholder) void Promise.resolve().then(() => track(submission.taskId));
  }, [submission, track]);

  // 提交后立即用占位清单渲染（无需等待额外请求）；动图通道提交没有占位清单，交给静态底图兜底。
  const placeholder = submission?.placeholder;
  const pending: AvatarView | null = submission && placeholder
    ? {
        task_id: submission.taskId, status: 'pending', body_type: placeholder.body_type,
        base_image: null, clips: {}, ready_count: 0, usable: false, placeholder_manifest: placeholder,
      }
    : null;
  const avatar: AvatarView | null = fetched ?? pending;
  const caption = notice && avatar && notice.taskId === avatar.task_id ? notice.text
    : avatar && (avatar.status === 'pending' || avatar.status === 'running') ? '分身生成中…' : '';

  return (
    <View style={styles.stage}>
      <AvatarPlayer pet={pet} avatar={avatar} map={map} health={health} emotionEvent={emotionEvent} />
      {caption ? <Text accessibilityLiveRegion="polite" style={styles.caption}>{caption}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stage: { width: '54%', maxWidth: 160, marginTop: 5, marginBottom: 2 },
  caption: { fontSize: 10, lineHeight: 14, color: colors.secondary, textAlign: 'center' },
});

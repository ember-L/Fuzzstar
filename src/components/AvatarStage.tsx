import { useVideoPlayer, VideoView } from 'expo-video';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Image, StyleSheet, Text, View } from 'react-native';
import { api } from '../lib/api';
import { pickIdleSource, type AvatarView, type PlaceholderManifest } from '../lib/avatar';
import { ApiError } from '../lib/session';
import { pollTask, type TaskSnapshot } from '../lib/task-poller';
import { colors } from '../theme';

export interface Submission {
  taskId: string;
  placeholder: PlaceholderManifest;
}

// 首页分身舞台：提交后立即播放占位首帧（AC-03-1），生成成功后切换个人 idle 片。
// 完整动作播放器（附录 C 联动/淡入淡出/缓存）在 T07 实现。
export function AvatarStage({ pet, submission }: { pet: { id: number; name: string }; submission?: Submission }) {
  const [fetched, setFetched] = useState<AvatarView | null>(null);
  const [notice, setNotice] = useState<{ taskId: string; text: string } | null>(null);
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
    if (submission) void Promise.resolve().then(() => track(submission.taskId));
  }, [submission, track]);

  // 提交后立即用占位清单渲染（无需等待额外请求）；同任务的服务端结果到达后切换。
  const avatar: AvatarView | null = submission
    ? (fetched?.task_id === submission.taskId ? fetched : {
        task_id: submission.taskId, status: 'pending', body_type: submission.placeholder.body_type,
        base_image: null, clips: {}, ready_count: 0, usable: false, placeholder_manifest: submission.placeholder,
      })
    : fetched;
  const caption = notice && avatar && notice.taskId === avatar.task_id ? notice.text
    : avatar && (avatar.status === 'pending' || avatar.status === 'running') ? '分身生成中…' : '';

  const source = pickIdleSource(avatar);
  const url = source.kind === 'static' ? null : source.url;
  const player = useVideoPlayer(url, setup => { setup.loop = true; setup.muted = true; });
  useEffect(() => {
    if (!url) return;
    const sync = () => { if (AppState.currentState === 'active') player.play(); else player.pause(); };
    sync();
    const subscription = AppState.addEventListener('change', sync);
    return () => { subscription.remove(); player.pause(); };
  }, [url, player]);

  return (
    <View style={styles.stage}>
      {url ? (
        <VideoView player={player} style={styles.media} contentFit="contain" nativeControls={false}
          accessibilityLabel={`${pet.name}的分身`} />
      ) : (
        <Image source={require('../../../assets/figma/59f10c90466cfa3aa84c0f88478dccedc8f69565.png')}
          style={styles.media} accessibilityLabel={`${pet.name}的示意图`} />
      )}
      {caption ? <Text accessibilityLiveRegion="polite" style={styles.caption}>{caption}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stage: { width: '47%', maxWidth: 165, height: 195, alignSelf: 'flex-end' },
  media: { width: '100%', flex: 1 },
  caption: { fontSize: 10, lineHeight: 14, color: colors.secondary, textAlign: 'center' },
});

// 萌宠动图舞台（F14-5）：读取最新动图并轮询生成进度；不可用时回退现有分身舞台，不白屏。
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, StyleSheet, Text, View } from 'react-native';
import { api } from '../lib/api';
import type { MotionView } from '../lib/motion';
import { ApiError } from '../lib/session';
import { pollTask, type TaskSnapshot } from '../lib/task-poller';
import type { Submission } from './AvatarStage';
import { MotionPet } from './avatar/MotionPet';
import { colors } from '../theme';

const POLL_TIMEOUT_MS = 600_000;

export function MotionStage({ pet, health, emotionEvent, submission, fallback }: {
  pet: { id: number; name: string };
  health?: { state: string } | null;
  emotionEvent?: { id: string; emotion: string } | null;
  submission?: Submission;
  fallback: React.ReactNode;
}) {
  const [view, setView] = useState<MotionView | null>(null);
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState('');
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

  const fetchView = useCallback(async (signal?: AbortSignal): Promise<MotionView | null> => {
    try {
      return await api.authorized<MotionView>(`/pets/${pet.id}/motion`, { signal });
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
      const outcome = await pollTask(taskId, 'motion_batch', {
        fetchTask: (id, signal) => api.authorized<TaskSnapshot>(`/tasks/${id}`, { signal }),
        signal: controller.signal,
        timeoutMs: POLL_TIMEOUT_MS,
        isVisible: () => AppState.currentState === 'active',
      });
      if (!mounted.current || polling.current !== controller || outcome.kind !== 'settled') return;
      const next = await fetchView(controller.signal);
      if (!mounted.current || polling.current !== controller) return;
      setView(next);
      setNote(outcome.task.status === 'succeeded' ? '' : '萌宠动图生成失败，可重新上传照片再试。');
    } catch {
      if (mounted.current && polling.current === controller) setNote('查询生成进度失败，请稍后重试。');
    }
  }, [fetchView]);

  useEffect(() => {
    const controller = new AbortController();
    fetchView(controller.signal).then(next => {
      if (!mounted.current) return;
      setView(next);
      setLoading(false);
      if (next && (next.status === 'pending' || next.status === 'running')) void track(next.task_id);
    }).catch(() => { if (mounted.current) setLoading(false); });
    return () => controller.abort();
  }, [fetchView, track]);

  useEffect(() => {
    if (submission) void Promise.resolve().then(() => track(submission.taskId));
  }, [submission, track]);

  if (loading || !view?.usable) {
    return <>{fallback}</>;
  }
  return (
    <View style={styles.stage}>
      <MotionPet pet={pet} view={view} config={view.config} health={health} emotionEvent={emotionEvent} />
      {note ? <Text accessibilityLiveRegion="polite" style={styles.caption}>{note}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stage: { width: '54%', maxWidth: 160, marginTop: 5, marginBottom: 2 },
  caption: { fontSize: 10, lineHeight: 14, color: colors.secondary, textAlign: 'center' },
});

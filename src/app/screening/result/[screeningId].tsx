import { Link, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { Screen } from '../../../components/Screen';
import { api } from '../../../lib/api';
import { DISCLAIMER, STATE_LABELS, stateTone } from '../../../lib/screening';
import { cancelPetRechecks, scheduleRecheck } from '../../../lib/notifications';
import { buildRecheckReminder, shouldSchedule } from '../../../lib/recheck-reminder';
import { adviceNotice, shouldPollAdvice, type AdviceView } from '../../../lib/screening-advice';
import { ApiError } from '../../../lib/session';
import { pollTask } from '../../../lib/task-poller';
import { colors } from '../../../theme';

interface ScreeningDetail {
  screening_id: number; pet_id: number; state: string; redline_hit: boolean; redlines: string[];
  spirit: string; appetite: string; rules_version: string; created_at: string;
  symptoms: { code: string; label: string; duration: string | null; frequency: string | null; notes: string | null; severe: boolean; grade: string | null }[];
  media: { media_id: string; type: string }[];
  redline_card: { title: string; subtitle: string; preparation: string[] } | null;
  disclaimer: string; llm_advice: string | null;
  task_id: string | null; advice: AdviceView | null;
}

const GRADE_LABELS: Record<string, string> = { observe: '建议观察', vet: '建议就医' };
const TONE_COLORS = { ok: '#2E7D32', watch: '#B26A00', vet: '#B26A00', urgent: '#B3261E' } as const;

function formatTime(iso: string) {
  const value = /Z|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`;
  return new Date(value).toLocaleString();
}

export default function ScreeningResultScreen() {
  const { screeningId } = useLocalSearchParams<{ screeningId: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<ScreeningDetail | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reminderNotice, setReminderNotice] = useState<string | null>(null);
  const reminderHandled = useRef(new Set<number>());

  const load = useCallback(() => {
    api.authorized<ScreeningDetail>(`/screenings/${screeningId}`).then(next => { setDetail(next); setLoadFailed(false); }).catch(error => {
      if (error instanceof ApiError && error.status === 404) setProblem('未找到该初筛记录。');
      else setLoadFailed(true);
    });
  }, [screeningId]);
  useEffect(() => { load(); }, [load]);

  // 建议未就绪时按 screening_analysis 轮询（60 秒超时），结束后重拉详情取 ready/degraded。
  const polled = useRef(new Set<string>());
  useEffect(() => {
    if (!detail || !shouldPollAdvice(detail) || polled.current.has(detail.task_id!)) return;
    polled.current.add(detail.task_id!);
    const controller = new AbortController();
    void pollTask(detail.task_id!, 'screening_analysis', {
      fetchTask: id => api.authorized(`/tasks/${id}`),
      signal: controller.signal,
      isVisible: () => AppState.currentState === 'active',
    }).then(outcome => { if (outcome.kind !== 'aborted') load(); }).catch(() => {});
    return () => controller.abort();
  }, [detail, load]);

  // observe 结果注册 +24h 复查提醒（F06-2）；权限拒绝时应用内横幅降级（F10-3）。
  useEffect(() => {
    if (!detail || detail.state !== 'observe' || reminderHandled.current.has(detail.screening_id)) return;
    reminderHandled.current.add(detail.screening_id);
    let active = true;
    void (async () => {
      const pets = await api.authorized<{ id: number; name: string }[]>('/pets');
      const petName = pets.find(pet => pet.id === detail.pet_id)?.name ?? '猫咪';
      const reminder = buildRecheckReminder(detail, petName);
      if (!shouldSchedule(reminder, Date.now())) return;
      await cancelPetRechecks(detail.pet_id).catch(() => {});
      const outcome = await scheduleRecheck(reminder);
      if (!active) return;
      if (outcome === 'scheduled') setReminderNotice('已注册 24 小时后的复查提醒；提前复查会自动取消。');
      else setReminderNotice('通知权限未开启，复查提醒将以应用内横幅呈现；可在「我的」重新授权。');
    })().catch(() => {});
    return () => { active = false; };
  }, [detail]);

  const openMedia = async (mediaId: string) => {
    try {
      const ticket = await api.authorized<{ download_url: string }>(`/media/${mediaId}`);
      await Linking.openURL(ticket.download_url);
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : '无法打开存证媒体。');
    }
  };
  const removeMedia = async (mediaId: string) => {
    try {
      await api.authorized(`/screenings/${screeningId}/media/${mediaId}`, { method: 'DELETE' });
      setDetail(prev => prev ? { ...prev, media: prev.media.filter(item => item.media_id !== mediaId) } : prev);
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : '删除存证失败，请重试。');
    }
  };

  if (!detail) {
    return (
      <Screen>
        <Text accessibilityRole="header" style={styles.title}>初筛结果</Text>
        {problem ? <Text style={styles.problem}>{problem}</Text> : null}
        {loadFailed ? (
          <Pressable accessibilityRole="button" style={styles.primary} onPress={load}><Text style={styles.primaryText}>重试</Text></Pressable>
        ) : !problem ? <ActivityIndicator color={colors.brand} /> : null}
        <Link href="/health" style={styles.link}>返回健康</Link>
      </Screen>
    );
  }

  const tone = stateTone(detail.state);
  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>初筛结果</Text>
      <View style={[styles.stateCard, { borderColor: TONE_COLORS[tone] }]}>
        <Text style={[styles.stateText, { color: TONE_COLORS[tone] }]}>{STATE_LABELS[detail.state] ?? detail.state}</Text>
        <Text style={styles.subtitle}>{formatTime(detail.created_at)} · 规则版本 {detail.rules_version}</Text>
      </View>
      {reminderNotice ? (
        <View style={styles.reminderBanner}><Text style={styles.reminderText}>{reminderNotice}</Text></View>
      ) : null}
      {detail.redline_card ? (
        <View style={styles.redCard}>
          <Text style={styles.redTitle}>{detail.redline_card.title}</Text>
          <Text style={styles.redSubtitle}>{detail.redline_card.subtitle}</Text>
          <Text style={styles.redHeading}>就医准备</Text>
          {detail.redline_card.preparation.map((item, index) => (
            <Text key={item} style={styles.redItem}>{`${index + 1}. ${item}`}</Text>
          ))}
        </View>
      ) : null}
      {detail.symptoms.length > 0 ? (
        <View style={styles.card}>
          <Text style={styles.section}>症状与分级</Text>
          {detail.symptoms.map(symptom => (
            <View key={symptom.code} style={styles.symptomRow}>
              <Text style={styles.body}>{symptom.label}{symptom.severe ? '（严重）' : ''}</Text>
              <Text style={styles.grade}>{symptom.grade ? GRADE_LABELS[symptom.grade] ?? symptom.grade : '—'}</Text>
            </View>
          ))}
        </View>
      ) : null}
      {detail.media.length > 0 ? (
        <View style={styles.card}>
          <Text style={styles.section}>存证媒体</Text>
          {detail.media.map(item => (
            <View key={item.media_id} style={styles.symptomRow}>
              <Pressable accessibilityRole="button" onPress={() => void openMedia(item.media_id)}>
                <Text style={styles.link}>{item.type === 'video' ? '查看视频' : '查看照片'}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" onPress={() => void removeMedia(item.media_id)}>
                <Text style={styles.remove}>删除</Text>
              </Pressable>
            </View>
          ))}
        </View>
      ) : null}
      {detail.advice && (detail.advice.text || detail.advice.status === 'pending') ? (
        <View style={styles.card}>
          <Text style={styles.section}>AI 护理建议</Text>
          {adviceNotice(detail.advice) ? <Text style={styles.adviceNotice}>{adviceNotice(detail.advice)}</Text> : null}
          {detail.advice.text ? <Text style={styles.body}>{detail.advice.text}</Text> : null}
          {(detail.advice.tips ?? []).map((tip, index) => (
            <Text key={tip} style={styles.tip}>{`${index + 1}. ${tip}`}</Text>
          ))}
        </View>
      ) : null}
      <Text style={styles.disclaimer}>{detail.disclaimer || DISCLAIMER}</Text>
      {problem ? <Text accessibilityLiveRegion="polite" style={styles.problem}>{problem}</Text> : null}
      <Pressable accessibilityRole="button" style={styles.primary} onPress={() => router.replace(`/screening/history/${detail.pet_id}`)}>
        <Text style={styles.primaryText}>查看历史记录</Text>
      </Pressable>
      <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => router.replace('/health')}>
        <Text style={styles.secondaryText}>返回健康</Text>
      </Pressable>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  subtitle: { fontSize: 12, lineHeight: 18, color: colors.secondary, marginTop: 4 },
  body: { fontSize: 14, lineHeight: 20, color: colors.text, flexShrink: 1 },
  stateCard: { padding: 18, borderRadius: 18, backgroundColor: colors.surface, borderWidth: 2, gap: 4 },
  reminderBanner: { padding: 12, borderRadius: 12, backgroundColor: colors.soft },
  reminderText: { fontSize: 13, lineHeight: 20, color: colors.text },
  stateText: { fontSize: 22, fontWeight: '700' },
  redCard: { padding: 18, borderRadius: 18, backgroundColor: '#FDECEC', gap: 8 },
  redTitle: { fontSize: 20, fontWeight: '700', color: '#B3261E' },
  redSubtitle: { fontSize: 14, lineHeight: 21, color: '#7A1F1A' },
  redHeading: { fontSize: 14, fontWeight: '700', color: '#7A1F1A', marginTop: 4 },
  redItem: { fontSize: 13, lineHeight: 20, color: '#7A1F1A' },
  card: { padding: 16, borderRadius: 18, backgroundColor: colors.surface, gap: 10 },
  section: { fontSize: 15, fontWeight: '700', color: colors.text },
  symptomRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  grade: { fontSize: 13, fontWeight: '600', color: colors.secondary },
  adviceNotice: { fontSize: 13, lineHeight: 19, color: colors.secondary },
  tip: { fontSize: 13, lineHeight: 20, color: colors.text },
  link: { fontSize: 14, color: colors.text, textDecorationLine: 'underline', minHeight: 32, paddingVertical: 6 },
  remove: { fontSize: 13, color: '#B3261E', textDecorationLine: 'underline', paddingVertical: 6 },
  disclaimer: { fontSize: 12, lineHeight: 18, color: colors.secondary },
  problem: { fontSize: 13, lineHeight: 20, color: '#B3261E' },
  primary: { minHeight: 48, borderRadius: 14, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: colors.onBrand, fontWeight: '700', fontSize: 15 },
  secondary: { minHeight: 44, borderRadius: 12, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { color: colors.text, fontWeight: '600', fontSize: 14 },
});

// 聊聊页（T15/T16，FRD F09-1/2/3/4/5/6/7）：每宠一线程、同步人设回复、红线就医卡、
// 录音解读（1–60s→audio_interpret 45s 轮询→情绪+置信度气泡）、常驻免责、
// chat_cache 弱网镜像、文字失败入 retry_queue 自动补发（幂等键防重；音频不入队）。
import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type ScrollViewInstance } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioPlayer, useAudioRecorder, useAudioRecorderState } from 'expo-audio';
import { api } from '../../lib/api';
import { AUDIO_FOOTER, AUDIO_MAX_SECONDS, confidenceText, emotionLabel, recordingContentType, validateDuration } from '../../lib/audio-message';
import { CHAT_INPUT_MAX, chatQueueItem, confirmSend, localPendingId, parseChatBody, toCachedMessage, validateChatInput, type ChatGuidance, type ChatMessage } from '../../lib/chat';
import { mergeMessages, type CachedMessage } from '../../lib/chat-cache';
import { emotionBus } from '../../lib/chat-emotion';
import { getOfflineStore } from '../../lib/offline-store';
import { offlineSync } from '../../lib/offline-sync';
import { uploadMedia } from '../../lib/photo-upload';
import { QUOTA_EXHAUSTED_HINT, canUse, type QuotaSnapshot } from '../../lib/quota';
import { classifyFailure, generateKey } from '../../lib/retry-queue';
import { ApiError } from '../../lib/session';
import { pollTask, type TaskSnapshot } from '../../lib/task-poller';
import { colors } from '../../theme';

const DISCLAIMER = 'AI 结果仅供日常健康管理参考,不替代专业兽医诊断';

interface SendResult { user_message: ChatMessage; pet_message: ChatMessage; guidance: ChatGuidance | null }
interface AudioSendResult { task_id: string; user_message: ChatMessage; pet_message: null; guidance: null }

export default function ChatScreen() {
  const [pets, setPets] = useState<{ id: number; name: string }[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<CachedMessage[]>([]);
  const [nextBefore, setNextBefore] = useState<number | null>(null);
  const [guidance, setGuidance] = useState<ChatGuidance | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [recordingBusy, setRecordingBusy] = useState(false);
  const [playingUrl, setPlayingUrl] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaSnapshot>();
  const scrollRef = useRef<ScrollViewInstance>(null);
  const audioAbort = useRef<AbortController | null>(null);
  const autoStop = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recordStart = useRef(0);
  const recorder = useAudioRecorder({ ...RecordingPresets.HIGH_QUALITY, directory: 'document' });
  const recorderState = useAudioRecorderState(recorder);
  const player = useAudioPlayer(playingUrl ? { uri: playingUrl } : null);
  const selected = pets.find(pet => pet.id === selectedId) ?? pets[0];
  const selectedPetId = selected?.id;
  const pendingCount = messages.filter(message => message.pending).length;

  // 缓存优先渲染（AC-09-6 飞行模式可读历史），联网后合并服务端最新页。
  const loadHistory = useCallback(async (petId: number, sid: number | null) => {
    const store = await getOfflineStore();
    const cached = await store.chat.list(petId);
    const queue = await store.queue.list();
    const pending: CachedMessage[] = queue
      .filter(item => item.kind === 'chat_text' && item.petId === petId)
      .map(item => ({ id: localPendingId(item.idempotencyKey), role: 'user', kind: 'text',
                      content: parseChatBody(item).content, createdAt: item.createdAt, pending: true }));
    setMessages(mergeMessages(cached, pending));
    if (sid === null) return;
    try {
      const page = await api.authorized<{ items: ChatMessage[]; next_before: number | null }>(
        `/chat/sessions/${sid}/messages?limit=50`);
      const server = [...page.items].reverse().map(message => toCachedMessage(message));
      await store.chat.put(petId, server);
      setMessages(mergeMessages(mergeMessages(cached, server), pending));
      setNextBefore(page.next_before);
      setNotice(null);
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        setNotice('登录或授权已失效，请重新登录后再聊。');
      } else {
        setNotice('弱网模式：正在显示缓存历史，恢复联网后自动同步。');
      }
    }
  }, []);

  useFocusEffect(useCallback(() => {
    let active = true;
    api.authorized<{ id: number; name: string }[]>('/pets').then(items => {
      if (active) setPets(items);
    }).catch(() => { if (active) setPets([]); });
    api.authorized<QuotaSnapshot>('/quota').then(snapshot => { if (active) setQuota(snapshot); }).catch(() => {});
    void offlineSync.drainNow();
    return () => { active = false; };
  }, []));

  const openSession = useCallback(async (petId: number, isActive: () => boolean) => {
    try {
      const session = await api.authorized<{ session_id: number }>(`/pets/${petId}/chat/sessions`, { method: 'POST' });
      if (!isActive()) return;
      setSessionId(session.session_id);
      await loadHistory(petId, session.session_id);
    } catch {
      if (isActive()) { setSessionId(null); setNotice('聊天线程尚未就绪，弱网下仍可阅读缓存历史。'); }
    }
  }, [loadHistory]);

  // 切猫隔离（AC-09-1）：每宠独立线程，自动创建；中止进行中的录音轮询。
  useEffect(() => {
    if (!selectedPetId) {
      void Promise.resolve().then(() => { setSessionId(null); setMessages([]); });
      return;
    }
    let active = true;
    void Promise.resolve().then(() => { setGuidance(null); setNextBefore(null); setPlayingUrl(null); });
    void Promise.resolve().then(() => loadHistory(selectedPetId, null));
    void Promise.resolve().then(() => openSession(selectedPetId, () => active));
    return () => { active = false; };
  }, [selectedPetId, loadHistory, openSession]);

  // 补发成功后刷新历史与待同步状态（AC-07-5 ≤10s）。
  useEffect(() => offlineSync.subscribe(() => {
    if (selectedPetId) void loadHistory(selectedPetId, sessionId);
  }), [selectedPetId, sessionId, loadHistory]);

  useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [messages.length]);

  // 切猫/卸载：中止音频轮询、清理自动停止定时器、停止录音。
  useEffect(() => {
    return () => {
      audioAbort.current?.abort();
      if (autoStop.current) { clearTimeout(autoStop.current); autoStop.current = null; }
      if (recorder.isRecording) void recorder.stop();
    };
  }, [selectedPetId, recorder]);

  // 共享播放器：点击语音气泡切换音源并从头播放。
  useEffect(() => {
    if (playingUrl) { player.seekTo(0); player.play(); }
  }, [playingUrl, player]);

  const loadMore = async () => {
    if (!selected || sessionId === null || nextBefore === null || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.authorized<{ items: ChatMessage[]; next_before: number | null }>(
        `/chat/sessions/${sessionId}/messages?limit=50&before=${nextBefore}`);
      const older = [...page.items].reverse().map(message => toCachedMessage(message));
      const store = await getOfflineStore();
      await store.chat.put(selected.id, older);
      setMessages(prev => mergeMessages(prev, older));
      setNextBefore(page.next_before);
    } catch { /* 保留已有历史 */ } finally { setLoadingMore(false); }
  };

  const submit = async () => {
    const checked = validateChatInput(input);
    if (!checked.ok) { setNotice(checked.message); return; }
    if (!selected || sessionId === null) { setNotice('聊天线程尚未就绪，请稍后再试。'); return; }
    const store = await getOfflineStore();
    const key = generateKey();
    const localId = localPendingId(key);
    const optimistic: CachedMessage = { id: localId, role: 'user', kind: 'text', content: checked.value, createdAt: Date.now(), pending: true };
    setMessages(prev => mergeMessages(prev, [optimistic]));
    setInput('');
    setBusy(true);
    setNotice(null);
    setGuidance(null);
    try {
      const result = await api.authorized<SendResult>(`/chat/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
        body: JSON.stringify({ kind: 'text', content: checked.value }),
      });
      setMessages(prev => confirmSend(prev, localId, result.user_message, result.pet_message));
      await store.chat.put(selected.id, [toCachedMessage(result.user_message), toCachedMessage(result.pet_message)]);
      // F09-5：回复到达→首页分身播一次对应动作后回待机。
      if (result.pet_message.emotion_label) emotionBus.publish(selected.id, result.pet_message.emotion_label);
      setGuidance(result.guidance);
    } catch (error) {
      if (classifyFailure(error) === 'retry') {
        await store.queue.insert(chatQueueItem(selected.id, sessionId, checked.value, key, Date.now()));
        setNotice('网络不可用，消息已加入待同步，恢复联网后自动发送。');
      } else {
        setMessages(prev => prev.filter(message => message.id !== localId));
        setNotice(error instanceof ApiError ? error.message : '发送失败，请稍后重试。');
      }
    } finally {
      setBusy(false);
    }
  };

  // F09-3/4：停止录音→时长校验→presign 上传→音频消息 202→45s 轮询→刷新双气泡。
  const stopAndSend = useCallback(async () => {
    if (autoStop.current) { clearTimeout(autoStop.current); autoStop.current = null; }
    if (!recorder.isRecording) return;
    await recorder.stop();
    const uri = recorder.uri;
    const seconds = (Date.now() - recordStart.current) / 1000;
    const checked = validateDuration(seconds);
    if (!checked.ok) { setNotice(checked.message); return; }
    if (!selectedPetId || sessionId === null || !uri) { setNotice('聊天线程尚未就绪，录音未发送。'); return; }
    const petId = selectedPetId;
    const sid = sessionId;
    setRecordingBusy(true);
    setNotice(null);
    const controller = new AbortController();
    audioAbort.current = controller;
    try {
      const raw = await (await fetch(uri)).blob();
      const file = new Blob([raw], { type: recordingContentType(uri) });
      const mediaId = await uploadMedia(petId, file, 'audio', api.authorized, (url, init) => fetch(url, init), controller.signal);
      const result = await api.authorized<AudioSendResult>(`/chat/sessions/${sid}/messages`, {
        method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: 'audio', media_id: mediaId }),
      });
      const store = await getOfflineStore();
      setMessages(prev => mergeMessages(prev, [toCachedMessage(result.user_message)]));
      await store.chat.put(petId, [toCachedMessage(result.user_message)]);
      const outcome = await pollTask(result.task_id, 'audio_interpret', {
        fetchTask: id => api.authorized<TaskSnapshot>(`/tasks/${id}`),
        signal: controller.signal,
        isVisible: () => AppState.currentState === 'active',
      });
      if (outcome.kind === 'aborted') return;
      if (outcome.kind === 'settled' && outcome.task.status === 'succeeded') {
        const emotion = (outcome.task.result as { emotion?: string } | null)?.emotion;
        if (emotion && emotion !== 'unrecognized') emotionBus.publish(petId, emotion);
        await loadHistory(petId, sid);
      } else {
        setNotice('音频解读未成功，请稍后重试；文字聊天不受影响。');
        await loadHistory(petId, sid);
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      setNotice(error instanceof ApiError ? error.message : '录音上传失败，请重试；文字聊天不受影响。');
    } finally {
      setRecordingBusy(false);
      audioAbort.current = null;
    }
  }, [recorder, selectedPetId, sessionId, loadHistory]);

  const toggleRecording = async () => {
    if (Platform.OS === 'web') { setNotice('网页端暂不支持录音，请使用 App；文字聊天不受影响。'); return; }
    if (recorder.isRecording) { await stopAndSend(); return; }
    if (recordingBusy) return;
    if (!selectedPetId || sessionId === null) { setNotice('聊天线程尚未就绪，请稍后再试。'); return; }
    try {
      const status = await AudioModule.requestRecordingPermissionsAsync();
      if (!status.granted) { setNotice('未获得麦克风权限，可在系统设置中开启；文字聊天不受影响。'); return; }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      recordStart.current = Date.now();
      setNotice(null);
      autoStop.current = setTimeout(() => { void stopAndSend(); }, AUDIO_MAX_SECONDS * 1000);
    } catch {
      setNotice('无法开始录音，请重试；文字聊天不受影响。');
    }
  };

  const recordingSeconds = Math.min(AUDIO_MAX_SECONDS, Math.floor((recorderState.durationMillis ?? 0) / 1000));

  return (
    <SafeAreaView edges={['top', 'bottom']} style={styles.safe}>
      <View style={styles.header}>
        <Text accessibilityRole="header" style={styles.title}>聊聊</Text>
        {pets.length > 0 ? (
          <View style={styles.selector}>
            {pets.map(pet => (
              <Pressable key={pet.id} accessibilityRole="button" accessibilityState={{ selected: selected?.id === pet.id }}
                onPress={() => setSelectedId(pet.id)} style={[styles.pet, selected?.id === pet.id && styles.activePet]}>
                <Text style={styles.petText}>{selected?.id === pet.id ? '✓ ' : ''}{pet.name}</Text>
              </Pressable>
            ))}
          </View>
        ) : null}
      </View>
      {guidance && selected ? (
        <View style={styles.guidance} accessibilityLiveRegion="assertive">
          <Text style={styles.guidanceTitle}>{guidance.title}</Text>
          <Text style={styles.guidanceText}>{guidance.text}</Text>
          {guidance.route === 'screening' ? (
            <Link href={`/screening/${selected.id}`} style={styles.guidanceButton} accessibilityRole="button">去做初筛</Link>
          ) : null}
        </View>
      ) : null}
      {notice ? <Text accessibilityLiveRegion="polite" style={styles.notice}>{notice}</Text> : null}
      {pendingCount > 0 ? <Text style={styles.pendingBanner}>{pendingCount} 条待同步 · 恢复联网后自动发送</Text> : null}
      <ScrollView ref={scrollRef} style={styles.list} contentContainerStyle={styles.listContent}>
        {nextBefore !== null ? (
          <Pressable onPress={() => void loadMore()} disabled={loadingMore} accessibilityRole="button" style={styles.loadMore}>
            <Text style={styles.loadMoreText}>{loadingMore ? '加载中…' : '加载更早的消息'}</Text>
          </Pressable>
        ) : null}
        {messages.length === 0 ? (
          <Text style={styles.empty}>{selected ? `和${selected.name}说说话吧，它会用自己的方式回应你。` : '创建猫咪档案后，就可以和它聊聊了。'}</Text>
        ) : null}
        {messages.map(message => (
          <View key={message.id} style={[styles.bubbleRow, message.role === 'user' ? styles.userRow : styles.petRow]}>
            <View style={[styles.bubble, message.role === 'user' ? styles.userBubble : styles.petBubble, message.pending && styles.pendingBubble]}>
              {message.kind === 'audio' ? (
                <Pressable onPress={() => message.audioUrl && setPlayingUrl(message.audioUrl)} accessibilityRole="button"
                  accessibilityLabel="播放语音消息">
                  <Text style={styles.bubbleText}>🎤 语音消息{playingUrl !== null && playingUrl === message.audioUrl ? ' · 播放中' : ''}</Text>
                  <Text style={styles.audioHint}>{message.audioUrl ? '点击播放' : '音频暂不可用（弱网缓存）'}</Text>
                </Pressable>
              ) : (
                <Text style={styles.bubbleText}>{message.content}</Text>
              )}
              {message.role === 'pet' && message.taskId ? (
                <Text style={styles.emotionChip}>
                  {message.emotionLabel
                    ? `${emotionLabel(message.emotionLabel)} · ${confidenceText(message.emotionLabel, message.emotionConfidence)}`
                    : '未识别'}
                </Text>
              ) : null}
              {message.pending ? <Text style={styles.pendingTag}>待同步</Text> : null}
            </View>
          </View>
        ))}
      </ScrollView>
      <Text style={styles.disclaimer}>{DISCLAIMER}</Text>
      <Text style={styles.disclaimer}>{AUDIO_FOOTER}</Text>
      {recorderState.isRecording ? (
        <Text accessibilityLiveRegion="polite" style={styles.recordingBanner}>录音中… 点 ⏹ 停止并解读（最长 {AUDIO_MAX_SECONDS} 秒）</Text>
      ) : null}
      {!canUse(quota, 'chat_msg') ? <Text style={styles.notice}>{QUOTA_EXHAUSTED_HINT}（录音解读不占聊天配额。）</Text> : null}
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.inputRow}>
          <Pressable onPress={() => void toggleRecording()} disabled={recordingBusy} accessibilityRole="button"
            accessibilityLabel={recorderState.isRecording ? '停止录音并解读' : '开始录音'}
            style={[styles.mic, recordingBusy && styles.sendDisabled, recorderState.isRecording && styles.micActive]}>
            {recordingBusy ? <ActivityIndicator color={colors.text} /> : (
              <Text style={styles.micText}>{recorderState.isRecording ? `⏹ ${recordingSeconds}s` : '🎤'}</Text>
            )}
          </Pressable>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="说点什么…"
            placeholderTextColor={colors.secondary}
            multiline
            maxLength={CHAT_INPUT_MAX}
            accessibilityLabel="聊天输入框"
          />
          <Pressable onPress={() => void submit()} disabled={busy || !input.trim() || !canUse(quota, 'chat_msg')} accessibilityRole="button"
            accessibilityState={{ disabled: busy || !input.trim() || !canUse(quota, 'chat_msg') }}
            style={[styles.send, (busy || !input.trim() || !canUse(quota, 'chat_msg')) && styles.sendDisabled]}>
            {busy ? <ActivityIndicator color={colors.onBrand} /> : <Text style={styles.sendText}>发送</Text>}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: 20, paddingTop: 12, gap: 10 },
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  selector: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  pet: { minHeight: 40, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.surface },
  activePet: { backgroundColor: colors.soft },
  petText: { fontSize: 14, fontWeight: '600', color: colors.text },
  guidance: { marginHorizontal: 20, marginTop: 10, padding: 14, borderRadius: 16, backgroundColor: '#FDECEA', borderWidth: 1, borderColor: '#C0392B', gap: 6 },
  guidanceTitle: { fontSize: 16, fontWeight: '700', color: '#C0392B' },
  guidanceText: { fontSize: 13, lineHeight: 20, color: colors.text },
  guidanceButton: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 18, borderRadius: 12, backgroundColor: '#C0392B', color: '#FFFFFF', fontWeight: '700', overflow: 'hidden' },
  notice: { paddingHorizontal: 20, paddingTop: 8, fontSize: 13, lineHeight: 20, color: colors.secondary },
  pendingBanner: { paddingHorizontal: 20, paddingTop: 6, fontSize: 12, fontWeight: '600', color: '#C77E1F' },
  recordingBanner: { paddingHorizontal: 20, paddingTop: 6, fontSize: 12, fontWeight: '600', color: '#C0392B' },
  list: { flex: 1, marginTop: 8 },
  listContent: { paddingHorizontal: 20, paddingBottom: 12, gap: 10 },
  loadMore: { minHeight: 40, justifyContent: 'center', alignItems: 'center' },
  loadMoreText: { fontSize: 13, color: colors.text, textDecorationLine: 'underline' },
  empty: { fontSize: 14, lineHeight: 22, color: colors.secondary, textAlign: 'center', paddingVertical: 32 },
  bubbleRow: { flexDirection: 'row' },
  userRow: { justifyContent: 'flex-end' },
  petRow: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '78%', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 16, gap: 4 },
  userBubble: { backgroundColor: colors.soft },
  petBubble: { backgroundColor: colors.surface },
  pendingBubble: { opacity: 0.65 },
  bubbleText: { fontSize: 15, lineHeight: 22, color: colors.text },
  audioHint: { fontSize: 11, color: colors.secondary },
  emotionChip: { fontSize: 12, fontWeight: '600', color: '#7A5CC7' },
  pendingTag: { fontSize: 11, color: '#C77E1F', fontWeight: '600' },
  disclaimer: { paddingHorizontal: 20, paddingVertical: 3, fontSize: 11, lineHeight: 16, color: colors.secondary },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 10, paddingHorizontal: 20, paddingBottom: 10 },
  mic: { minHeight: 44, minWidth: 52, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 10, borderRadius: 16, backgroundColor: colors.surface },
  micActive: { backgroundColor: '#FDECEA' },
  micText: { fontSize: 15, fontWeight: '700', color: colors.text },
  input: { flex: 1, minHeight: 44, maxHeight: 120, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 16, backgroundColor: colors.surface, fontSize: 15, color: colors.text },
  send: { minHeight: 44, minWidth: 64, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 16, borderRadius: 16, backgroundColor: colors.brand },
  sendDisabled: { opacity: 0.5 },
  sendText: { fontSize: 15, fontWeight: '700', color: colors.onBrand },
});

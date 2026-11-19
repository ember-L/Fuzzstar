// 聊聊页（T15，FRD F09-1/2/5/6/7）：每宠一线程、同步人设回复、红线就医卡、
// 常驻免责、chat_cache 弱网镜像、文字失败入 retry_queue 自动补发（幂等键防重）。
import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type ScrollViewInstance } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '../../lib/api';
import { CHAT_INPUT_MAX, chatQueueItem, confirmSend, localPendingId, parseChatBody, toCachedMessage, validateChatInput, type ChatGuidance, type ChatMessage } from '../../lib/chat';
import { mergeMessages, type CachedMessage } from '../../lib/chat-cache';
import { emotionBus } from '../../lib/chat-emotion';
import { getOfflineStore } from '../../lib/offline-store';
import { offlineSync } from '../../lib/offline-sync';
import { classifyFailure, generateKey } from '../../lib/retry-queue';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

const DISCLAIMER = 'AI 结果仅供日常健康管理参考,不替代专业兽医诊断';

interface SendResult { user_message: ChatMessage; pet_message: ChatMessage; guidance: ChatGuidance | null }

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
  const scrollRef = useRef<ScrollViewInstance>(null);
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

  // 切猫隔离（AC-09-1）：每宠独立线程，自动创建。
  useEffect(() => {
    if (!selectedPetId) {
      void Promise.resolve().then(() => { setSessionId(null); setMessages([]); });
      return;
    }
    let active = true;
    void Promise.resolve().then(() => { setGuidance(null); setNextBefore(null); });
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
              <Text style={styles.bubbleText}>{message.content}</Text>
              {message.pending ? <Text style={styles.pendingTag}>待同步</Text> : null}
            </View>
          </View>
        ))}
      </ScrollView>
      <Text style={styles.disclaimer}>{DISCLAIMER}</Text>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.inputRow}>
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
          <Pressable onPress={() => void submit()} disabled={busy || !input.trim()} accessibilityRole="button"
            style={[styles.send, (busy || !input.trim()) && styles.sendDisabled]}>
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
  pendingTag: { fontSize: 11, color: '#C77E1F', fontWeight: '600' },
  disclaimer: { paddingHorizontal: 20, paddingVertical: 6, fontSize: 11, lineHeight: 16, color: colors.secondary },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 10, paddingHorizontal: 20, paddingBottom: 10 },
  input: { flex: 1, minHeight: 44, maxHeight: 120, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 16, backgroundColor: colors.surface, fontSize: 15, color: colors.text },
  send: { minHeight: 44, minWidth: 64, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 16, borderRadius: 16, backgroundColor: colors.brand },
  sendDisabled: { opacity: 0.5 },
  sendText: { fontSize: 15, fontWeight: '700', color: colors.onBrand },
});

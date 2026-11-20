// 首页分身播放器（T07）：附录 C 动作联动、个人片→占位片→静态呼吸回退、
// 仅 loop 边界切换 + 300ms 淡入淡出（150ms 出 + 150ms 入）、LRU 文件缓存。
import { useVideoPlayer, VideoView } from 'expo-video';
import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Animated, AppState, Pressable, StyleSheet } from 'react-native';
import { candidateFor, type AvatarView } from '../../lib/avatar';
import { decideAction, type ActionMap } from '../../lib/action-map';
import { createAssetCache } from '../../lib/asset-cache';
import { getAssetStore } from '../../lib/asset-store';
import { FADE_MS, initialPlayerState, reducePlayer } from '../../lib/player-machine';

export interface HealthInput { state: string; events?: string }
export interface EmotionEvent { id: string; emotion: string }

const STATIC_IMAGE = require('../../../assets/figma/59f10c90466cfa3aa84c0f88478dccedc8f69565.png');

export function AvatarPlayer({ pet, avatar, map, health, emotionEvent }: {
  pet: { id: number; name: string };
  avatar: AvatarView | null;
  map: ActionMap | null;
  health?: HealthInput | null;
  emotionEvent?: EmotionEvent | null;
}) {
  const [machine, dispatch] = useReducer(reducePlayer, undefined, () => initialPlayerState());
  const [storeReady, setStoreReady] = useState(false);
  const [resolved, setResolved] = useState<{ key: string; uri: string } | null>(null);
  const [displayUri, setDisplayUri] = useState<string | null>(null);
  const [playerStatus, setPlayerStatus] = useState('idle');
  const cache = useRef<ReturnType<typeof createAssetCache> | null>(null);
  const counters = useRef<Record<string, number>>({});
  const opacity = useMemo(() => new Animated.Value(1), []);
  const breath = useMemo(() => new Animated.Value(1), []);
  const switching = useRef(false);
  const prevTime = useRef(0);
  const personalKeys = useRef<Record<string, string>>({});

  const candidate = useMemo(
    () => candidateFor(machine.action, avatar, pet.id, machine.degraded),
    [machine.action, machine.degraded, avatar, pet.id],
  );

  useEffect(() => {
    let cancelled = false;
    getAssetStore().then(store => {
      if (cancelled) return;
      cache.current = createAssetCache(store.io);
      setStoreReady(true);
    }).catch(() => { /* 存储不可用时走远端/静态兜底 */ });
    return () => { cancelled = true; };
  }, []);

  // 健康待机联动（AC-04-4）：observe/vet/urgent → sick，一个 loop 边界内切换。
  useEffect(() => {
    const decision = decideAction(map, { health: health ?? { state: 'normal' } }, counters.current);
    void Promise.resolve().then(() => dispatch({ type: 'standby', action: decision.action }));
  }, [map, health]);

  // 聊天情绪一次性触发（T11 接线）：id 变化即新事件。
  useEffect(() => {
    if (!emotionEvent) return;
    const decision = decideAction(map, { emotion: emotionEvent.emotion }, counters.current);
    if (decision.source !== 'chat_emotion') return;
    counters.current.chat_emotion = (counters.current.chat_emotion ?? 0) + 1;
    void Promise.resolve().then(() => dispatch({ type: 'request', action: decision.action, oneShot: true }));
  }, [emotionEvent, map]);

  const interact = (gesture: 'tap' | 'long_press') => {
    const decision = decideAction(map, { gesture }, counters.current);
    if (decision.source !== 'interaction') return;
    counters.current.interaction = (counters.current.interaction ?? 0) + 1;
    dispatch({ type: 'request', action: decision.action, oneShot: true });
  };

  // 个人片版本到达/更新 → 下一 loop 边界无缝替换（AC-03-5），并清除该动作降级。
  useEffect(() => {
    if (!avatar) return;
    for (const [action, clip] of Object.entries(avatar.clips)) {
      if (clip.status !== 'ready' || !clip.url) continue;
      const key = clip.version_id ?? 'v0';
      if (personalKeys.current[action] === key) continue;
      personalKeys.current[action] = key;
      void Promise.resolve().then(() => dispatch({ type: 'upgrade', action }));
    }
  }, [avatar]);

  // 解析当前动作候选：缓存命中/下载；失败沿回退链降级（AC-03-6 不白屏）。
  useEffect(() => {
    if (candidate.kind === 'static' || !candidate.key || !candidate.url) {
      void Promise.resolve().then(() => setResolved(null));
      return;
    }
    if (!storeReady || !cache.current) return;
    let cancelled = false;
    const key = candidate.key;
    const kind = candidate.kind;
    cache.current.resolve(key, candidate.url).then(asset => {
      if (cancelled) return;
      if (asset) setResolved({ key, uri: asset.uri });
      else dispatch({ type: 'error', kind });
    }).catch(() => {
      if (!cancelled) dispatch({ type: 'error', kind });
    });
    return () => { cancelled = true; };
  }, [candidate, storeReady]);

  // 错误降级立即切换；静态兜底时没有 loop 可等，pending 立即生效。
  useEffect(() => {
    if (machine.urgent || (machine.pending && candidate.kind === 'static' && !machine.fading)) {
      void Promise.resolve().then(() => dispatch({ type: 'loopEnd' }));
    }
  }, [machine.urgent, machine.pending, machine.fading, candidate.kind]);

  const player = useVideoPlayer(displayUri, setup => { setup.loop = true; setup.muted = true; });

  useEffect(() => {
    prevTime.current = 0;
    const statusSub = player.addListener('statusChange', ({ status }) => {
      setPlayerStatus(status);
      if (status === 'error') dispatch({ type: 'error', kind: candidate.kind });
    });
    // loop 回绕检测：只在完整播放一圈后触发切换，动作中途不穿帮。
    const timeSub = player.addListener('timeUpdate', ({ currentTime }) => {
      const prev = prevTime.current;
      prevTime.current = currentTime;
      if (prev > 0.5 && currentTime < prev - 0.3) dispatch({ type: 'loopEnd' });
    });
    return () => { statusSub.remove(); timeSub.remove(); };
  }, [player, candidate.kind]);

  useEffect(() => {
    const sync = () => { if (AppState.currentState === 'active') player.play(); else player.pause(); };
    sync();
    const sub = AppState.addEventListener('change', sync);
    return () => { sub.remove(); player.pause(); };
  }, [player]);

  // 淡出 150ms → 换源 → 就绪后淡入 150ms（合计 300ms，仅 loop 边界/降级触发）。
  useEffect(() => {
    if (!machine.fading || switching.current) return;
    const target = candidate.kind === 'static' ? null
      : resolved && resolved.key === candidate.key ? resolved.uri : candidate.url;
    if (target === displayUri) { dispatch({ type: 'fadeDone' }); return; }
    switching.current = true;
    Animated.timing(opacity, { toValue: 0, duration: FADE_MS / 2, useNativeDriver: true }).start(() => {
      if (target !== null) setPlayerStatus('idle'); // 等新源就绪后再淡入，避免空帧
      setDisplayUri(target);
    });
  }, [machine.fading, candidate, resolved, displayUri, opacity]);

  // 首次起播：静态兜底画面上缓存就绪后淡入占位/个人片（AC-03-1 提交后 5s 内首帧）。
  useEffect(() => {
    if (switching.current || machine.fading || displayUri !== null) return;
    if (!resolved || resolved.key !== candidate.key || candidate.kind === 'static') return;
    switching.current = true;
    const uri = resolved.uri;
    Animated.timing(opacity, { toValue: 0, duration: FADE_MS / 2, useNativeDriver: true }).start(() => {
      setPlayerStatus('idle');
      setDisplayUri(uri);
    });
  }, [resolved, candidate, displayUri, machine.fading, opacity]);

  useEffect(() => {
    if (!switching.current) return;
    if (displayUri !== null && playerStatus !== 'readyToPlay' && playerStatus !== 'playing') return;
    Animated.timing(opacity, { toValue: 1, duration: FADE_MS / 2, useNativeDriver: true }).start(() => {
      switching.current = false;
      dispatch({ type: 'fadeDone' });
    });
  }, [displayUri, playerStatus, opacity]);

  // 静态兜底呼吸缩放（F03-6）。
  useEffect(() => {
    if (displayUri !== null) return;
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(breath, { toValue: 1.03, duration: 1200, useNativeDriver: true }),
      Animated.timing(breath, { toValue: 1, duration: 1200, useNativeDriver: true }),
    ]));
    loop.start();
    return () => { loop.stop(); breath.setValue(1); };
  }, [displayUri, breath]);

  return (
    <Pressable
      style={styles.stage}
      onPress={() => interact('tap')}
      onLongPress={() => interact('long_press')}
      accessibilityLabel={`${pet.name}的分身，点按或长按互动`}
      accessibilityRole="image"
    >
      <Animated.View style={[styles.mediaWrap, { opacity }]}>
        {displayUri ? (
          <VideoView player={player} style={styles.media} contentFit="contain" nativeControls={false} />
        ) : (
          <Animated.Image source={STATIC_IMAGE} style={[styles.media, { transform: [{ scale: breath }] }]} />
        )}
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  stage: { width: '100%', height: '100%' },
  mediaWrap: { width: '100%', flex: 1 },
  media: { width: '100%', height: '100%' },
});

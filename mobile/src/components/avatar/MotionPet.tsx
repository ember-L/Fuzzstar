// 萌宠动图播放器（F14-2/3/4）：GIF 循环播放、手势换一次性动作、健康状态决定待机动作。
// 切换 300ms 淡入淡出；GIF 播完由计时器收尾回待机，不依赖 loop 事件。
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Animated, PanResponder, Pressable, StyleSheet, Text, View } from 'react-native';
import {
  actionLabel, emotionActions, gifUrl, initialMotionState, MOTION_FADE_MS, oneShotMs,
  reduceMotion, standbyFor, statusLabel, type MotionConfig, type MotionView,
} from '../../lib/motion';
import { colors } from '../../theme';

const STATIC_IMAGE = require('../../../assets/figma/59f10c90466cfa3aa84c0f88478dccedc8f69565.png');
const REPLY_MS = 2200;
const SWIPE_MIN = 30;

export function MotionPet({ pet, view, config, health, emotionEvent }: {
  pet: { id: number; name: string };
  view: MotionView | null;
  config: MotionConfig | null;
  health?: { state: string } | null;
  emotionEvent?: { id: string; emotion: string } | null;
}) {
  const standby = standbyFor(config, health?.state);
  const [machine, dispatch] = useReducer(reduceMotion, standby, initialMotionState);
  const [broken, setBroken] = useState<Record<string, boolean>>({});
  const [display, setDisplay] = useState<string | null>(null);
  const lastEmotion = useRef<string | null>(null);
  const opacity = useMemo(() => new Animated.Value(1), []);

  // 健康待机联动（F14-3）：状态变化只改待机目标，一次性动作播完再切。
  useEffect(() => {
    dispatch({ type: 'standby', action: standby });
  }, [standby]);

  useEffect(() => {
    if (!machine.oneShot) return;
    const timer = setTimeout(() => dispatch({ type: 'settle' }), oneShotMs(config, view, machine.action));
    return () => clearTimeout(timer);
  }, [machine.oneShot, machine.action, config, view]);

  useEffect(() => {
    if (!machine.reply) return;
    const timer = setTimeout(() => dispatch({ type: 'clearReply' }), REPLY_MS);
    return () => clearTimeout(timer);
  }, [machine.reply]);

  useEffect(() => {
    if (!emotionEvent || lastEmotion.current === emotionEvent.id) return;
    lastEmotion.current = emotionEvent.id;
    const actions = emotionActions(config, emotionEvent.emotion);
    if (actions.length === 0) return;
    dispatch({ type: 'gesture', key: `emotion:${emotionEvent.emotion}`, actions, replies: [''] });
  }, [emotionEvent, config]);

  const interact = useCallback((gesture: string) => {
    const rule = config?.gestures?.[gesture];
    if (!rule) return;
    dispatch({ type: 'gesture', key: gesture, actions: rule.actions, replies: rule.replies });
  }, [config]);

  // 左右滑动只做手势方向判定，纵向滚动仍交给外层。
  const pan = useMemo(() => PanResponder.create({
    onMoveShouldSetPanResponder: (_event, gesture) =>
      Math.abs(gesture.dx) > 12 && Math.abs(gesture.dx) > Math.abs(gesture.dy),
    onPanResponderRelease: (_event, gesture) => {
      if (gesture.dx <= -SWIPE_MIN) interact('swipe_left');
      else if (gesture.dx >= SWIPE_MIN) interact('swipe_right');
    },
  }), [interact]);

  const candidate = broken[machine.action] ? null : gifUrl(view, machine.action);
  const source = candidate ?? (broken.base ? null : view?.base_image?.url ?? null);

  useEffect(() => {
    if (source === display) return;
    Animated.timing(opacity, { toValue: 0, duration: MOTION_FADE_MS / 2, useNativeDriver: true }).start(() => {
      setDisplay(source);
      Animated.timing(opacity, { toValue: 1, duration: MOTION_FADE_MS / 2, useNativeDriver: true }).start();
    });
  }, [source, display, opacity]);

  const status = statusLabel(config, health?.state);
  const action = actionLabel(config, machine.action);

  return (
    <Pressable
      style={styles.stage}
      onPress={() => interact('tap')}
      onLongPress={() => interact('long_press')}
      accessibilityLabel={`${pet.name}的萌宠动图，点按、长按或左右滑动互动`}
      accessibilityRole="image"
    >
      <View style={styles.mediaWrap} {...pan.panHandlers}>
        <Animated.View style={[styles.mediaWrap, { opacity }]}>
          {display ? (
            <Animated.Image
              source={{ uri: display }}
              style={styles.media}
              resizeMode="contain"
              onError={() => setBroken(prev => (candidate ? { ...prev, [machine.action]: true } : { ...prev, base: true }))}
            />
          ) : (
            <Animated.Image source={STATIC_IMAGE} style={styles.media} resizeMode="contain" />
          )}
        </Animated.View>
        {machine.reply ? (
          <View style={styles.replyBubble}>
            <Text style={styles.replyText} numberOfLines={2}>{machine.reply}</Text>
          </View>
        ) : null}
      </View>
      {status ? (
        <Text style={styles.caption}>{status} · {action}</Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  stage: { flex: 1, width: '100%' },
  mediaWrap: { flex: 1, width: '100%', justifyContent: 'flex-end' },
  media: { width: '100%', flex: 1 },
  replyBubble: {
    position: 'absolute', left: 0, right: 0, bottom: 2, paddingHorizontal: 8, paddingVertical: 5,
    borderRadius: 10, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border,
  },
  replyText: { fontSize: 10, lineHeight: 14, color: colors.text, textAlign: 'center' },
  caption: { fontSize: 10, lineHeight: 14, color: colors.secondary, textAlign: 'center', marginTop: 2 },
});

import { useLocalSearchParams, useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { cancelPetRechecks } from '../../lib/notifications';
import { MediaUploadError, uploadMedia } from '../../lib/photo-upload';
import { buildPayload, emptyForm, mediaLimitError, missingFields, type ScreeningForm, type SymptomsConfig } from '../../lib/screening';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

const SPIRIT_LABELS: Record<string, string> = { normal: '精神正常', slightly_down: '轻度沉郁', markedly_down: '明显沉郁' };
const APPETITE_LABELS: Record<string, string> = { normal: '食欲正常', decreased: '食欲下降', refused: '拒食' };
const DURATION_LABELS: Record<string, string> = { '<2h': '不到 2 小时', '2-12h': '2–12 小时', '12-24h': '12–24 小时', '>24h': '超过 24 小时' };
const FREQUENCY_LABELS: Record<string, string> = { '1': '1 次', '2-3': '2–3 次', '4-6': '4–6 次', '>6': '超过 6 次' };

type PendingMedia = { key: string; kind: 'photo' | 'video'; uri: string; file: Blob };

export default function ScreeningScreen() {
  const { petId } = useLocalSearchParams<{ petId: string }>();
  const router = useRouter();
  const id = Number(petId);
  const [config, setConfig] = useState<SymptomsConfig | null>(null);
  const [form, setForm] = useState<ScreeningForm>(emptyForm);
  const [pending, setPending] = useState<PendingMedia[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const loadConfig = useCallback(() => {
    api.authorized<SymptomsConfig>('/config/symptoms').then(next => { setConfig(next); setLoadFailed(false); }).catch(() => setLoadFailed(true));
  }, []);
  useEffect(() => { loadConfig(); }, [loadConfig]);
  useEffect(() => () => { abortRef.current?.abort(); }, []);

  const fieldLabel = (field: string) => {
    if (field === 'spirit') return '精神状态';
    if (field === 'appetite') return '食欲';
    const [code, part] = field.split('.');
    const label = config?.symptoms.find(s => s.code === code)?.label ?? code;
    return `${label}${part === 'frequency' ? '的发生频次' : '的持续时间'}`;
  };

  const toggleSymptom = (code: string) => {
    setForm(prev => {
      const symptoms = { ...prev.symptoms };
      if (symptoms[code]) delete symptoms[code];
      else symptoms[code] = { duration: null, frequency: null, notes: '', severe: false };
      return { ...prev, symptoms };
    });
  };
  const patchSymptom = (code: string, patch: Partial<ScreeningForm['symptoms'][string]>) => {
    setForm(prev => ({ ...prev, symptoms: { ...prev.symptoms, [code]: { ...prev.symptoms[code], ...patch } } }));
  };
  const toggleRedline = (code: string) => {
    setForm(prev => ({ ...prev, redlineOptions: prev.redlineOptions.includes(code)
      ? prev.redlineOptions.filter(item => item !== code) : [...prev.redlineOptions, code] }));
  };

  const pickMedia = async (kind: 'photo' | 'video') => {
    if (busy) return;
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: kind === 'photo' ? ['images'] : ['videos'],
      videoMaxDuration: 30,
    });
    if (result.canceled) return;
    const asset = result.assets[0];
    try {
      const response = await fetch(asset.uri);
      const raw = await response.blob();
      const type = asset.mimeType ?? (kind === 'photo' ? 'image/jpeg' : 'video/mp4');
      const file = raw.type ? raw : new Blob([raw], { type });
      setPending(prev => [...prev, { key: `${Date.now()}-${prev.length}`, kind, uri: asset.uri, file }]);
      setProblem(null);
    } catch {
      setProblem('无法读取所选文件，请重试。');
    }
  };

  const submit = async () => {
    if (!config || busy) return;
    const missing = missingFields(config, form);
    if (missing.length > 0) { setProblem(`请完善：${missing.map(fieldLabel).join('、')}。`); return; }
    const limit = mediaLimitError(pending);
    if (limit) { setProblem(limit); return; }
    setBusy(true);
    setProblem(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const mediaIds: string[] = [];
      for (const item of pending) {
        mediaIds.push(await uploadMedia(id, item.file, item.kind, api.authorized, (url, init) => fetch(url, init), controller.signal));
      }
      const payload = { ...buildPayload(form), media_ids: mediaIds };
      const result = await api.authorized<{ screening_id: number }>(`/pets/${id}/screenings`, {
        method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      // 复查完成（F06-3 / AC-10-1）：取消该猫全部待触发的复查提醒，新结果页按需重新注册。
      await cancelPetRechecks(id).catch(() => {});
      router.replace(`/screening/result/${result.screening_id}`);
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError || error instanceof MediaUploadError) setProblem(error.message);
      else setProblem('提交失败，请检查网络后重试。');
      setBusy(false);
    }
  };

  if (!config) {
    return (
      <Screen>
        <Text accessibilityRole="header" style={styles.title}>健康初筛</Text>
        {loadFailed ? (
          <View style={styles.card}>
            <Text style={styles.body}>问卷配置加载失败。</Text>
            <Pressable accessibilityRole="button" style={styles.primary} onPress={loadConfig}><Text style={styles.primaryText}>重试</Text></Pressable>
          </View>
        ) : <ActivityIndicator color={colors.brand} />}
      </Screen>
    );
  }

  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>健康初筛</Text>
      <Text style={styles.subtitle}>必填项完成后即可提交；存证照片／视频可选。</Text>

      <View style={styles.card}>
        <Text style={styles.section}>精神状态（必答）</Text>
        <View style={styles.chips}>
          {config.spirit_options.map(option => (
            <Pressable key={option} accessibilityRole="button" accessibilityState={{ selected: form.spirit === option }}
              style={[styles.chip, form.spirit === option && styles.chipActive]} onPress={() => setForm(prev => ({ ...prev, spirit: option }))}>
              <Text style={styles.chipText}>{SPIRIT_LABELS[option] ?? option}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.section}>食欲（必答）</Text>
        <View style={styles.chips}>
          {config.appetite_options.map(option => (
            <Pressable key={option} accessibilityRole="button" accessibilityState={{ selected: form.appetite === option }}
              style={[styles.chip, form.appetite === option && styles.chipActive]} onPress={() => setForm(prev => ({ ...prev, appetite: option }))}>
              <Text style={styles.chipText}>{APPETITE_LABELS[option] ?? option}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.section}>症状（可多选）</Text>
        <View style={styles.chips}>
          {config.symptoms.map(spec => (
            <Pressable key={spec.code} accessibilityRole="button" accessibilityState={{ selected: Boolean(form.symptoms[spec.code]) }}
              style={[styles.chip, form.symptoms[spec.code] && styles.chipActive]} onPress={() => toggleSymptom(spec.code)}>
              <Text style={styles.chipText}>{spec.label}</Text>
            </Pressable>
          ))}
        </View>
        {config.symptoms.filter(spec => form.symptoms[spec.code]).map(spec => {
          const answer = form.symptoms[spec.code];
          return (
            <View key={spec.code} style={styles.followup}>
              <Text style={styles.followupTitle}>{spec.label} · 持续时间（必答）</Text>
              <View style={styles.chips}>
                {config.duration_bands.map(band => (
                  <Pressable key={band} accessibilityRole="button" accessibilityState={{ selected: answer.duration === band }}
                    style={[styles.chip, answer.duration === band && styles.chipActive]} onPress={() => patchSymptom(spec.code, { duration: band })}>
                    <Text style={styles.chipText}>{DURATION_LABELS[band] ?? band}</Text>
                  </Pressable>
                ))}
              </View>
              {spec.frequency ? (
                <>
                  <Text style={styles.followupTitle}>发生频次（必答）</Text>
                  <View style={styles.chips}>
                    {config.frequency_bands.map(band => (
                      <Pressable key={band} accessibilityRole="button" accessibilityState={{ selected: answer.frequency === band }}
                        style={[styles.chip, answer.frequency === band && styles.chipActive]} onPress={() => patchSymptom(spec.code, { frequency: band })}>
                        <Text style={styles.chipText}>{FREQUENCY_LABELS[band] ?? band}</Text>
                      </Pressable>
                    ))}
                  </View>
                </>
              ) : null}
              {spec.severe_label ? (
                <View style={styles.switchRow}>
                  <Text style={styles.body}>{spec.severe_label}</Text>
                  <Switch value={answer.severe} onValueChange={value => patchSymptom(spec.code, { severe: value })} />
                </View>
              ) : null}
              <TextInput style={styles.notes} value={answer.notes} maxLength={config.notes_max} multiline
                placeholder={`补充说明（可选，${config.notes_max} 字以内）`} placeholderTextColor={colors.secondary}
                onChangeText={text => patchSymptom(spec.code, { notes: text })} />
            </View>
          );
        })}
      </View>

      <View style={styles.card}>
        <Text style={styles.section}>紧急信号（如有请勾选）</Text>
        <Text style={styles.subtitle}>命中任一紧急信号将直接建议立即就医。</Text>
        {config.redlines.map(spec => (
          <View key={spec.code} style={styles.redline}>
            <Text style={styles.followupTitle}>{spec.label}</Text>
            {spec.options ? (
              <View style={styles.chips}>
                {spec.options.map(option => (
                  <Pressable key={option.code} accessibilityRole="button" accessibilityState={{ selected: form.redlineOptions.includes(option.code) }}
                    style={[styles.chip, form.redlineOptions.includes(option.code) && styles.chipDanger]} onPress={() => toggleRedline(option.code)}>
                    <Text style={styles.chipText}>{option.label}</Text>
                  </Pressable>
                ))}
              </View>
            ) : (
              <Text style={styles.subtitle}>呕吐持续超过 24 小时会自动判定，无需勾选。</Text>
            )}
          </View>
        ))}
      </View>

      <View style={styles.card}>
        <Text style={styles.section}>存证（可选）</Text>
        <Text style={styles.subtitle}>照片最多 3 张（≤10 MiB），视频最多 1 段（≤30 秒、≤50 MiB）。</Text>
        <View style={styles.row}>
          <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => void pickMedia('photo')}><Text style={styles.secondaryText}>添加照片</Text></Pressable>
          <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => void pickMedia('video')}><Text style={styles.secondaryText}>添加视频</Text></Pressable>
        </View>
        {pending.map(item => (
          <View key={item.key} style={styles.switchRow}>
            <Text style={styles.body}>{item.kind === 'photo' ? '照片' : '视频'} · {(item.file.size / (1024 * 1024)).toFixed(1)} MiB</Text>
            <Pressable accessibilityRole="button" onPress={() => setPending(prev => prev.filter(entry => entry.key !== item.key))}>
              <Text style={styles.remove}>移除</Text>
            </Pressable>
          </View>
        ))}
      </View>

      {problem ? <Text accessibilityLiveRegion="polite" style={styles.problem}>{problem}</Text> : null}
      <Pressable accessibilityRole="button" style={[styles.primary, busy && styles.disabled]} disabled={busy} onPress={() => void submit()}>
        {busy ? <ActivityIndicator color={colors.onBrand} /> : <Text style={styles.primaryText}>提交初筛</Text>}
      </Pressable>
      <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => router.back()}><Text style={styles.secondaryText}>返回</Text></Pressable>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '700', color: colors.onBrand },
  subtitle: { fontSize: 13, lineHeight: 20, color: colors.secondary, marginTop: 4 },
  body: { fontSize: 14, lineHeight: 20, color: colors.text, flexShrink: 1 },
  card: { padding: 16, borderRadius: 18, backgroundColor: colors.surface, gap: 10 },
  section: { fontSize: 15, fontWeight: '700', color: colors.text },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 40, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 10, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border },
  chipActive: { backgroundColor: colors.soft, borderColor: colors.brand },
  chipDanger: { backgroundColor: '#FDECEC', borderColor: '#B3261E' },
  chipText: { fontSize: 13, color: colors.text },
  followup: { marginTop: 6, padding: 12, borderRadius: 12, backgroundColor: colors.background, gap: 8 },
  followupTitle: { fontSize: 13, fontWeight: '600', color: colors.text },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  notes: { minHeight: 60, borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 10, fontSize: 13, color: colors.text, textAlignVertical: 'top' },
  redline: { gap: 6 },
  row: { flexDirection: 'row', gap: 10 },
  primary: { minHeight: 48, borderRadius: 14, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: colors.onBrand, fontWeight: '700', fontSize: 15 },
  secondary: { minHeight: 44, borderRadius: 12, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 14 },
  secondaryText: { color: colors.text, fontWeight: '600', fontSize: 14 },
  disabled: { opacity: 0.6 },
  problem: { fontSize: 13, lineHeight: 20, color: '#B3261E' },
  remove: { fontSize: 13, color: '#B3261E', textDecorationLine: 'underline' },
});

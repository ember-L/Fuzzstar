import { useLocalSearchParams, useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { File } from 'expo-file-system';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { Button } from '../../components/ui/Button';
import { EntryRow } from '../../components/ui/EntryRow';
import { api } from '../../lib/api';
import { cancelPetRechecks } from '../../lib/notifications';
import { MediaUploadError, uploadMedia, type MediaSource } from '../../lib/photo-upload';
import { buildPayload, emptyForm, mediaLimitError, missingFields, type ScreeningForm, type SymptomsConfig } from '../../lib/screening';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

const SPIRIT_LABELS: Record<string, string> = { normal: '精神正常', slightly_down: '轻度沉郁', markedly_down: '明显沉郁' };
const APPETITE_LABELS: Record<string, string> = { normal: '食欲正常', decreased: '食欲下降', refused: '拒食' };
const DURATION_LABELS: Record<string, string> = { '<2h': '不到 2 小时', '2-12h': '2–12 小时', '12-24h': '12–24 小时', '>24h': '超过 24 小时' };
const FREQUENCY_LABELS: Record<string, string> = { '1': '1 次', '2-3': '2–3 次', '4-6': '4–6 次', '>6': '超过 6 次' };

type PendingMedia = { key: string; kind: 'photo' | 'video'; file: MediaSource };

export default function ScreeningScreen() {
  const { petId } = useLocalSearchParams<{ petId: string }>();
  const router = useRouter();
  const id = Number(petId);
  const [stage, setStage] = useState<'intro' | 'form'>('intro');
  const [petName, setPetName] = useState('猫咪');
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
  useEffect(() => {
    api.authorized<{ name: string }>(`/pets/${id}`).then(pet => setPetName(pet.name)).catch(() => {});
  }, [id]);
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
      // SDK 58 的全局 fetch 只接受 Blob / 带 bytes() 的 File，{ uri } 描述会被拒绝。
      const file = new File(asset.uri);
      if (file.size <= 0) { setProblem('无法读取所选文件，请重新选择。'); return; }
      setPending(prev => [...prev, { key: `${Date.now()}-${prev.length}`, kind, file }]);
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

  const header = (
    <View style={styles.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={styles.back}>
        <Text style={styles.backText}>‹</Text>
      </Pressable>
      <Text accessibilityRole="header" style={styles.headerTitle}>健康初筛</Text>
      <View style={styles.backSpacer} />
    </View>
  );

  // 入口确认屏（Figma 23:394）：对象确认＋初筛说明＋紧急提示。
  if (stage === 'intro') {
    return (
      <Screen>
        {header}
        <View style={styles.subjectCard}>
          <Image source={require('../../../assets/figma/cat-avatar.png')} style={styles.subjectAvatar} />
          <View style={styles.subjectTexts}>
            <Text style={styles.subjectLabel}>本次初筛对象</Text>
            <Text style={styles.subjectName}>{petName}</Text>
          </View>
          <View style={styles.subjectTag}><Text style={styles.subjectTagText}>当前猫咪</Text></View>
        </View>
        <Text style={styles.introTitle}>{`花 1 分钟，看看${petName}的状态`}</Text>
        <Text style={styles.introBody}>{'回答几个简短问题，记录精神、食欲和身体信号。\n这不是诊断，而是一份可随时给兽医看的记录。'}</Text>
        <View style={styles.stepsCard}>
          {[
            { num: '01', title: '精神状态', desc: '是否活跃、躲藏或反应变慢' },
            { num: '02', title: '食欲变化', desc: '吃多吃少，或者完全不吃' },
            { num: '03', title: '身体症状', desc: '呕吐、排泄、饮水、呼吸等异常' },
          ].map(step => (
            <View key={step.num} style={styles.step}>
              <Text style={styles.stepNum}>{step.num}</Text>
              <View style={styles.stepTexts}>
                <Text style={styles.stepTitle}>{step.title}</Text>
                <Text style={styles.stepDesc}>{step.desc}</Text>
              </View>
            </View>
          ))}
        </View>
        <Text style={styles.durationNote}>◷  约 1 分钟 · 每天可做一次</Text>
        <Button title="开始健康初筛" onPress={() => setStage('form')} />
        <EntryRow icon="alert" iconColor={colors.danger} backgroundColor={colors.dangerBg}
          title="出现紧急症状？" subtitle="立即查看需要及时就医的信号"
          onPress={() => setStage('form')} style={styles.emergencyRow} />
        <Text style={styles.introDisclaimer}>初筛结果仅供日常健康管理参考，不替代专业兽医诊断。</Text>
      </Screen>
    );
  }

  if (!config) {
    return (
      <Screen>
        {header}
        {loadFailed ? (
          <View style={styles.card}>
            <Text style={styles.body}>问卷配置加载失败。</Text>
            <Button title="重试" onPress={loadConfig} />
          </View>
        ) : <ActivityIndicator color={colors.brand} />}
      </Screen>
    );
  }

  return (
    <Screen>
      {header}
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
                placeholder={`补充说明（可选，${config.notes_max} 字以内）`} placeholderTextColor={colors.disabledText}
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
          <Button title="添加照片" variant="secondary" onPress={() => void pickMedia('photo')} style={styles.half} />
          <Button title="添加视频" variant="secondary" onPress={() => void pickMedia('video')} style={styles.half} />
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
      <Button title="提交初筛" busy={busy} onPress={() => void submit()} />
      <Button title="返回" variant="secondary" onPress={() => router.back()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  back: { width: 38, height: 38, borderRadius: 19, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' },
  backText: { fontSize: 26, lineHeight: 30, color: colors.text, marginTop: -2 },
  backSpacer: { width: 38 },
  headerTitle: { fontSize: 19, fontWeight: '600', color: colors.text },
  subjectCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.surfaceRaised, borderRadius: 16, padding: 12, minHeight: 88 },
  subjectAvatar: { width: 64, height: 64, borderRadius: 32 },
  subjectTexts: { flex: 1, gap: 2 },
  subjectLabel: { fontSize: 12, color: colors.secondary },
  subjectName: { fontSize: 19, fontWeight: '600', color: colors.text },
  subjectTag: { height: 25, borderRadius: 13, backgroundColor: colors.brandSoft, paddingHorizontal: 9, alignItems: 'center', justifyContent: 'center' },
  subjectTagText: { fontSize: 11, fontWeight: '500', color: colors.accent },
  introTitle: { fontSize: 21, lineHeight: 29, fontWeight: '600', color: colors.text, marginTop: 8 },
  introBody: { fontSize: 13, lineHeight: 18, color: colors.secondary },
  stepsCard: { backgroundColor: colors.surfaceRaised, borderRadius: 16, padding: 16, gap: 18 },
  step: { flexDirection: 'row', gap: 14, alignItems: 'flex-start' },
  stepNum: { fontSize: 16, fontWeight: '600', color: colors.accent, width: 24 },
  stepTexts: { flex: 1, gap: 3 },
  stepTitle: { fontSize: 16, fontWeight: '600', color: colors.text },
  stepDesc: { fontSize: 12, color: colors.secondary },
  durationNote: { fontSize: 12, color: colors.secondary },
  emergencyRow: { minHeight: 72 },
  introDisclaimer: { fontSize: 11, lineHeight: 15, color: colors.secondary, textAlign: 'center' },
  subtitle: { fontSize: 13, lineHeight: 20, color: colors.secondary },
  body: { fontSize: 14, lineHeight: 20, color: colors.text, flexShrink: 1 },
  card: { padding: 16, borderRadius: 20, backgroundColor: colors.surfaceRaised, gap: 10 },
  section: { fontSize: 15, fontWeight: '600', color: colors.text },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 40, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border },
  chipActive: { backgroundColor: colors.brandSoft, borderColor: colors.brand },
  chipDanger: { backgroundColor: colors.dangerBg, borderColor: colors.danger },
  chipText: { fontSize: 13, color: colors.text },
  followup: { marginTop: 6, padding: 12, borderRadius: 12, backgroundColor: colors.background, gap: 8 },
  followupTitle: { fontSize: 13, fontWeight: '600', color: colors.text },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  notes: { minHeight: 60, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 10, fontSize: 13, color: colors.text, textAlignVertical: 'top' },
  redline: { gap: 6 },
  row: { flexDirection: 'row', gap: 10 },
  half: { flex: 1 },
  problem: { fontSize: 13, lineHeight: 20, color: colors.danger },
  remove: { fontSize: 13, color: colors.danger, textDecorationLine: 'underline' },
});

import { useFocusEffect, useRouter } from 'expo-router';
import { Image, Keyboard, Linking, Platform, Pressable, StyleSheet, Text, View, type TextInputInstance } from 'react-native';
import { useCallback, useRef, useState } from 'react';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Screen } from '../../components/Screen';
import { Button } from '../../components/ui/Button';
import { Icon, type IconName } from '../../components/ui/Icon';
import { TextField } from '../../components/ui/TextField';
import { api } from '../../lib/api';
import { DELETION_CONFIRM_LABEL, DELETION_NOTICE, TRAINING_NOTICE, entitlementSummary, trainingConsentBody } from '../../lib/account';
import { cancelPetFeeding, cancelPetRechecks, getPermissionState, requestPermission, type PermissionState } from '../../lib/notifications';
import { QUOTA_EXHAUSTED_HINT, quotaEntries, type QuotaSnapshot } from '../../lib/quota';
import { ApiError } from '../../lib/session';
import { colors, radius, spacing, typography } from '../../theme';

type Profile = { id: number; nickname: string };
type Policy = { privacy: string; terms: string };
type Consent = { required: Policy; links: Policy; granted: boolean; training_granted: boolean };
type Entitlement = { plan: string; status: string; message: string };
type Pet = { id: number; name: string; species: 'cat'; breed: string | null; sex: 'male' | 'female' | 'unknown'; birth_date: string | null; neutered: boolean; body_type?: 'slim' | 'standard' | 'chubby' };
const emptyDraft = { name: '', breed: '', sex: 'unknown' as Pet['sex'], birth_date: '', neutered: false, body_type: 'standard' as NonNullable<Pet['body_type']> };
const hasFloatingTabBar = Platform.OS === 'ios' && Number.parseInt(Platform.Version, 10) >= 26;

function petMeta(pet: Pet) {
  const parts: string[] = [pet.breed ?? '猫咪'];
  if (pet.birth_date) {
    const birth = new Date(pet.birth_date);
    const months = Math.max(0, Math.floor((Date.now() - birth.getTime()) / (30.44 * 24 * 3600 * 1000)));
    parts.push(months < 12 ? `${months} 个月` : `${Math.floor(months / 12)} 岁`);
  }
  parts.push(pet.neutered ? '已绝育' : '未绝育');
  return parts.join(' · ');
}

function MenuRow({ icon, title, subtitle, onPress, first }: { icon: IconName; title: string; subtitle: string; onPress: () => void; first?: boolean }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.menuRow, !first && styles.menuDivider, pressed && styles.pressed]}>
      <Icon name={icon} size={22} color={colors.accent} />
      <View style={styles.menuTexts}>
        <Text style={styles.menuTitle}>{title}</Text>
        <Text style={styles.menuSubtitle}>{subtitle}</Text>
      </View>
      <Text style={styles.menuChevron}>›</Text>
    </Pressable>
  );
}

export default function ProfileScreen() {
  const router = useRouter();
  const { bottom } = useSafeAreaInsets();
  // iOS 悬浮 Tab 覆盖滚动区；在原有页底留白外加上当前 Tab 的安全区。
  const contentStyle = hasFloatingTabBar ? { paddingBottom: bottom + 32 } : undefined;
  const [profile, setProfile] = useState<Profile>();
  const [consent, setConsent] = useState<Consent>();
  const [pets, setPets] = useState<Pet[]>([]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [registering, setRegistering] = useState(false);
  const passwordField = useRef<TextInputInstance>(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [editing, setEditing] = useState<Pet | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [removing, setRemoving] = useState<number>();
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [trainingAsk, setTrainingAsk] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(true);
  const [notifyState, setNotifyState] = useState<PermissionState>('undetermined');
  const [quota, setQuota] = useState<QuotaSnapshot>();
  const [entitlement, setEntitlement] = useState<Entitlement>();

  const resetProfile = useCallback(() => {
    setProfile(undefined); setConsent(undefined); setPets([]);
    setEditing(null); setShowCreate(false); setRemoving(undefined);
    setDraft(emptyDraft); setQuota(undefined); setEntitlement(undefined);
    setTrainingAsk(false); setDeleting(false); setPrivacyOpen(false);
  }, []);

  const load = useCallback(async () => {
    const me = await api.authorized<Profile>('/me');
    setProfile(me);
    const state = await api.authorized<Consent>('/consents');
    setConsent(state);
    setPets(state.granted ? await api.authorized<Pet[]>('/pets') : []);
    setQuota(await api.authorized<QuotaSnapshot>('/quota'));
    setEntitlement(await api.authorized<Entitlement>('/me/entitlement'));
  }, []);

  useFocusEffect(useCallback(() => {
    let active = true;
    void load().catch(error => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 401) resetProfile();
      else setNotice(error instanceof Error ? error.message : '暂时无法加载账号');
    }).finally(() => { if (active) setBusy(false); });
    void getPermissionState().then(value => { if (active) setNotifyState(value); }).catch(() => {});
    return () => { active = false; };
  }, [load, resetProfile]));

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setNotice('');
    setBusy(true);
    try {
      await action();
    } catch (error) {
      if (profile && error instanceof ApiError && error.status === 401) resetProfile();
      if (error instanceof ApiError && (error.code === 'CONSENT_REQUIRED' || error.code === 'CONSENT_VERSION_CHANGED')) {
        setConsent(undefined); setPets([]);
      }
      setNotice(error instanceof Error ? error.message : '暂时无法完成操作');
    } finally {
      setBusy(false);
    }
  }

  const missingCredentials = !email.trim() || !password;
  const submitCredentials = () => {
    if (busy || missingCredentials) return;
    Keyboard.dismiss();
    void run(async () => {
      if (registering) {
        await api.register(email.trim(), password);
        setPassword('');
        await load();
      } else {
        await api.login(email.trim(), password);
        setPassword('');
        await load();
      }
    });
  };

  const json = (method: string, body: object): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const beginEdit = (pet: Pet) => {
    setShowCreate(false); setEditing(pet); setRemoving(undefined);
    setDraft({ name: pet.name, breed: pet.breed ?? '', sex: pet.sex, birth_date: pet.birth_date ?? '', neutered: pet.neutered, body_type: pet.body_type ?? 'standard' });
  };
  const savePet = () => run(async () => {
    const birthday = draft.birth_date.trim();
    if (birthday && !/^\d{4}-\d{2}-\d{2}$/.test(birthday)) throw new Error('请输入 YYYY-MM-DD 格式的生日，未知可留空');
    const body = { ...draft, name: draft.name.trim(), breed: draft.breed.trim() || null, birth_date: birthday || null };
    const pet = await api.authorized<Pet>(editing ? `/pets/${editing.id}` : '/pets', json(editing ? 'PATCH' : 'POST', body));
    setPets(current => editing ? current.map(item => item.id === pet.id ? pet : item) : [...current, pet]);
    setDraft(emptyDraft); setEditing(null); setShowCreate(false);
  });
  const confirmRemove = (pet: Pet) => run(async () => {
    await api.authorized(`/pets/${pet.id}`, { method: 'DELETE' });
    // 档案删除（F02-3）：同步取消该猫全部复查提醒与喂养提醒，避免幽灵通知。
    await cancelPetRechecks(pet.id).catch(() => {});
    await cancelPetFeeding(pet.id).catch(() => {});
    setRemoving(undefined);
    if (editing?.id === pet.id) { setEditing(null); setDraft(emptyDraft); }
    setPets(current => current.filter(item => item.id !== pet.id));
  });

  const editor = (
    <View style={styles.formCard}>
      <Text style={styles.formTitle}>{editing ? `编辑 · ${editing.name}` : '新建猫咪档案'}</Text>
      <TextField accessibilityLabel="猫咪名字" value={draft.name} onChangeText={name => setDraft(prev => ({ ...prev, name }))} placeholder="猫咪名字（必填）" maxLength={64} editable={!busy} />
      <TextField accessibilityLabel="猫咪品种" value={draft.breed} onChangeText={breed => setDraft(prev => ({ ...prev, breed }))} placeholder="品种（可不填）" maxLength={64} editable={!busy} />
      <TextField accessibilityLabel="猫咪生日，年-月-日" value={draft.birth_date} onChangeText={birth_date => setDraft(prev => ({ ...prev, birth_date }))} placeholder="生日 YYYY-MM-DD（可不填）" maxLength={10} editable={!busy} />
      <View style={styles.chips}>
        {([['unknown', '性别未知'], ['male', '弟弟'], ['female', '妹妹']] as const).map(([value, label]) => (
          <Pressable key={value} accessibilityRole="radio" accessibilityState={{ checked: draft.sex === value }} disabled={busy}
            onPress={() => setDraft(prev => ({ ...prev, sex: value }))} style={[styles.chip, draft.sex === value && styles.chipActive]}>
            <Text style={styles.chipText}>{draft.sex === value ? '✓ ' : ''}{label}</Text>
          </Pressable>
        ))}
      </View>
      <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: draft.neutered }} disabled={busy}
        onPress={() => setDraft(prev => ({ ...prev, neutered: !prev.neutered }))} style={[styles.chip, draft.neutered && styles.chipActive]}>
        <Text style={styles.chipText}>{draft.neutered ? '✓ 已绝育' : '标记已绝育'}</Text>
      </Pressable>
      <Text style={styles.fieldLabel}>体型（影响分身占位片选择）</Text>
      <View style={styles.chips}>
        {([['slim', '偏瘦'], ['standard', '标准'], ['chubby', '偏胖']] as const).map(([value, label]) => (
          <Pressable key={value} accessibilityRole="radio" accessibilityState={{ checked: draft.body_type === value }} disabled={busy}
            onPress={() => setDraft(prev => ({ ...prev, body_type: value }))} style={[styles.chip, draft.body_type === value && styles.chipActive]}>
            <Text style={styles.chipText}>{draft.body_type === value ? '✓ ' : ''}{label}</Text>
          </Pressable>
        ))}
      </View>
      <Button title={editing ? '保存猫咪档案' : '添加猫咪'} busy={busy} disabled={!draft.name.trim()} onPress={() => void savePet()} />
      {editing ? <Button title="取消编辑" variant="secondary" disabled={busy} onPress={() => { setEditing(null); setDraft(emptyDraft); }} /> : null}
      {showCreate && !editing ? <Button title="取消" variant="secondary" disabled={busy} onPress={() => { setShowCreate(false); setDraft(emptyDraft); }} /> : null}
    </View>
  );

  return (
    <Screen contentStyle={[contentStyle, !profile && styles.authContent]} adjustForKeyboard={!profile}>
      {!profile ? (
        <>
          <View style={styles.authHeader}>
            <Image source={require('../../../assets/figma/logo.png')} style={styles.authLogo} accessible={false} />
            <Text style={styles.authBrand}>绒星 · 星光护绒</Text>
            <Text accessibilityRole="header" style={styles.authTitle}>{registering ? '创建绒星账号' : '登录绒星'}</Text>
            <Text style={styles.authSubtitle}>{registering ? '注册后即可开始使用。' : '照顾猫咪的点滴，都在这里。'}</Text>
          </View>
          <View style={styles.authCard}>
            <View style={styles.authField}>
              <Text style={styles.authLabel}>邮箱</Text>
              <TextField accessibilityLabel="邮箱" placeholder="请输入邮箱地址" autoCapitalize="none" autoCorrect={false}
                autoComplete="email" keyboardType="email-address" returnKeyType="next" submitBehavior="submit"
                onSubmitEditing={() => passwordField.current?.focus()} value={email} onChangeText={setEmail} editable={!busy} style={styles.authInput} />
            </View>
            <View style={styles.authField}>
              <Text style={styles.authLabel}>密码</Text>
              <TextField ref={passwordField} accessibilityLabel="密码" placeholder="请输入密码" secureTextEntry autoCapitalize="none"
                autoComplete={registering ? 'new-password' : 'current-password'} returnKeyType="go" onSubmitEditing={submitCredentials}
                value={password} onChangeText={setPassword} editable={!busy} style={styles.authInput} />
              {registering ? <Text style={styles.bodyText}>至少 8 位，同时包含字母和数字。</Text> : null}
            </View>
            {notice ? <Text accessibilityLiveRegion="polite" style={styles.notice}>{notice}</Text> : null}
            <Button title={registering ? '创建账号' : '登录'} busy={busy} disabled={missingCredentials}
              onPress={submitCredentials} style={styles.authSubmit} />
            {busy ? <Text accessibilityLiveRegion="polite" style={styles.busyText}>处理中…</Text> : null}
          </View>
          <View style={styles.authActions}>
            <Pressable accessibilityRole="button" disabled={busy} onPress={() => {
              setRegistering(!registering); setPassword(''); setNotice('');
            }} style={({ pressed }) => [styles.authAction, pressed && styles.pressed]}>
              <Text style={styles.authActionText}>{registering ? '已有账号？返回登录' : '创建账号'}</Text>
            </Pressable>
          </View>
        </>
      ) : (
        <>
          <Text accessibilityRole="header" style={styles.pageTitle}>我的</Text>
          {notice ? <Text accessibilityLiveRegion="polite" style={styles.notice}>{notice}</Text> : null}
          {busy ? <Text accessibilityLiveRegion="polite" style={styles.busyText}>处理中…</Text> : null}
          {/* 用户信息卡 */}
          <View style={styles.userCard}>
            <View style={styles.userAvatar}><Icon name="user" size={20} color={colors.accent} /></View>
            <View style={styles.userTexts}>
              <Text style={styles.userName}>{profile.nickname}</Text>
              <Text style={styles.userNote}>邮箱账号 · 已登录</Text>
            </View>
          </View>

          {!consent ? <Button title="重新加载账号资料" variant="secondary" busy={busy} onPress={() => void run(load)} /> : null}

          {consent && !consent.granted ? (
            <View style={styles.formCard}>
              <Text style={styles.formTitle}>隐私与服务协议</Text>
              <Text style={styles.bodyText}>请阅读并同意以下两个文件后再添加猫咪。不同意可退出登录。</Text>
              {consent.links.privacy && consent.links.terms ? (
                <>
                  <Button title={`阅读隐私政策 (${consent.required.privacy})`} variant="secondary" busy={busy}
                    onPress={() => void run(() => Linking.openURL(consent.links.privacy))} />
                  <Button title={`阅读服务协议 (${consent.required.terms})`} variant="secondary" busy={busy}
                    onPress={() => void run(() => Linking.openURL(consent.links.terms))} />
                  <Button title="我已阅读并同意两份文件" busy={busy} onPress={() => void run(async () => {
                    await api.authorized('/consents', json('POST', consent.required));
                    await load();
                  })} />
                </>
              ) : <Text style={styles.bodyText}>当前环境尚未配置协议原文，无法提交同意。</Text>}
            </View>
          ) : null}

          {consent?.granted ? (
            <>
              {/* 我的猫咪 */}
              <Text style={styles.groupLabel}>我的猫咪</Text>
              <View style={styles.listCard}>
                {pets.map((pet, index) => (
                  <View key={pet.id}>
                    <Pressable accessibilityRole="button" onPress={() => beginEdit(pet)}
                      style={({ pressed }) => [styles.petRow, index > 0 && styles.menuDivider, pressed && styles.pressed]}>
                      <Image source={require('../../../assets/figma/cat-avatar.png')} style={styles.petAvatar} />
                      <View style={styles.menuTexts}>
                        <Text style={styles.menuTitle}>{pet.name}</Text>
                        <Text style={styles.menuSubtitle}>{petMeta(pet)}</Text>
                      </View>
                      {index === 0 ? <Text style={styles.defaultTag}>默认</Text> : null}
                      <Text style={styles.menuChevron}>›</Text>
                    </Pressable>
                    {removing === pet.id ? (
                      <View style={styles.inlineConfirm}>
                        <Text style={styles.bodyText}>确定移除 {pet.name} 的档案？移除后档案不再显示。</Text>
                        <Button title="确认移除" busy={busy} onPress={() => void confirmRemove(pet)} />
                        <Button title="取消移除" variant="secondary" disabled={busy} onPress={() => setRemoving(undefined)} />
                      </View>
                    ) : null}
                  </View>
                ))}
                {!pets.length ? <Text style={styles.emptyNote}>还没有猫咪档案，添加你的第一只猫咪吧。</Text> : null}
                <Pressable accessibilityRole="button" accessibilityState={{ disabled: pets.length >= 5 || busy }}
                  onPress={() => { if (pets.length >= 5) { setNotice('最多创建 5 只猫咪。'); return; } setEditing(null); setShowCreate(true); setDraft(emptyDraft); }}
                  style={({ pressed }) => [styles.petRow, pets.length > 0 && styles.menuDivider, pressed && styles.pressed, (pets.length >= 5 || busy) && styles.dim]}>
                  <Text style={styles.addPlus}>＋</Text>
                  <View style={styles.menuTexts}><Text style={styles.addLabel}>添加猫咪档案</Text></View>
                  <Text style={styles.menuChevron}>›</Text>
                </Pressable>
                {pets.length ? (
                  <Pressable accessibilityRole="button" disabled={busy} onPress={() => setRemoving(removing === undefined ? pets[0].id : undefined)}
                    style={({ pressed }) => [styles.petRow, styles.menuDivider, pressed && styles.pressed]}>
                    <Text style={styles.removeLabel}>{removing === undefined ? '移除猫咪档案…' : '收起移除确认'}</Text>
                  </Pressable>
                ) : null}
              </View>
              {showCreate || editing ? editor : null}

              {/* 健康与档案 */}
              <Text style={styles.groupLabel}>健康与档案</Text>
              <View style={styles.listCard}>
                <MenuRow first icon="file" title="猫咪档案管理" subtitle="名字、品种、生日、绝育状态"
                  onPress={() => { if (pets[0]) beginEdit(pets[0]); else { setShowCreate(true); setDraft(emptyDraft); } }} />
                <MenuRow icon="clock" title="健康记录历史" subtitle="初筛、饮食、体重按时间查看"
                  onPress={() => { if (pets[0]) router.push(`/timeline/${pets[0].id}`); else setNotice('先创建猫咪档案，再查看健康记录。'); }} />
                <MenuRow icon="bell" title="提醒设置" subtitle="喂养时段与初筛复查提醒"
                  onPress={() => { if (pets[0]) router.push(`/reminders/${pets[0].id}`); else setNotice('先创建猫咪档案，再设置提醒。'); }} />
              </View>

              {/* 账号与数据 */}
              <Text style={styles.groupLabel}>账号与数据</Text>
              <View style={styles.listCard}>
                <MenuRow first icon="shield" title="隐私与数据" subtitle="授权管理、数据删除、账号注销" onPress={() => setPrivacyOpen(open => !open)} />
                <MenuRow icon="file" title="用户协议" subtitle="绒星服务条款"
                  onPress={() => { if (consent?.links.terms) void run(() => Linking.openURL(consent.links.terms)); else setNotice('协议链接暂不可用，请稍后重试。'); }} />
                <MenuRow icon="settings" title="帮助与反馈" subtitle="常见问题、联系支持"
                  onPress={() => setNotice('帮助文档与支持渠道即将上线；当前问题可通过注册邮箱联系项目组。')} />
              </View>
              {privacyOpen ? (
                <View style={styles.formCard}>
                  <Text style={styles.formTitle}>通知权限</Text>
                  <Text style={styles.bodyText}>{notifyState === 'granted'
                    ? '已开启：observe 初筛 24 小时后会收到复查提醒。'
                    : '未开启：复查提醒将以应用内横幅呈现，不影响任何功能。'}</Text>
                  {notifyState !== 'granted' ? (
                    <Button title="重新授权通知" variant="secondary" busy={busy} onPress={() => void run(async () => {
                      setNotifyState(await requestPermission());
                    })} />
                  ) : null}
                  <Text style={styles.formTitle}>训练数据授权</Text>
                  {consent?.training_granted ? (
                    <>
                      <Text style={styles.bodyText}>已允许将匿名使用数据用于模型训练。</Text>
                      <Button title="撤销训练授权" variant="secondary" busy={busy} onPress={() => void run(async () => {
                        await api.authorized('/consents/training', json('POST', trainingConsentBody(false)));
                        await load();
                      })} />
                    </>
                  ) : trainingAsk ? (
                    <>
                      <Text style={styles.bodyText}>{TRAINING_NOTICE}</Text>
                      <Button title="确认授权" busy={busy} onPress={() => void run(async () => {
                        await api.authorized('/consents/training', json('POST', trainingConsentBody(true)));
                        setTrainingAsk(false);
                        await load();
                      })} />
                      <Button title="不允许" variant="secondary" busy={busy} onPress={() => void run(async () => {
                        await api.authorized('/consents/training', json('POST', trainingConsentBody(false)));
                        setTrainingAsk(false);
                        await load();
                      })} />
                    </>
                  ) : (
                    <>
                      <Text style={styles.bodyText}>默认不允许。授权与否都不影响任何功能。</Text>
                      <Button title="设置训练授权" variant="secondary" busy={busy} onPress={() => setTrainingAsk(true)} />
                    </>
                  )}
                  <Text style={styles.formTitle}>注销账号</Text>
                  {deleting ? (
                    <>
                      <Text style={styles.bodyText}>{DELETION_NOTICE}</Text>
                      <Button title={DELETION_CONFIRM_LABEL} busy={busy} onPress={() => void run(async () => {
                        await api.authorized('/me', { method: 'DELETE' });
                        await api.clear();
                        resetProfile();
                        setNotice('注销申请已提交：账号已冻结，15 天后数据将被物理清除。');
                      })} />
                      <Button title="取消注销" variant="secondary" disabled={busy} onPress={() => setDeleting(false)} />
                    </>
                  ) : (
                    <Button title="申请注销账号" variant="secondary" busy={busy} onPress={() => setDeleting(true)} />
                  )}
                </View>
              ) : null}

              {/* 今日配额与权益（功能卡，画板未含） */}
              <View style={styles.formCard}>
                <Text style={styles.formTitle}>今日用量</Text>
                {quotaEntries(quota).map(entry => (
                  <Text key={entry.metric} style={styles.quotaText}>{entry.label}：{entry.used}/{entry.limit}{entry.exhausted ? ' · ' + QUOTA_EXHAUSTED_HINT : ''}</Text>
                ))}
                {!quota ? <Text style={styles.bodyText}>用量加载中…</Text> : null}
                <Text style={styles.formTitle}>会员权益</Text>
                <Text style={styles.quotaText}>{entitlementSummary(entitlement)}</Text>
                <Text style={styles.bodyText}>测试期不提供付费功能，所有权益免费开放。</Text>
              </View>
            </>
          ) : null}

          <Button title="在此设备退出登录" variant="secondary" busy={busy} onPress={() => void run(async () => {
            await api.clear();
            resetProfile();
          })} />
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  authContent: { paddingTop: spacing.s6 },
  authHeader: { alignItems: 'center', gap: spacing.s2, paddingBottom: spacing.s2 },
  authLogo: { width: 72, height: 72, marginBottom: spacing.s1 },
  authBrand: { ...typography.label, color: colors.accent },
  authTitle: { ...typography.pageTitle, color: colors.onBrand, textAlign: 'center' },
  authSubtitle: { ...typography.caption, color: colors.secondary, textAlign: 'center' },
  authCard: { padding: spacing.s5, gap: spacing.s4, backgroundColor: colors.surfaceRaised, borderRadius: radius.lg },
  authField: { gap: spacing.s2 },
  authLabel: { ...typography.label, color: colors.text },
  authInput: { borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, paddingHorizontal: spacing.s4 },
  authSubmit: { height: 'auto', minHeight: 48, paddingVertical: spacing.s2 },
  authActions: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', columnGap: spacing.s3 },
  authAction: { minHeight: 44, justifyContent: 'center', paddingHorizontal: spacing.s2 },
  authActionText: { ...typography.caption, fontWeight: '600', color: colors.accent },
  pageTitle: { fontSize: 24, lineHeight: 32, fontWeight: '600', color: colors.text },
  notice: { color: colors.text, backgroundColor: colors.brandSoft, borderRadius: 12, padding: 12, fontSize: 13, lineHeight: 20 },
  busyText: { fontSize: 12, color: colors.secondary },
  bodyText: { fontSize: 13, lineHeight: 20, color: colors.secondary },
  pressed: { opacity: 0.85 },
  dim: { opacity: 0.6 },
  userCard: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: colors.surfaceRaised, borderRadius: 16, padding: 14, minHeight: 67 },
  userAvatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' },
  userTexts: { flex: 1, gap: 2 },
  userName: { fontSize: 16, fontWeight: '600', color: colors.text },
  userNote: { fontSize: 11, color: colors.secondary },
  groupLabel: { fontSize: 12, fontWeight: '500', color: colors.secondary, marginTop: 8 },
  listCard: { backgroundColor: colors.surfaceRaised, borderRadius: 16, paddingHorizontal: 14 },
  menuRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  menuDivider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  menuTexts: { flex: 1, gap: 2 },
  menuTitle: { fontSize: 14, fontWeight: '600', color: colors.text },
  menuSubtitle: { fontSize: 11, color: colors.secondary },
  menuChevron: { fontSize: 24, color: colors.timestamp },
  petRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  petAvatar: { width: 42, height: 42, borderRadius: 21 },
  defaultTag: { fontSize: 11, fontWeight: '500', color: colors.accent },
  addPlus: { fontSize: 22, color: colors.accent, width: 42, textAlign: 'center' },
  addLabel: { fontSize: 14, fontWeight: '500', color: colors.text },
  removeLabel: { fontSize: 12, color: colors.secondary },
  emptyNote: { fontSize: 12, color: colors.secondary, paddingVertical: 12 },
  inlineConfirm: { gap: 8, paddingVertical: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  formCard: { padding: 16, borderRadius: 20, backgroundColor: colors.surfaceRaised, gap: 12 },
  formTitle: { fontSize: 15, fontWeight: '600', color: colors.text },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { minHeight: 40, borderWidth: 1, borderColor: colors.border, borderRadius: 12, justifyContent: 'center', paddingHorizontal: 12, backgroundColor: colors.background },
  chipActive: { backgroundColor: colors.brandSoft, borderColor: colors.brand },
  chipText: { fontSize: 13, color: colors.text },
  fieldLabel: { fontSize: 12, color: colors.secondary },
  quotaText: { fontSize: 13, lineHeight: 20, color: colors.text },
});

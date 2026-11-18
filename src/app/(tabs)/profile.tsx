import { useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Screen } from '../../components/Screen';
import { api } from '../../lib/api';
import { ApiError } from '../../lib/session';
import { colors } from '../../theme';

type Profile = { id: number; nickname: string };
type Policy = { privacy: string; terms: string };
type Consent = { required: Policy; links: Policy; granted: boolean };
const emptyPet = { name: '', breed: '', sex: 'unknown' as 'unknown' | 'male' | 'female', birth_date: '', neutered: false };
type Pet = Omit<typeof emptyPet, 'breed' | 'birth_date'> & { id: number; breed: string | null; birth_date: string | null };

function Action({ label, onPress, disabled = false }: { label: string; onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress}
      style={({ pressed }) => [styles.button, (pressed || disabled) && styles.dim]}>
      <Text style={styles.buttonText}>{label}</Text>
    </Pressable>
  );
}

function json(method: string, body: object): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

export default function ProfileScreen() {
  const [profile, setProfile] = useState<Profile>();
  const [consent, setConsent] = useState<Consent>();
  const [pets, setPets] = useState<Pet[]>([]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [draft, setDraft] = useState(emptyPet);
  const [editing, setEditing] = useState<number>();
  const [removing, setRemoving] = useState<number>();
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(true);

  function resetProfile() {
    setProfile(undefined);
    setConsent(undefined);
    setPets([]);
    setEditing(undefined);
    setRemoving(undefined);
    setDraft(emptyPet);
  }

  async function load() {
    setProfile(await api.authorized<Profile>('/me'));
    const state = await api.authorized<Consent>('/consents');
    setConsent(state);
    setPets(state.granted ? await api.authorized<Pet[]>('/pets') : []);
  }

  useEffect(() => {
    Promise.resolve().then(load).catch(error => {
      if (!(error instanceof ApiError && error.status === 401)) {
        setNotice(error instanceof Error ? error.message : '暂时无法加载账号');
      }
    }).finally(() => setBusy(false));
  }, []);

  async function run(action: () => Promise<void>) {
    setNotice('');
    setBusy(true);
    try {
      await action();
    } catch (error) {
      if (profile && error instanceof ApiError && error.status === 401) resetProfile();
      if (error instanceof ApiError && (error.code === 'CONSENT_REQUIRED' || error.code === 'CONSENT_VERSION_CHANGED')) {
        setConsent(undefined);
        setPets([]);
      }
      setNotice(error instanceof Error ? error.message : '暂时无法完成操作');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Text accessibilityRole="header" style={styles.title}>我的</Text>
      {notice ? <Text accessibilityLiveRegion="polite" style={styles.notice}>{notice}</Text> : null}
      {busy ? <Text accessibilityLiveRegion="polite" style={styles.text}>处理中…</Text> : null}
      {!profile ? (
        <View style={styles.card}>
          <Text accessibilityRole="header" style={styles.heading}>邮箱账号</Text>
          <TextInput accessibilityLabel="邮箱" placeholder="邮箱" autoCapitalize="none" autoCorrect={false}
            autoComplete="email" keyboardType="email-address" value={email} onChangeText={setEmail} editable={!busy} style={styles.input} />
          <TextInput accessibilityLabel="密码" placeholder="密码" secureTextEntry autoCapitalize="none"
            autoComplete="current-password" value={password} onChangeText={setPassword} editable={!busy} style={styles.input} />
          <Action label="登录" disabled={busy || !email.trim() || !password} onPress={() => void run(async () => {
            await api.login(email.trim(), password);
            setPassword('');
            await load();
          })} />
          <Action label="注册并发送验证邮件" disabled={busy || !email.trim() || !password} onPress={() => void run(async () => {
            setNotice((await api.sendVerification('/auth/register', email.trim(), password)).message);
          })} />
          <Action label="补发验证邮件" disabled={busy || !email.trim() || !password} onPress={() => void run(async () => {
            setNotice((await api.sendVerification('/auth/resend-verification', email.trim(), password)).message);
          })} />
        </View>
      ) : (
        <>
          <Text style={styles.heading}>{profile.nickname}</Text>
          {!consent ? <Action label="重新加载账号资料" disabled={busy} onPress={() => void run(load)} /> : null}
          {consent && !consent.granted ? (
            <View style={styles.card}>
              <Text accessibilityRole="header" style={styles.heading}>隐私与服务协议</Text>
              <Text style={styles.text}>请阅读并同意以下两个文件后再添加猫咪。不同意可退出登录。</Text>
              {consent.links.privacy && consent.links.terms ? (
                <>
                  <Action label={`阅读隐私政策 (${consent.required.privacy})`} disabled={busy}
                    onPress={() => void run(() => Linking.openURL(consent.links.privacy))} />
                  <Action label={`阅读服务协议 (${consent.required.terms})`} disabled={busy}
                    onPress={() => void run(() => Linking.openURL(consent.links.terms))} />
                  <Action label="我已阅读并同意两份文件" disabled={busy} onPress={() => void run(async () => {
                    await api.authorized('/consents', json('POST', consent.required));
                    await load();
                  })} />
                </>
              ) : <Text style={styles.text}>当前环境尚未配置协议原文，无法提交同意。</Text>}
            </View>
          ) : null}
          {consent?.granted ? (
            <View style={styles.card}>
              <Text accessibilityRole="header" style={styles.heading}>猫咪档案</Text>
              {!pets.length ? <Text style={styles.text}>还没有猫咪档案，添加你的第一只猫咪吧。</Text> : null}
              {pets.map(pet => (
                <View key={pet.id} style={styles.card}>
                  <Text style={styles.heading}>{pet.name}</Text>
                  <Text style={styles.text}>{[pet.breed || '品种未知', pet.sex === 'male' ? '公' : pet.sex === 'female' ? '母' : '性别未知',
                    pet.birth_date || '生日未知', pet.neutered ? '已绝育' : '未标记绝育'].join(' · ')}</Text>
                  <Action label={`编辑 ${pet.name}`} disabled={busy} onPress={() => { setDraft({ name: pet.name, breed: pet.breed ?? '', sex: pet.sex, birth_date: pet.birth_date ?? '', neutered: pet.neutered }); setEditing(pet.id); }} />
                  {removing === pet.id ? (
                    <>
                      <Text style={styles.text}>确定移除 {pet.name} 的档案？移除后档案不再显示。</Text>
                      <Action label="确认移除" disabled={busy} onPress={() => void run(async () => {
                        await api.authorized(`/pets/${pet.id}`, { method: 'DELETE' });
                        setRemoving(undefined);
                        if (editing === pet.id) { setEditing(undefined); setDraft(emptyPet); }
                        setPets(current => current.filter(item => item.id !== pet.id));
                      })} />
                      <Action label="取消移除" onPress={() => setRemoving(undefined)} />
                    </>
                  ) : <Action label={`移除 ${pet.name}`} disabled={busy} onPress={() => setRemoving(pet.id)} />}
                </View>
              ))}
              <TextInput accessibilityLabel="猫咪名字" placeholder="猫咪名字（必填）" maxLength={64}
                value={draft.name} onChangeText={name => setDraft(current => ({ ...current, name }))} editable={!busy} style={styles.input} />
              <TextInput accessibilityLabel="猫咪品种" placeholder="品种（可不填）" maxLength={64}
                value={draft.breed} onChangeText={breed => setDraft(current => ({ ...current, breed }))} editable={!busy} style={styles.input} />
              <TextInput accessibilityLabel="猫咪生日，年-月-日" placeholder="生日 YYYY-MM-DD（可不填）" maxLength={10}
                value={draft.birth_date} onChangeText={birth_date => setDraft(current => ({ ...current, birth_date }))} editable={!busy} style={styles.input} />
              <Text style={styles.text}>性别</Text>
              <View style={styles.options}>
                {(['unknown', 'male', 'female'] as const).map(sex => (
                  <Pressable key={sex} accessibilityRole="radio" accessibilityState={{ checked: draft.sex === sex }}
                    disabled={busy} onPress={() => setDraft(current => ({ ...current, sex }))} style={styles.option}>
                    <Text style={styles.text}>{draft.sex === sex ? '✓ ' : ''}{sex === 'male' ? '公' : sex === 'female' ? '母' : '未知'}</Text>
                  </Pressable>
                ))}
              </View>
              <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: draft.neutered }} disabled={busy}
                onPress={() => setDraft(current => ({ ...current, neutered: !current.neutered }))} style={styles.option}>
                <Text style={styles.text}>{draft.neutered ? '✓ 已绝育' : '标记已绝育'}</Text>
              </Pressable>
              <Action label={editing === undefined ? '添加猫咪' : '保存猫咪档案'} disabled={busy || !draft.name.trim()}
                onPress={() => void run(async () => {
                  const birthday = draft.birth_date.trim();
                  if (birthday && !/^\d{4}-\d{2}-\d{2}$/.test(birthday)) throw new Error('请输入 YYYY-MM-DD 格式的生日，未知可留空');
                  const pet = await api.authorized<Pet>(editing === undefined ? '/pets' : `/pets/${editing}`,
                    json(editing === undefined ? 'POST' : 'PATCH', { ...draft, name: draft.name.trim(),
                      breed: draft.breed.trim() || null, birth_date: birthday || null }));
                  setPets(current => editing === undefined ? [...current, pet] : current.map(item => item.id === pet.id ? pet : item));
                  setDraft(emptyPet);
                  setEditing(undefined);
                })} />
              {editing !== undefined ? <Action label="取消编辑" onPress={() => { setEditing(undefined); setDraft(emptyPet); }} /> : null}
            </View>
          ) : null}
          <Action label="在此设备退出登录" disabled={busy} onPress={() => void run(async () => {
            await api.clear();
            resetProfile();
          })} />
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { color: colors.text, fontSize: 28, fontWeight: '700' },
  heading: { color: colors.text, fontSize: 18, fontWeight: '700' },
  text: { color: colors.secondary, fontSize: 15 },
  notice: { color: colors.text, backgroundColor: colors.soft, borderRadius: 12, padding: 12 },
  card: { gap: 12, backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 16, padding: 16 },
  input: { minHeight: 48, borderColor: colors.border, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12,
    color: colors.text, backgroundColor: colors.background },
  options: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  option: { minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: 12, justifyContent: 'center', paddingHorizontal: 12 },
  button: { minHeight: 48, justifyContent: 'center', alignItems: 'center', borderRadius: 12, backgroundColor: colors.brand, padding: 10 },
  buttonText: { color: colors.onBrand, fontSize: 15, fontWeight: '600', textAlign: 'center' },
  dim: { opacity: 0.6 },
});

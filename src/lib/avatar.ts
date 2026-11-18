// 分身展示选择（FRD F03-6 回退链：个人片 → 占位片 → 静态底图）。纯函数，便于测试。

export interface PlaceholderManifest {
  version: string;
  body_type: string;
  clips: Record<string, string>;
}

export interface AvatarClip {
  status: 'ready' | 'failed' | 'pending';
  url: string | null;
  version_id?: string;
}

export interface AvatarView {
  task_id: string;
  status: string;
  body_type: string;
  base_image: { url: string; version_id: string } | null;
  clips: Record<string, AvatarClip>;
  ready_count: number;
  usable: boolean;
  placeholder_manifest: PlaceholderManifest;
}

export type IdleSource =
  | { kind: 'personal'; url: string }
  | { kind: 'placeholder'; url: string }
  | { kind: 'static' };

type AvatarLike = Partial<Pick<AvatarView, 'clips' | 'placeholder_manifest'>> | null | undefined;

export function pickIdleSource(avatar: AvatarLike): IdleSource {
  const personal = avatar?.clips?.idle;
  if (personal?.status === 'ready' && personal.url) return { kind: 'personal', url: personal.url };
  const placeholder = avatar?.placeholder_manifest?.clips?.idle;
  if (placeholder) return { kind: 'placeholder', url: placeholder };
  return { kind: 'static' };
}

// T07 动作候选：个人片 → 占位片 → 静态底图（F03-6）。
// 缓存键按内容版本（pet/action/version_id 或占位库版本），签名 URL 过期不影响命中。
export type SourceKind = 'personal' | 'placeholder' | 'static';

export interface ClipCandidate {
  action: string;
  kind: SourceKind;
  key: string | null;
  url: string | null;
}

export function candidateFor(
  action: string,
  avatar: AvatarLike,
  petId: number,
  degraded: Record<string, 'placeholder' | 'static'> = {},
): ClipCandidate {
  const level = degraded[action];
  const personal = avatar?.clips?.[action];
  if (level !== 'placeholder' && level !== 'static' && personal?.status === 'ready' && personal.url) {
    return { action, kind: 'personal', key: `p:${petId}:${action}:${personal.version_id ?? 'v0'}`, url: personal.url };
  }
  const manifest = avatar?.placeholder_manifest;
  const placeholder = manifest?.clips?.[action];
  if (level !== 'static' && manifest && placeholder) {
    return { action, kind: 'placeholder', key: `ph:${manifest.version}:${manifest.body_type}:${action}`, url: placeholder };
  }
  return { action, kind: 'static', key: null, url: null };
}

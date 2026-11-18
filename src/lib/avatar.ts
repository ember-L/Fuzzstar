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

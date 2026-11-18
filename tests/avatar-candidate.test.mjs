// T07 动作候选解析：个人片→占位片→静态（F03-6），缓存键按内容版本。
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { candidateFor } from '../src/lib/avatar.ts';

const manifest = { version: 'v1', body_type: 'chubby', clips: { idle: 'https://api/ph/v1/chubby/idle.mp4', happy: 'https://api/ph/v1/chubby/happy.mp4' } };
const avatar = {
  clips: {
    idle: { status: 'ready', url: 'https://oss/idle.mp4?sig=1', version_id: 'ver-9' },
    happy: { status: 'failed', url: null },
  },
  placeholder_manifest: manifest,
};

test('个人片 ready → personal，键含 pet/action/version_id', () => {
  const c = candidateFor('idle', avatar, 7);
  assert.deepEqual(c, { action: 'idle', kind: 'personal', key: 'p:7:idle:ver-9', url: 'https://oss/idle.mp4?sig=1' });
});

test('单动作 failed → 该动作占位片（AC-03-6）', () => {
  const c = candidateFor('happy', avatar, 7);
  assert.equal(c.kind, 'placeholder');
  assert.equal(c.key, 'ph:v1:chubby:happy');
  assert.equal(c.url, manifest.clips.happy);
});

test('降级标记强制占位/静态；无清单 → 静态兜底', () => {
  assert.equal(candidateFor('idle', avatar, 7, { idle: 'placeholder' }).kind, 'placeholder');
  assert.equal(candidateFor('idle', avatar, 7, { idle: 'static' }).kind, 'static');
  assert.equal(candidateFor('idle', { clips: {}, placeholder_manifest: null }, 7).kind, 'static');
  assert.equal(candidateFor('idle', null, 7).kind, 'static');
  const c = candidateFor('idle', { clips: {}, placeholder_manifest: null }, 7);
  assert.deepEqual(c, { action: 'idle', kind: 'static', key: null, url: null });
});

test('个人片无 version_id 时键用 v0 占位', () => {
  const c = candidateFor('idle', { clips: { idle: { status: 'ready', url: 'https://x/i.mp4' } }, placeholder_manifest: manifest }, 3);
  assert.equal(c.key, 'p:3:idle:v0');
});

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { pickIdleSource } from '../src/lib/avatar.ts';

const placeholder = { version: 'v1', body_type: 'standard', clips: { idle: 'https://api.test/api/v1/avatar/placeholders/v1/standard/idle.mp4' } };

test('personal ready idle clip wins', () => {
  const source = pickIdleSource({ clips: { idle: { status: 'ready', url: 'https://cdn.test/idle.mp4' } }, placeholder_manifest: placeholder });
  assert.deepEqual(source, { kind: 'personal', url: 'https://cdn.test/idle.mp4' });
});

test('failed personal clip falls back to placeholder', () => {
  const source = pickIdleSource({ clips: { idle: { status: 'failed', url: null } }, placeholder_manifest: placeholder });
  assert.deepEqual(source, { kind: 'placeholder', url: placeholder.clips.idle });
});

test('pending generation plays placeholder immediately', () => {
  const source = pickIdleSource({ clips: { idle: { status: 'pending', url: null } }, placeholder_manifest: placeholder });
  assert.equal(source.kind, 'placeholder');
});

test('submission manifest alone is enough for first frame', () => {
  const source = pickIdleSource({ placeholder_manifest: placeholder });
  assert.equal(source.kind, 'placeholder');
});

test('no avatar and no manifest keeps static fallback', () => {
  assert.deepEqual(pickIdleSource(null), { kind: 'static' });
  assert.deepEqual(pickIdleSource(undefined), { kind: 'static' });
  assert.deepEqual(pickIdleSource({}), { kind: 'static' });
});

test('ready clip without url falls back to placeholder', () => {
  const source = pickIdleSource({ clips: { idle: { status: 'ready', url: null } }, placeholder_manifest: placeholder });
  assert.equal(source.kind, 'placeholder');
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { ACTION_LABELS, GIF_ACTIONS, GIF_SHARE_HINT, gifFileName, parseGifTask } from '../src/lib/gif-export.ts';

test('gif actions cover the seven avatar actions with labels', () => {
  assert.deepEqual(GIF_ACTIONS, ['idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right']);
  for (const action of GIF_ACTIONS) assert.ok(ACTION_LABELS[action]);
});

test('parseGifTask maps statuses and download url', () => {
  assert.deepEqual(parseGifTask({ status: 'succeeded', download_url: 'https://x/g.gif' }),
    { status: 'succeeded', downloadUrl: 'https://x/g.gif' });
  assert.deepEqual(parseGifTask({ status: 'running' }), { status: 'pending', downloadUrl: null });
  assert.deepEqual(parseGifTask({ status: 'failed' }), { status: 'failed', downloadUrl: null });
  assert.deepEqual(parseGifTask({ status: 'succeeded' }), { status: 'failed', downloadUrl: null });
  assert.deepEqual(parseGifTask(null), { status: 'pending', downloadUrl: null });
});

test('gif file name uses pet name and action label', () => {
  assert.equal(gifFileName('团团', 'happy'), '团团-开心.gif');
  assert.equal(gifFileName('团团', 'nope'), '团团-nope.gif');
});

test('share hint mentions watermark and no third-party upload', () => {
  assert.ok(GIF_SHARE_HINT.includes('绒星 · AI 参考'));
  assert.ok(GIF_SHARE_HINT.includes('不会上传第三方'));
});

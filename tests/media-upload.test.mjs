import assert from 'node:assert/strict';
import { test } from 'node:test';
import { uploadMedia, MediaUploadError } from '../src/lib/photo-upload.ts';

const ticket = { media_id: 'a'.repeat(32), upload: { url: 'https://storage.example/upload', fields: { key: 'k', policy: 'p' } } };

function harness({ presign = ticket, uploadOk = true, complete = { media_id: 'a'.repeat(32), status: 'verified' } } = {}) {
  const calls = [];
  const authorized = async (path, init) => {
    calls.push({ path, body: init?.body ? JSON.parse(init.body) : undefined });
    if (path === '/media/presign') return presign;
    return complete;
  };
  const sendUpload = async () => ({ ok: uploadOk });
  return { calls, authorized, sendUpload };
}

const mp4 = new Blob([new Uint8Array(64)], { type: 'video/mp4' });

test('video presign declares kind video and completes', async () => {
  const h = harness();
  const id = await uploadMedia(7, mp4, 'video', h.authorized, h.sendUpload, new AbortController().signal);
  assert.equal(id, 'a'.repeat(32));
  assert.deepEqual(h.calls[0].body, { pet_id: 7, kind: 'video', content_type: 'video/mp4', size_bytes: 64 });
});

test('video rejects wrong type and oversize', async () => {
  const h = harness();
  const signal = new AbortController().signal;
  await assert.rejects(uploadMedia(7, new Blob([new Uint8Array(4)], { type: 'video/webm' }), 'video', h.authorized, h.sendUpload, signal), MediaUploadError);
  const big = new Blob([new Uint8Array(50 * 1024 * 1024 + 1)], { type: 'video/mp4' });
  await assert.rejects(uploadMedia(7, big, 'video', h.authorized, h.sendUpload, signal), MediaUploadError);
});

test('photo path still enforces image limits', async () => {
  const h = harness();
  const signal = new AbortController().signal;
  await assert.rejects(uploadMedia(7, mp4, 'photo', h.authorized, h.sendUpload, signal), MediaUploadError);
  const png = new Blob([new Uint8Array(8)], { type: 'image/png' });
  assert.equal(await uploadMedia(7, png, 'photo', h.authorized, h.sendUpload, signal), 'a'.repeat(32));
  assert.equal(h.calls[0].body.kind, 'photo');
});

test('failed upload surfaces a retryable error', async () => {
  const h = harness({ uploadOk: false });
  await assert.rejects(uploadMedia(7, mp4, 'video', h.authorized, h.sendUpload, new AbortController().signal), MediaUploadError);
});

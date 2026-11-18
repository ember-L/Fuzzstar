import assert from 'node:assert/strict';
import test from 'node:test';
import { uploadPhoto } from '../src/lib/photo-upload.ts';

const photo = new Blob(['fixture'], { type: 'image/png' });
const mediaId = 'a'.repeat(32);
const upload = { url: 'https://storage.example/bucket', fields: { key: 'photos/2/test', 'Content-Type': 'image/png', policy: 'signed' } };
const signal = () => new AbortController().signal;

test('sends the original file to storage without API credentials, then verifies it for the selected cat', async () => {
  const calls = [];
  const result = await uploadPhoto(2, photo, async (path, init) => {
    calls.push(path);
    assert.equal(init.method, 'POST');
    if (path === '/media/presign') {
      assert.deepEqual(JSON.parse(init.body), { pet_id: 2, content_type: 'image/png', size_bytes: photo.size });
      return { media_id: mediaId, upload };
    }
    assert.equal(path, `/media/${mediaId}/complete`);
    return { media_id: mediaId, status: 'verified' };
  }, async (url, init) => {
    calls.push(url);
    assert.equal(url, upload.url);
    assert.equal(init.method, 'POST');
    assert.equal(init.credentials, 'omit');
    assert.equal(init.redirect, 'error');
    assert.equal(init.headers, undefined);
    assert.deepEqual([...init.body.entries()].slice(0, -1), Object.entries(upload.fields));
    const [field, file] = [...init.body.entries()].at(-1);
    assert.equal(field, 'file');
    assert.equal(file.type, 'image/png');
    assert.equal(await file.text(), 'fixture');
    return new Response(null, { status: 204 });
  }, signal());
  assert.equal(result, mediaId);
  assert.deepEqual(calls, ['/media/presign', upload.url, `/media/${mediaId}/complete`]);
});

test('does not request a signature for an unsupported, empty, or oversized file', async () => {
  for (const file of [new Blob(['x'], { type: 'image/gif' }), new Blob([], { type: 'image/png' }),
    { type: 'image/png', size: 10 * 1024 * 1024 + 1 }]) {
    await assert.rejects(uploadPhoto(2, file, assert.fail, assert.fail, signal()), /10 MiB/);
  }
});

test('does not confirm after storage rejection, cancellation, or an unsafe upload URL', async () => {
  for (const scenario of ['rejected', 'aborted', 'unsafe']) {
    const controller = new AbortController();
    let transferred = false;
    await assert.rejects(uploadPhoto(2, photo, async path => {
      assert.equal(path, '/media/presign');
      return { media_id: mediaId, upload: { ...upload, url: scenario === 'unsafe' ? 'http://storage.example/bucket' : upload.url } };
    }, async () => {
      transferred = true;
      if (scenario === 'aborted') controller.abort();
      return new Response(null, { status: scenario === 'rejected' ? 403 : 204 });
    }, controller.signal), /上传/);
    assert.equal(transferred, scenario !== 'unsafe');
  }
});

test('storage success without a matching verified response is not reported as success', async () => {
  await assert.rejects(uploadPhoto(2, photo, async path => path === '/media/presign'
    ? { media_id: mediaId, upload } : { media_id: mediaId, status: 'pending' },
  async () => new Response(null, { status: 204 }), signal()), /未确认/);
});

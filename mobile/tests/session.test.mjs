import assert from 'node:assert/strict';
import test from 'node:test';
import { createSessionClient } from '../src/lib/session.ts';

test('concurrent expired requests rotate once and persist the new refresh token', async () => {
  let saved = 'old';
  let rotations = 0;
  const session = createSessionClient(async (path, init) => {
    if (path === '/auth/refresh') {
      assert.equal(JSON.parse(init.body).refresh_token, 'old');
      rotations++;
      return Response.json({ access_token: 'access', refresh_token: 'new' });
    }
    assert.equal(init.headers.Authorization, 'Bearer access');
    return Response.json({ id: 1 });
  }, { read: async () => saved, write: async token => { saved = token; } });
  assert.deepEqual(await Promise.all([session.authorized('/me'), session.authorized('/me')]), [{ id: 1 }, { id: 1 }]);
  assert.equal(rotations, 1);
  assert.equal(saved, 'new');
});

test('an expired access token is retried, then a revoked refresh clears storage', async () => {
  let saved = null;
  let replay = false;
  const calls = [];
  const session = createSessionClient(async (path, init) => {
    calls.push(path);
    if (path === '/auth/login') return Response.json({ access_token: 'expired', refresh_token: 'first' });
    if (path === '/auth/refresh' && !replay) {
      assert.equal(JSON.parse(init.body).refresh_token, 'first');
      return Response.json({ access_token: 'valid', refresh_token: 'next' });
    }
    if (init.headers?.Authorization === 'Bearer valid' && !replay) return Response.json({ id: 1 });
    return Response.json({ code: 'TOKEN_EXPIRED', message: '请重新登录' }, { status: 401 });
  }, { read: async () => saved, write: async token => { saved = token; } });
  await session.login('cat@example.com', 'test');
  assert.deepEqual(await session.authorized('/me'), { id: 1 });
  assert.deepEqual(calls, ['/auth/login', '/me', '/auth/refresh', '/me']);
  replay = true;
  await assert.rejects(session.authorized('/me'), { status: 401 });
  assert.equal(saved, null);
});

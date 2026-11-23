import assert from 'node:assert/strict';
import test from 'node:test';
import { DELETION_CONFIRM_LABEL, DELETION_NOTICE, TRAINING_NOTICE, entitlementSummary, trainingConsentBody } from '../src/lib/account.ts';

test('deletion notice states freeze, 15 days and physical purge', () => {
  for (const fragment of ['冻结', '15 天', '物理清除', '无法恢复']) assert.ok(DELETION_NOTICE.includes(fragment));
  assert.ok(DELETION_CONFIRM_LABEL.includes('确认注销'));
});

test('training notice states default off and no feature impact', () => {
  assert.ok(TRAINING_NOTICE.includes('默认不允许'));
  assert.ok(TRAINING_NOTICE.includes('不影响任何功能'));
  assert.deepEqual(trainingConsentBody(true), { granted: true });
  assert.deepEqual(trainingConsentBody(false), { granted: false });
});

test('entitlement summary defaults to free test period', () => {
  assert.equal(entitlementSummary(null), '免费版 · 测试期免费');
  assert.equal(entitlementSummary({ plan: 'free', message: '测试期免费' }), '免费版 · 测试期免费');
  assert.equal(entitlementSummary({ plan: 'pro', message: '测试期免费' }), '专业版 · 测试期免费');
});

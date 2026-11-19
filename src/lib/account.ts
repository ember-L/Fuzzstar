export const DELETION_NOTICE = '注销后账号将被冻结、无法登录；15 天内数据保留但不可访问，到期后所有数据（含云端照片与视频）将被物理清除，无法恢复。';
export const DELETION_CONFIRM_LABEL = '我已了解，确认注销';
export const TRAINING_NOTICE = '是否允许绒星将你的匿名使用数据用于模型训练？默认不允许；拒绝不影响任何功能，你可以随时更改。';

export function trainingConsentBody(granted: boolean): { granted: boolean } {
  return { granted };
}

export function entitlementSummary(entitlement: { plan?: string; message?: string } | null | undefined): string {
  const plan = entitlement?.plan === 'pro' ? '专业版' : '免费版';
  return plan + ' · ' + (entitlement?.message || '测试期免费');
}

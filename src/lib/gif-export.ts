export const GIF_ACTIONS = ['idle', 'happy', 'sad', 'sick', 'crouch', 'look_left', 'look_right'] as const;
export const ACTION_LABELS: Record<string, string> = {
  idle: '待机', happy: '开心', sad: '难过', sick: '不适', crouch: '蹲伏', look_left: '向左看', look_right: '向右看',
};
export const GIF_SHARE_HINT = 'GIF 已添加「绒星 · AI 参考」水印，仅通过系统分享面板发送，不会上传第三方。';

export interface GifTaskView { status: 'pending' | 'succeeded' | 'failed'; downloadUrl: string | null }

export function parseGifTask(task: { status?: string; download_url?: string | null } | null | undefined): GifTaskView {
  if (!task) return { status: 'pending', downloadUrl: null };
  if (task.status === 'succeeded') {
    return task.download_url
      ? { status: 'succeeded', downloadUrl: task.download_url }
      : { status: 'failed', downloadUrl: null };
  }
  if (task.status === 'pending' || task.status === 'running') return { status: 'pending', downloadUrl: null };
  return { status: 'failed', downloadUrl: null };
}

export function gifFileName(petName: string, action: string): string {
  return petName + '-' + (ACTION_LABELS[action] ?? action) + '.gif';
}

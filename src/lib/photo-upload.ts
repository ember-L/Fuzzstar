import type { createSessionClient } from './session';

type Ticket = { media_id: string; upload: { url: string; fields: Record<string, string> } };
type SendUpload = (url: string, init: RequestInit) => Promise<{ ok: boolean }>;

export class PhotoUploadError extends Error {}

export async function uploadPhoto(petId: number, file: Blob, authorized: ReturnType<typeof createSessionClient>['authorized'],
                                  sendUpload: SendUpload, signal: AbortSignal) {
  if (!['image/jpeg', 'image/png', 'image/heic'].includes(file.type) || file.size <= 0 || file.size > 10 * 1024 * 1024) {
    throw new PhotoUploadError('请选择 10 MiB 以内的 JPG、PNG 或 HEIC 照片。');
  }
  const checkActive = () => {
    if (signal.aborted) throw new PhotoUploadError('上传已中止，请重试。');
  };
  checkActive();
  const ticket = await authorized<Ticket>('/media/presign', {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pet_id: petId, content_type: file.type, size_bytes: file.size }),
  });
  checkActive();
  if (!ticket?.upload || !/^[0-9a-f]{32}$/.test(ticket.media_id)) throw new PhotoUploadError('未获得有效的上传凭证。');
  const { upload, media_id: mediaId } = ticket;
  let url: URL;
  try { url = new URL(upload.url); }
  catch { throw new PhotoUploadError('未获得有效的上传地址。'); }
  const local = url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !local) || url.username || url.password) throw new PhotoUploadError('上传地址不安全。');

  const body = new FormData();
  for (const [name, value] of Object.entries(upload.fields)) body.append(name, value);
  body.append('file', file);
  const response = await sendUpload(upload.url, { method: 'POST', body, signal, credentials: 'omit', redirect: 'error' });
  checkActive();
  if (!response.ok) throw new PhotoUploadError('照片上传失败，请重试。');
  const result = await authorized<{ media_id: string; status: string }>(`/media/${mediaId}/complete`, { method: 'POST', signal });
  checkActive();
  if (result?.status !== 'verified' || result.media_id !== mediaId) throw new PhotoUploadError('照片尚未确认，请重试。');
  return mediaId;
}

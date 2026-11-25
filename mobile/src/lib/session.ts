type Tokens = { access_token: string; refresh_token: string };
type Send = (path: string, init?: RequestInit) => Promise<Response>;
type TokenStorage = { read: () => Promise<string | null>; write: (token: string | null) => Promise<void> };

export class ApiError extends Error {
  constructor(publicStatus: number, publicCode: string, message: string) {
    super(message);
    this.status = publicStatus;
    this.code = publicCode;
  }
  readonly status: number;
  readonly code: string;
}

async function read<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data?.code ?? '', data?.message ?? '服务暂时不可用');
  return data as T;
}

function post(body: object): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

export function createSessionClient(send: Send, storage: TokenStorage) {
  let access: string | null = null;
  let renewal: Promise<void> | undefined;

  async function save(tokens: Tokens) {
    await storage.write(tokens.refresh_token);
    access = tokens.access_token;
  }

  async function clear() {
    if (renewal) await renewal.catch(() => {});
    access = null;
    await storage.write(null);
  }

  function renew(rejected: string | null) {
    if (renewal) return renewal;
    if (access && rejected !== access) return Promise.resolve();
    renewal = (async () => {
      const token = await storage.read();
      if (!token) throw new ApiError(401, 'AUTH_REQUIRED', '请登录');
      const response = await send('/auth/refresh', post({ refresh_token: token }));
      if (response.status === 401) {
        access = null;
        await storage.write(null);
      }
      await save(await read<Tokens>(response));
    })().finally(() => { renewal = undefined; });
    return renewal;
  }

  return {
    clear,
    async login(email: string, password: string) {
      await save(await read<Tokens>(await send('/auth/login', post({ email, password }))));
    },
    async register(email: string, password: string) {
      await save(await read<Tokens>(await send('/auth/register', post({ email, password }))));
    },
    async authorized<T>(path: string, init?: RequestInit): Promise<T> {
      if (!access) await renew(null);
      const before = access;
      const request = () => send(path, { ...init, headers: { ...init?.headers, Authorization: `Bearer ${access}` } });
      const response = await request();
      if (response.status !== 401) return read<T>(response);
      await renew(before);
      return read<T>(await request());
    },
  };
}

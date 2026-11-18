# 绒星项目

绒星 App 目前可在本地联调邮箱账号、协议同意、多猫档案和照片上传。产品与设计参考见 [项目规划与设计参考](项目规划与设计参考.md)，交付范围与进度见 [全栈任务规划](docs/superpowers/plans/2026-11-17-rongxing-full-stack.md)。

## 本地运行

### 1. 后端

需要 Python 3.11 或更高版本。若已有 Python 3.9 的 `.venv`，请另建新环境（例如 `.venv311`）再安装依赖。在 `backend` 目录执行：

```sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./rongxing-dev.db
# 仅首次生成。之后启动 API 和邮件 worker 时复用同一个密钥，不要提交到仓库。
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export PRIVACY_VERSION=local-p1 TERMS_VERSION=local-t1
# 示例链接仅供本地使用；正常联调请换成对应版本的真实 HTTPS 原文。
export PRIVACY_URL=https://example.com/privacy TERMS_URL=https://example.com/terms
python -m alembic upgrade head
uvicorn app.main:create_dev_app --factory --host 127.0.0.1
```

[健康检查](http://127.0.0.1:8000/api/v1/health) 只确认 API 进程在线。默认 `app.main:app` 只开放该接口；上面启动的是本地业务联调入口，**不要将它暴露到外网**。SQLite 用于本地开发；生产目标为 MySQL，`DATABASE_URL` 形如 `mysql+pymysql://用户名:密码@主机:3306/数据库名`。迁移不会创建测试账号。

### 2. 邮箱验证

设置 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_FROM` 和 `VERIFICATION_BASE_URL`。邮件验证需要 TLS SMTP 和收件人可达的受控 HTTPS 确认页；`VERIFICATION_BASE_URL` 应以 `/api/v1/auth/verify-email` 结尾，不加查询参数或片段。仅获取链接页面不会验证邮箱，提交确认后才生效。无 SMTP 时可运行下方 API 测试，用临时数据库和模拟投递验证注册流程。

注册及补发只写数据库投递队列。用与 API 相同的 `DATABASE_URL` 和稳定的 `JWT_SECRET`，在 `backend` 目录运行 `python -m app.mail_worker`。命令单次最多处理 20 条，需要外部周期调度；失败退避重试最多 5 次，进程中断可能导致重复投递。补发需要正确密码且只适用于未验证账号，间隔 60 秒，补发后旧链接失效。

### 3. 可选：照片上传联调

使用启用了**版本控制**的 S3 兼容私有桶。配置 `MEDIA_S3_ENDPOINT`、`MEDIA_S3_BUCKET`、`MEDIA_S3_ACCESS_KEY`、`MEDIA_S3_SECRET_KEY`（必须同时提供）以及可选 `MEDIA_S3_REGION`（默认 `us-east-1`）。地址应由 API 和上传客户端共同可达；仅本机测试允许 `http://127.0.0.1` 或 `http://localhost`，其余使用 HTTPS。未配置时其他业务可用，上传返回 `503 MEDIA_UNAVAILABLE`。网页直传需要桶的 CORS 允许对应的前端源发起 POST／GET；不要开启公共读取，也不要记录签名 URL。

1. `POST /api/v1/media/presign` 提交 `pet_id`、`content_type`、`size_bytes`，返回 `media_id` 和 `{upload: {url, fields}}`。支持 JPG、PNG、HEIC，单张 ≤10 MiB。将 `fields` 原样加入 multipart 表单，再将 `file` 作为最后一个字段向 `upload.url` 发起 POST；不向对象存储发送 API 的 Bearer 令牌。
2. 在 10 分钟内调用 `POST /api/v1/media/{media_id}/complete`。API 复核对象字节数及类型、解码图片并限制为单帧和最多 2500 万像素；首次通过后固定对象的 `VersionId`。重复上传不能替换已验证的版本。
3. `GET /api/v1/media/{media_id}` 仅对归属当前账号活跃猫咪的已验证照片签发 60 分钟下载链接。已签发的链接在到期前仍可访问，请视作临时凭证。后续业务应使用 `media_id` 并再次校验其归属和已验证版本，不接受客户端传入的任意媒体 URL。

仅联调照片，不提供视频／音频、单猫主体判定或分身提交。尚未自动清理过期票据、未引用对象及旧版本；不要把通用“删除非当前版本”策略直接用于此桶，否则可能删除仍被引用的版本。

### 4. 移动端 / 网页

需要 Node.js 和 npm。在 `mobile` 目录执行：

```sh
npm install
export EXPO_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
npm run web
```

Expo 开发工具也可用 `npm start` 启动。`127.0.0.1` 示例用于同机网页；真机需要可达的开发 API 地址，发布版只接受 HTTPS。原生端通过 SecureStore 保存刷新令牌；网页仅在内存保留会话，刷新页面需重新登录。「在此设备退出登录」仅清理本机令牌，不吊销服务端会话。

「我的」提供邮箱登录、当前版本协议确认和猫咪档案管理。登录并同意协议后，在首页选中猫咪 →「选择照片」→「确认上传」。切猫会清除待上传照片；后端确认后才显示「照片已验证」，这不是分身生成，也不提供照片列表。健康和聊聊仍是占位；首页不会为未评估的猫咪生成健康分。首页素材源自 Figma，正式发布前需确认授权或替换。

## 本地 API 范围

| `/api/v1` 接口 | 行为 |
| --- | --- |
| `POST /auth/register` | 邮箱、密码；接受请求并排队验证邮件，已注册邮箱得到相同响应 |
| `GET /auth/verify-email`、`POST /auth/verify-email` | 展示确认页 / 提交令牌；24 小时有效、仅可使用一次 |
| `POST /auth/resend-verification` | 邮箱、密码；未验证账号可请求补发 |
| `POST /auth/login`、`POST /auth/refresh` | 已验证邮箱可登录；刷新令牌轮换，重放旧令牌会吊销所属会话 |
| `GET /me` | Bearer JWT；读取当前账号 |
| `GET/POST /consents` | 读取协议链接及版本 / 同意当前版本；训练授权默认关闭，不提供设置入口 |
| `GET/POST /pets`、`GET/PATCH/DELETE /pets/{id}` | 须登录并同意当前协议；最多 5 只活跃猫咪；删除为软删 |
| `POST /media/presign`、`POST /media/{id}/complete`、`GET /media/{id}` | 本地照片上传签名、验证与版本化下载；须已登录、同意当前协议且拥有活跃猫咪 |
| `GET /tasks/{task_id}` | 只读轮询；须登录并同意当前协议，只能查询本人活跃猫咪的任务。响应为 `task_id`、`type`、`status`、`result`，不返回内部请求载荷 |

认证 POST 使用数据库按来源 IP 固定分钟限流（30 次／分钟），不是上线需要的分布式防滥用方案。任务只由可信业务服务入库；同猫咪、同任务类型、同幂等键的相同载荷只创建一条记录。任务可由 worker 认领，状态为 `pending`、`running`、`succeeded` 或 `failed`；15 分钟的认领租约过期后可再次认领，初次执行加最多两次重试。当前没有公开的任务提交接口或运行中的 AI worker，移动端也尚未接入轮询。

## 验证命令

```sh
# backend（激活虚拟环境后）
python -m unittest discover -s tests -v

# mobile
npm run typecheck
npm run lint
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --test tests/*.test.mjs
```

任务测试也可针对已迁移的独立 MySQL 测试库运行（会留下测试数据，勿指向业务库）：

```sh
TASK_TEST_DATABASE_URL="$DATABASE_URL" python -m unittest discover -s tests -p test_tasks.py -v
```

照片存储端到端检查默认跳过。准备启用版本控制的**独立可丢弃测试桶**（检查会留下合成图片对象和版本），按上文配置环境后运行：

```sh
MEDIA_S3_SMOKE=1 python -m unittest discover -s tests -p test_media_storage.py -v
```

MySQL 8.4 已验证最新迁移及任务并发去重、认领。网页用真实 API 和模拟对象存储验过切猫、非法照片拒绝与成功上传；实际 S3/MinIO 上传策略、生产 OSS 适配、真实 SMTP、正式协议、iOS/Android 真机及生产队列仍待验收。

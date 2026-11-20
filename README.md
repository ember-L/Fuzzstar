# 绒星项目

绒星 App 目前可在本地联调邮箱账号、协议同意、多猫档案、照片上传、分身生成任务（arq worker + 移动端轮询）、首页分身播放（占位首帧 → 个人 idle 片）、健康初筛（版本化规则硬判定 + 红线紧急分流 + 存证）、首页健康聚合（状态卡 + 健康分 + 扣分明细）、饮食记录／喂养参考（快录三步 + 本地日聚合 + RER/DER 公式参考）与文字聊天／录音解读（人设回复 + 红线分流 + 音频情绪解读 + 离线补发）。产品与设计参考见 [项目规划与设计参考](项目规划与设计参考.md)，交付范围与进度见 [全栈任务规划](docs/superpowers/plans/2026-11-17-rongxing-full-stack.md)。

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

1. `POST /api/v1/media/presign` 提交 `pet_id`、`content_type`、`size_bytes` 和可选 `kind`（`photo` 默认／`video`／`audio`），返回 `media_id` 和 `{upload: {url, fields}}`。照片支持 JPG、PNG、HEIC，单张 ≤10 MiB；视频支持 MP4、MOV，单段 ≤50 MiB；音频支持 MP4、M4A、MP3、WAV、WebM，单段 ≤10 MiB 且时长 1–60 秒。将 `fields` 原样加入 multipart 表单，再将 `file` 作为最后一个字段向 `upload.url` 发起 POST；不向对象存储发送 API 的 Bearer 令牌。
2. 在 10 分钟内调用 `POST /api/v1/media/{media_id}/complete`。API 复核对象字节数及类型：照片解码并限制为单帧和最多 2500 万像素；视频用 ffprobe 校验含视频流且时长 ≤30 秒（部署环境需要 ffmpeg）。首次通过后固定对象的 `VersionId`。重复上传不能替换已验证的版本。
3. `GET /api/v1/media/{media_id}` 仅对归属当前账号活跃猫咪的已验证照片签发 60 分钟下载链接。已签发的链接在到期前仍可访问，请视作临时凭证。后续业务应使用 `media_id` 并再次校验其归属和已验证版本，不接受客户端传入的任意媒体 URL。

照片验证通过后，`POST /api/v1/pets/{pet_id}/avatar` 提交 `media_id` 即可创建分身生成任务（202 返回 `task_id` 和按猫咪体型选择的 `placeholder_manifest`）；同猫已有进行中任务时合并返回同一 `task_id`，失败任务可用同一照片重试。猫咪档案支持 `body_type`（slim/standard/chubby，默认 standard），决定占位片分组。过期未验证票据由 worker 在到期 1 小时后清理；被引用的对象版本按 `VersionId` 保留，不要把通用“删除非当前版本”策略直接用于此桶。单猫主体判定仍待后续需求。

### 4. 分身生成 worker

任务以数据库为准，Redis/arq 只做分发。在 `backend` 目录用与 API 相同的 `DATABASE_URL` 和 `MEDIA_S3_*` 配置，另设 `REDIS_URL`（默认 `redis://127.0.0.1:6379`）和 `DASHSCOPE_API_KEY`，运行：

```sh
python -m arq app.worker.WorkerSettings
```

worker 每 5 秒 sweep 一次：分发 pending 任务、回收过期租约、把耗尽重试的过期任务置为 failed，并清理过期未验证照片票据。单步失败按数据库 attempts 重试（初次 + 最多两次），arq 自身不重复重试。分身管线先生成底图，再为 7 个动作（idle/happy/sad/sick/crouch/look_left/look_right）各生成一条短片，单条失败不阻塞其余；≥5 条就绪判定可用。初筛建议任务（screening_analysis）调用 qwen-max 生成建议文本，失败重试耗尽后持久化状态档模板。当前 Provider 为 DashScope（qwen-image-edit 底图 + wanx2.1-i2v-turbo 图生视频 + qwen-max 建议），真实生成质量、耗时与成本尚未验收；测试用 fake provider 已验证完整管线。

### 5. 占位片库与动作映射

占位片库为 3 体型 × 7 动作共 21 条无声循环短片（720p、H.264、≤5 秒、首尾对齐），随仓库保存在 `backend/assets/placeholders`（当前 v1 为程序化临时素材，正式发布前需替换为授权素材并升版本）。重建或升版本在 `backend` 目录运行：

```sh
python -m scripts.build_placeholder_library --out assets/placeholders --version v1
```

API 启动时加载占位库（可用 `PLACEHOLDER_DIR` 覆盖路径）与动作映射 `backend/rules/action_map.yaml`（可用 `RULES_DIR` 覆盖目录）。占位库缺失时占位清单与分身提交返回 `503 PLACEHOLDER_UNAVAILABLE`；动作映射缺失时 `GET /api/v1/config/action-map` 返回 `503 CONFIG_UNAVAILABLE`。占位片经 `GET /api/v1/avatar/placeholders/{version}/{body_type}/{action}.mp4` 公开读取（通用内容，版本化路径按 immutable 缓存）；清单与动作映射接口须登录并同意当前协议。动作映射按 FRD 附录 C 版本化（当前 `am-2026-11-18`），供 T07 播放器联动使用。

`GET /api/v1/pets/{pet_id}/avatar` 返回最近一次分身任务的状态、占位清单，以及成功后底图与各动作片的 60 分钟签名播放地址（失败动作标记 failed，由客户端回退占位）；从未提交过返回 404。

### 6. 健康初筛

初筛为纯规则硬判定，不调用 LLM。规则包随仓库保存在 `backend/rules`（可用 `RULES_DIR` 覆盖）：`symptoms.yaml`（sx-2026-11-19，15 项症状、时长／频次分档、精神食欲选项与单独就医触发）、`redlines.yaml`（rl-2026-11-19，6 类红线含「呕吐 >24h」派生判定）、`scoring.yaml`（sc-2026-11-19，observe −10／vet −30／urgent −60）。规则缺失或非法时相关接口返回 `503 CONFIG_UNAVAILABLE`。

- `GET /api/v1/config/symptoms` 下发版本化问卷配置（选项、分档、追问适用项、红线选项）。
- `POST /api/v1/pets/{pet_id}/screenings` 提交精神／食欲（必答）、症状多选及追问（时长必填，适用项频次必填，严重度开关与 ≤255 字备注）、红线选项与存证 `media_ids`。缺项返回 `400 VALIDATION_ERROR` 并在 `detail.fields` 定位错误项；存证照片 ≤3 张、视频 ≤1 段，须同猫已验证媒体。命中红线立即返回 `urgent` 与就医准备清单（附录 F 文案），零 LLM、不受配额限制；非红线按规则分级（单症状按追问，多症状取最高；明显沉郁或拒食单独就医）。
- 每次提交存档答案、症状、`rules_version` 与判定快照（`triage_json`），同版本规则结果可复现；非 normal 结果写入健康事件；复查覆盖（F06-3）：新初筛结论自动解决该猫旧的活跃 screening 事件（`resolved_at` 非空），健康分与状态即时重算。`GET /api/v1/screenings/{id}` 回看详情，`GET /api/v1/pets/{id}/screenings` 分页历史，`DELETE /api/v1/screenings/{id}/media/{media_id}` 删除存证（仍被其他记录或分身任务引用时只删关联，保留对象版本）。
- 非 urgent 提交同时入队 `screening_analysis` 异步任务（幂等键为记录编号），由 worker 调用 qwen-max 仅生成观察／记录／就医建议文本，不参与分级、健康分与红线决策；输出约定 JSON（text + tips），解析失败或含「确诊」「治疗」措辞即判无效，按数据库 attempts 重试（初次 + 最多两次）。每次 LLM 调用（含失败尝试）写入 `ai_usage_logs` 审计。
- 建议降级：任务失败或提交后 60 秒仍未就绪时，详情接口按状态档返回模板建议（`rules/advice_templates.yaml`，at-2026-11-19，随 `RULES_DIR` 加载，缺失返回 `503 CONFIG_UNAVAILABLE`），分级与存档不受影响；worker 重试耗尽也会持久化模板。urgent 红线不建任务、零 LLM、无用量记录，提交时即持久化模板建议。

### 7. 首页健康聚合

- `GET /api/v1/pets/{pet_id}/health` 返回状态档（normal/observe/vet/urgent，取最新有效事件集合最高档）、健康分、扣分明细与概览入口。纯规则计算：`score = max(0, 100 − Σ 活跃事件有效扣分)`（权重 `rules/scoring.yaml`，sc-2026-11-19：observe −10 / vet −30 / urgent −60），禁止 LLM 打分、禁止默认 100；无初筛且无事件 → `score=null`，UI「未评估 --」。
- observe 事件 72 小时无复查在读时衰减为 0 分扣（明细保留并标「已衰减」，不再驱动状态与分身动作）；vet/urgent 不自动衰减，须复查解决。扣分明细逐项含来源初筛、症状、扣分、生效时间、衰减状态与 `rules_version`，可追溯。
- urgent 状态返回 `urgent_card`（附录 F 就医文案），首页红色卡 + 常驻就医入口。概览含最近初筛时间、今日饮食（T12 已交付：`diet_today` 按客户端 `tz_offset_minutes` 聚合当日克数／热量／笔数，与饮食接口同源）与最新体重（`latest_weight`，T13 已交付：来自最新体重记录，未记录为 null）。
- 详情接口的 `advice` 字段为 `{status: pending|ready|degraded, source, text, tips}`：规则分级立即返回，建议就绪后填充；移动端结果页对 pending 按 60 秒轮询 `screening_analysis`，结束后重拉详情，degraded 显示模板并提示「AI 建议暂不可用」。真实 qwen-max 质量与成本仍待 `DASHSCOPE_API_KEY` 验收，测试用 fake provider 已验证完整链路。

### 8. 饮食记录与喂养参考

- `POST /api/v1/pets/{pet_id}/diet` 快录：类型 dry/wet/snack/other、克数 >0 且 ≤2000（保留 1 位小数）、时间默认现在、可回改 ≤7 天（未来容忍 60 秒时钟偏差）、备注 ≤255 字；校验失败 400 并在 `detail.fields` 定位。热量按 `rules/feeding.yaml`（fd-2026-11-19，随 `RULES_DIR` 加载，缺失 503 `CONFIG_UNAVAILABLE`）标准密度估算：干粮 3.8 kcal/g、湿粮 0.9 kcal/g，零食/其他不计热量（50g 干粮 = 190.0 kcal）。
- `GET /api/v1/pets/{pet_id}/diet?date=YYYY-MM-DD&tz_offset_minutes=±N` 按客户端本地自然日聚合（合计克数/热量/笔数 + 逐条明细）；不带 date 返回最近记录（limit ≤50，倒序）供时间线混排。`DELETE /api/v1/pets/{pet_id}/diet/{record_id}` 删除后合计即时重算。
- `GET /api/v1/pets/{pet_id}/feeding-reference` 用最新体重与 FRD 附录 E 公式：RER=70×kg^0.75，DER=RER×生命阶段系数（<4 月 3.0 / 4–12 月 2.0 / 成年绝育 1.2 / 未绝育 1.4 / ≥11 岁 1.1；无生日按成年），换算干/湿粮克数并给 ±10% 区间；无体重只给记录引导，不输出数值。输出一律携带尾注「以上为公开营养学公式换算的参考值,非医嘱;请结合体况与兽医建议调整。」。饮食快录支持 `Idempotency-Key` 头（≤64 字符）：同键同载荷回放返回同一记录（`Idempotent-Replay: true`），同键异载荷 409 `IDEMPOTENCY_CONFLICT`；键按用户隔离、保留 7 天由 worker sweep 清理（T14）。
- 移动端 `/diet/{petId}` 快录三步（进入→输克数→记一笔，类型默认干粮、时间默认现在，回改用预设档位覆盖 ≤7 天）+ 日明细前后翻页与逐条删除；`/feeding/{petId}` 展示计算依据与区间；首页「今日饮食」实数据并跳转快录，「最新体重」显示最近测量；健康时间线并入饮食记录（按本地日分组倒序）。

### 9. 体重记录与趋势

- `POST /api/v1/pets/{pet_id}/weights` 录入体重：0.1–30 kg、精度 0.01 kg（超范围或超 2 位小数拦截并定位字段）；时间默认现在，可回改任意过去时间（未来容忍 60 秒）；同日多次全部保留。
- `GET /api/v1/pets/{pet_id}/weights` 返回最近记录（倒序，limit 默认 50 ≤200）与 90 天趋势：points 升序；骤变提示＝最新记录对比之前 7 天内任一基线变化 ≥±10%（取 |pct| 最大），alert 含 direction/pct/baseline/latest 与 suggestion='screening'；无记录给空态引导。
- 档案同步（AC-08-1）：`PetProfile.latest_weight{weight_kg,measured_at}` 随 GET /pets、GET /pets/{id}、POST、PATCH 返回；首页概览与喂养参考同源，录入后即时更新（喂养参考由引导切换为数值输出）。
- 移动端 `/weight/{petId}`：录入卡（数字键盘＋预设时间档位 ≤72h）→ 记录后即时更新确认；骤变红卡显示「7 天内体重下降 12.5%」＋「建议做一次健康初筛」并可跳转初筛入口（AC-08-2）；90 天趋势折线（react-native-svg，单点居中、空态引导）＋历史列表；首页「最新体重」卡跳转体重页（无记录引导「点击记一笔」）；健康时间线并入体重记录。分钟级任意回改待 T19 体验评审。

### 10. 喂养提醒与浅离线（T14）

- 服务端幂等：`request_idempotency` 表（migration 12）按 (user_id, key) 唯一，记录请求哈希与首次成功响应；饮食与聊天 POST 已接入，回放不重复计数、不改动原记录时间、不重复调用 LLM。校验失败（4xx）不缓存，修正后可复用同键。
- 移动端浅离线（F07-5）：饮食快录失败且属可重试类（网络错误／5xx／408／429）时写入本机持久队列（native expo-sqlite `rongxing-offline.db`，web 内存），页面显示「待同步」条目；恢复联网后同步循环（5 秒轮询 + 回到前台 + web online 事件）带原幂等键自动补发，≤10 秒内完成且不产生重复记录；4xx 业务拒绝出队并提示原因。音频不入队（需在线）。
- 聊天缓存（F09-6）：`chat_cache` 本机镜像与 `chat_text` 入队通道已随 T15 聊天页接线（按消息 id 去重合并、弱网可读、失败补发幂等防重）。
- 喂养提醒（F10-2）：`/reminders/{petId}` 每猫独立开关与多时段（默认关闭、上限 6 个、常用 08/12/18/22 + 自定义 HH:MM），设置仅存本机；保存即注册 DAILY 本地通知（expo-notifications，文案含宠物名，点击直达该猫饮食页），关闭或删猫自动取消；权限拒绝时提示并可重新授权；网页端不支持本地通知。连续 3 天准时触发与 ±5 分钟精度待真机验收。

### 11. 文字聊天、录音解读与安全边界（T15/T16）

- 每猫一线程自动创建（`POST /pets/{id}/chat/sessions`，已存在返回 200）；上下文为最近 20 条消息＋档案（名字／月龄／绝育／体型）＋最新初筛状态语气；输入 ≤500 字、回复 ≤100 字。
- 人设与红线配置版本化于 `rules/chat.yaml`（ct-2026-11-19，随 `RULES_DIR` 加载，缺失 503 CONFIG_UNAVAILABLE）。聊天模型 qwen-plus（`DASHSCOPE_API_KEY`）；LLM 失败／禁词（确诊／治疗／诊断）／解析失败降级模板安抚（source=template），对话不中断；调用写 ai_usage_logs（task_id 为 null）。
- 红线关键词（张口呼吸／百合／抽搐等 25 项）零 LLM：直接返回「建议立即就医」引导卡（可跳初筛）＋painful 情绪，不写用量记录。常驻免责：「AI 结果仅供日常健康管理参考,不替代专业兽医诊断」。
- 情绪标签（happy/relaxed/annoyed/fearful/painful/seeking_attention）按附录 C 映射动作；移动端回复到达经情绪总线触发首页分身播一次回待机（AC-09-5，真机播放观感待验收）。
- 聊天 POST 支持 `Idempotency-Key` 回放（同键同 body 返回同一消息对，不再调用 LLM）；移动端发送失败入 chat_text 队列联网自动补发，chat_cache 本机镜像弱网可读（AC-09-6）。
- 录音解读（F09-3/4）：聊天页录音 1–60 秒（expo-audio，麦克风权限，60 秒自动停止；网页端不支持录音、权限拒绝均提示且文字聊天不受影响），`kind=audio` presign 直传复核后 `POST /chat/sessions/{sid}/messages` 返回 202 `task_id`（audio_interpret，客户端 45 秒超时）；同音频已有进行中任务合并返回同一 task（200），失败重试为新任务。
- worker 调 qwen2-audio-instruct 解读情绪＋置信度，再由 qwen-plus 按情绪生成 ≤100 字回复；置信度 <0.4 标注「不太确定」，解读失败或情绪非法→「未识别」＋通用安抚（任务仍 succeeded），文字聊天不阻塞（AC-09-3/4）；音频不入离线队列。解读与回复调用写 ai_usage_logs（kind=audio/llm，带 task_id）。
- 娱乐边界尾注固定：「情绪解读为娱乐性参考,置信度仅供判断展示。」；真实 qwen2-audio 解读质量待凭证验收。

### 12. 配额、隐私与 GIF 分享（T17）

- 配额（F11）：`usage_counters` 表（migration 14）按服务器 UTC 自然日原子计数，默认初筛 10／分身 3／聊天 50 条，环境变量 `QUOTA_SCREENING`／`QUOTA_AVATAR`／`QUOTA_CHAT` 热调（须 >0）。超限返回 429 `QUOTA_EXCEEDED`（含「明日再试」）；红线初筛豁免（先判红线再扣配额）；分身仅新建任务计数（进行中合并不计），聊天仅文字计数（录音解读不占配额）。`GET /quota` 返回三项 used/limit；移动端初筛／上传／聊天入口超限置灰并提示，紧急信号不受限制。
- 隐私与注销（F12）：训练授权默认关闭，`POST /consents/training` `{granted}` 单独授权（版本随隐私协议），v1 不读取任何训练数据。`DELETE /me` 返回 202 `{purge_after}`（15 天），账号立即冻结（登录／刷新／访问令牌全部拒绝），重复申请返回 200 与原期限。arq worker sweep 对到期 `deletion_jobs` 执行物理清除：先删对象存储版本（照片／分身底图与动作片／GIF），再按外键顺序级联删除业务数据，`ai_usage_logs` 匿名化（user_id/task_id 置 NULL，仅保留聚合统计），最后删除账号；存储不可用则本轮失败下轮重试。媒体单条删除自 T09 起已有引用保护与对象同步删除。
- 会员（F11-4）：`GET /plans` 为 free/pro 代码目录（无价格），`GET /me/entitlement` 默认 free＋「测试期免费」；`plans`/`entitlements` 表已预留，不接支付。
- GIF 分享（F13）：`POST /pets/{id}/share/gif` `{action}` 要求最近一次成功分身的该动作已就绪，否则 409 `AVATAR_NOT_READY`；同动作进行中任务合并返回 200。`gif_export` 任务经 ffmpeg 调色板转码 480p／≤5 秒／12fps，烧录水印「绒星 · AI 参考」（字体 `GIF_WATERMARK_FONT` 或自动探测 PingFang/Noto CJK，缺字体任务失败重试）；`GET /tasks/{id}` 对 succeeded 的 gif 任务追加 `download_url`（60 分钟签名）。移动端 60 秒轮询超时，native 经 expo-file-system 下载后 expo-sharing 系统分享面板，网页降级为打开下载链接。

### 13. 移动端 / 网页

需要 Node.js 和 npm。在 `mobile` 目录执行：

```sh
npm install
export EXPO_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
npm run web
```

Expo 开发工具也可用 `npm start` 启动。`127.0.0.1` 示例用于同机网页；真机需要可达的开发 API 地址，发布版只接受 HTTPS。原生端通过 SecureStore 保存刷新令牌；网页仅在内存保留会话，刷新页面需重新登录。「在此设备退出登录」仅清理本机令牌，不吊销服务端会话。

「我的」提供邮箱登录、当前版本协议确认和猫咪档案管理。登录并同意协议后，在首页选中猫咪 →「选择照片」→「确认上传」。切猫会清除待上传照片并中断轮询；照片验证后自动提交分身生成，首页舞台立即播放该体型的占位首帧（无需额外请求），随后每 2 秒轮询任务状态，页面不可见时暂停，10 分钟超时后停止轮询并提示（后台任务继续）。生成成功后个人片在下一个待机循环边界淡入替换占位片（300ms 淡出/淡入，动作播放中途不切换）；失败、超时或不足 5/7 动作时给出可理解的提示，并可在上传卡片「重试生成」。首页播放器按版本化动作映射（`GET /config/action-map`，本地缓存并按版本比对，挂载/回到前台/每 60 秒刷新）驱动：健康状态持续待机、情绪与点按/长按一次性动作播完回待机；单动作缺失或播放损坏逐级回退 个人片→占位片→静态底图呼吸缩放，断网无缓存不白屏。视频文件按内容版本缓存于本机（expo-sqlite 索引 + 文件系统，LRU 默认上限 200 MB）；网页端走浏览器 HTTP 缓存。「健康」页提供初筛入口：按猫开始问卷（动态追问、缺项定位、紧急信号勾选、照片／视频存证选择与上传），提交后展示规则结果、红线就医清单与免责声明；AI 护理建议异步填充（生成中提示、60 秒超时或失败显示状态档模板并标注「AI 建议暂不可用」），并可回看历史与删除存证。健康时间线（`/timeline/{petId}`，首页与健康页均有入口）按本地日分组倒序混排初筛与饮食记录（状态色标、红线标记、点击进结果页或当日饮食明细），体重记录（T13 已并入，点击进体重页）。observe 初筛结果页自动注册 +24 小时本地复查提醒（expo-notifications，文案含宠物名，点击直达该猫初筛入口）；提前复查提交或删除猫咪时自动取消该猫全部待触发提醒；权限拒绝时降级为应用内横幅（健康页与结果页），「我的」提供重新授权入口；网页端无本地通知，恒走横幅路径。架构原定 notifee 需自定义 dev client，现以 Expo 官方 expo-notifications 薄适配层（`src/lib/notifications.ts`）替代，偏差待 T19 评审；通知真实触发、±5 分钟精度与点击跳转待真机验收。首页健康卡随焦点与切猫重拉：状态档文案与分级颜色、健康分（未评估显示「未评估 --」）、可展开扣分明细（症状／扣分／生效时间／衰减标注／规则版本）；urgent 红色卡 + 常驻「立即就医」入口。健康状态同时驱动分身待机动作（observe/vet/urgent → sick，按版本化映射，无需发版）。概览「最近初筛」显示时间并跳转历史，「和我聊聊」跳转聊聊页（T15：每猫一线程、缓存优先弱网可读、发送失败入队补发、红线就医引导卡、情绪回复联动首页分身播一次；T16：麦克风按钮录音 1–60 秒、60 秒自动停止，权限拒绝或网页端提示且文字聊天不受影响，上传后「解读中」2 秒轮询、45 秒超时，成功后情绪气泡显示情绪与置信度（<0.4「不太确定」、失败「未识别」+通用安抚），语音气泡点击播放，情绪回复联动首页分身播一次；录音需在线、不入离线队列）；「今日饮食」显示当日合计并跳转快录（无记录引导「记一笔」），「最新体重」显示最近测量值（T13 已交付，点击进体重页录入）。首页素材源自 Figma，正式发布前需确认授权或替换。真机播放观感与缓存命中仍待设备验收。饮食页断网快录显示「待同步」并在联网后自动补发（幂等防重）；饮食页入口可达「喂养提醒」页（每猫开关 + 多时段，默认关闭，仅本机持久化）。「我的」新增今日用量（三项 used/limit 与超限提示）、会员权益（测试期免费）、训练数据授权（默认关闭，单独确认开关）与注销账号（两步确认＋15 天物理清除说明，提交后冻结并清理本机会话）；首页新增 GIF 导出分享（选动作→导出→系统分享面板，水印由服务端烧录，60 秒超时提示）。

### 14. 运维、观测与质量（T18）

- 结构化 JSON 日志（`rongxing.access`/`worker`/`quota`）：request_id（X-Request-ID 复用或生成并回写）、path（不含 query）、status、duration_ms、user_id 尽力提取；任务 claimed/finished/failed 事件；**不落请求体/邮箱/密码/令牌**（单测注入敏感值验证）。配额拒绝审计表 `quota_denials`（migration 15）业务回滚不丢记录，90 天清理。
- 运营报表 `python -m scripts.ops_report --days 7 [--json]`（只读）：AI 调用/token/成本、每日成本、单用户成本 Top10（注销匿名桶）、任务成功率/重试/p95 时长、配额拒绝与今日用量。
- 本地性能门禁 `python -m scripts.latency_sample --samples 200`：8 个非 AI GET 端点进程内采样，总体 p95≤500ms 退出码门禁；2026-11-20 证据 n=1600 p95 2.34ms（本地方法学，非生产/真机结论）。
- 迁移回滚与备份恢复演练已在 MySQL 8.4 执行（head↔base 全程、dump→恢复→26 表行数一致）；演练修复 10 个迁移 downgrade 的 MySQL 1553 缺陷。完整 runbook、告警阈值建议、回归覆盖矩阵与外部待办见根目录 `OPERATIONS.md`。
- 真机指标（冷启动≤3s/缓存首帧≤1s/crash-free≥99%）、Sentry、生产 HTTPS 与告警接线、100 宠压测仍待外部。

## 本地 API 范围

| `/api/v1` 接口 | 行为 |
| --- | --- |
| `POST /auth/register` | 邮箱、密码；接受请求并排队验证邮件，已注册邮箱得到相同响应 |
| `GET /auth/verify-email`、`POST /auth/verify-email` | 展示确认页 / 提交令牌；24 小时有效、仅可使用一次 |
| `POST /auth/resend-verification` | 邮箱、密码；未验证账号可请求补发 |
| `POST /auth/login`、`POST /auth/refresh` | 已验证邮箱可登录；刷新令牌轮换，重放旧令牌会吊销所属会话 |
| `GET /me` | Bearer JWT；读取当前账号 |
| `GET/POST /consents`、`POST /consents/training` | 读取协议链接及版本 / 同意当前版本；训练授权默认关闭，`{granted}` 单独开关（T17） |
| `GET /quota` | 当日用量：初筛／分身／聊天 used/limit（UTC 自然日，env 热调；红线豁免、录音不占聊天配额） |
| `GET /plans`、`GET /me/entitlement` | free/pro 代码目录（无价格）与当前权益（默认 free＋「测试期免费」，不接支付） |
| `DELETE /me` | 注销申请：202 `{purge_after}`（15 天）并立即冻结账号；重复申请 200 原期限；到期 worker 物理清除数据库与对象存储，审计日志匿名化 |
| `POST /pets/{id}/share/gif` | GIF 导出：最近成功分身对应动作须 ready（否则 409），同动作进行中合并 200，否则 202 `task_id`（gif_export，60 秒客户端超时） |
| `GET/POST /pets`、`GET/PATCH/DELETE /pets/{id}` | 须登录并同意当前协议；最多 5 只活跃猫咪；删除为软删；档案含 `body_type`（slim/standard/chubby）与 `latest_weight`（来自最新体重记录，T13） |
| `POST /media/presign`、`POST /media/{id}/complete`、`GET /media/{id}` | 照片／视频／音频上传签名、验证与版本化下载（`kind` 区分，视频 ≤50 MiB／30 秒，音频 ≤10 MiB／1–60 秒）；须已登录、同意当前协议且拥有活跃猫咪 |
| `POST /pets/{id}/avatar` | 提交已验证照片生成分身；202 返回 `task_id` 与按体型选择的 `placeholder_manifest`，同猫进行中任务合并，失败任务可重试 |
| `GET /pets/{id}/avatar` | 最近一次分身任务状态与结果；成功后底图/动作片为 60 分钟签名地址，失败动作标记 failed；从未提交返回 404 |
| `GET /avatar/placeholder-manifest` | 版本化占位清单（3 体型 × 7 动作）；须登录并同意当前协议 |
| `GET /avatar/placeholders/{version}/{body_type}/{action}.mp4` | 占位片公开读取；版本化路径 immutable 缓存，白名单外 404 |
| `GET /config/action-map` | 版本化动作映射（FRD 附录 C）；须登录并同意当前协议 |
| `GET /config/symptoms` | 版本化初筛问卷配置（症状／分档／红线选项）；须登录并同意当前协议 |
| `POST /pets/{id}/screenings` | 提交初筛：规则硬判定，201 返回状态／分级／红线卡／免责声明／`task_id`（urgent 为 null）；缺项 400 定位错误项 |
| `GET /screenings/{id}`、`GET /pets/{id}/screenings` | 初筛详情回看与历史（limit ≤50）；详情含 `advice`（pending/ready/degraded）；仅本人活跃猫咪 |
| `DELETE /screenings/{id}/media/{media_id}` | 删除存证关联；无其他引用时连同对象版本删除 |
| `GET /pets/{id}/health` | 首页健康聚合：状态档 + 健康分（无初筛且无事件为 null）+ 扣分明细（含衰减与规则版本）+ 最近初筛 + 今日饮食（tz_offset_minutes）+ 最新体重；urgent 附就医卡 |
| `POST /pets/{id}/diet`、`GET /pets/{id}/diet`、`DELETE /pets/{id}/diet/{record_id}` | 饮食快录（克数/时间/备注校验定位；可选 `Idempotency-Key` 幂等回放）、本地日聚合或最近列表、删除重算 |
| `GET /pets/{id}/feeding-reference` | 最新体重 + 附录 E 公式 RER/DER 与干/湿粮 ±10% 区间；无体重给引导；恒带「参考值,非医嘱」尾注 |
| `POST /pets/{id}/weights` | 体重录入：0.1–30 kg 精度 0.01，可回改、同日多次保留；即时更新档案最新体重与喂养参考 |
| `GET /pets/{id}/weights` | 最近记录（倒序 limit ≤200）＋ 90 天趋势点与 7 天内 ±10% 骤变提示（建议初筛） |
| `POST /pets/{id}/chat/sessions`、`GET /pets/{id}/chat/sessions` | 每猫一线程自动创建（已存在返回 200）；须登录并同意当前协议 |
| `POST /chat/sessions/{sid}/messages`、`GET /chat/sessions/{sid}/messages` | 文字发送（≤500 字，可选 `Idempotency-Key` 回放；红线零 LLM＋就医引导卡）、音频解读（`kind=audio`＋`media_id`，202 `task_id`，同音频合并 200）与历史（倒序 limit ≤200＋before 游标） |
| `GET /tasks/{task_id}` | 只读轮询；须登录并同意当前协议，只能查询本人活跃猫咪的任务。响应为 `task_id`、`type`、`status`、`result`，不返回内部请求载荷；gif_export succeeded 追加 `download_url`（60 分钟签名） |

认证 POST 使用数据库按来源 IP 固定分钟限流（30 次／分钟），不是上线需要的分布式防滥用方案。任务只由可信业务服务入库；同猫咪、同任务类型、同幂等键的相同载荷只创建一条记录。任务可由 worker 认领，状态为 `pending`、`running`、`succeeded` 或 `failed`；15 分钟的认领租约过期后可再次认领，初次执行加最多两次重试。分身提交接口与 arq worker 已接入，移动端按 2 秒轮询并在不可见时暂停；真实 DashScope 生成仍待凭证验收。首页健康聚合（T08）已接线：健康分纯规则、复查覆盖旧事件、observe 72h 读时衰减、urgent 常驻就医入口；今日饮食概览（T12）与最新体重（T13）已同源填充：体重录入即时更新档案、首页与喂养参考，90 天趋势与 ±10% 骤变提示已交付（AC-08-1/2 本地验证）。初筛时间线与 24h 复查提醒（T11）已接线：按日倒序分组、observe 注册/复查与删猫取消、权限拒绝横幅降级与重新授权；通知真实触发待真机。浅离线与幂等（T14）已接线：饮食失败入本机持久队列、联网 ≤10s 带原键补发不重复（AC-07-5 本地验证），服务端幂等表 7 天清理；喂养提醒每猫多时段 DAILY 通知已注册（AC-10-2 连续准时待真机）；文字聊天（T15）已接线：每猫线程、20 条上下文人设、红线零 LLM 引导、禁词/失败模板降级、情绪联动、聊天幂等回放与离线补发（AC-09-1/2/5/6/7 本地验证）；真实 qwen-plus 质量待凭证。录音解读（T16）已接线：1–60 秒录音直传复核、audio_interpret 异步 45 秒超时、qwen2-audio 情绪+置信度（<0.4「不太确定」）、解读失败「未识别」+通用安抚不阻塞文字、娱乐边界尾注与 audio/llm 用量审计（AC-09-3/4 本地验证）；真实 qwen2-audio 质量待凭证。配额、隐私与分享（T17）已接线：UTC 自然日配额（10/3/50，env 热调）超限 429「明日再试」、红线豁免、入口置灰；训练授权单独开关默认关闭；注销二次确认→冻结→15 天到期物理清除（数据库＋对象存储版本，审计匿名化，AC-12-1～6 本地验证含清除模拟与对象删除核验）；plans/entitlement 只读「测试期免费」；GIF 导出 480p≤5s 水印「绒星 · AI 参考」＋签名下载＋系统分享（AC-13-1/2 本地验证，真机分享面板待设备）。设计评审清单、文案审计与发布 runbook／指标定义（T19/T20 本地交付）见根目录 `DESIGN_REVIEW.md` 与 `RELEASE.md`：专业评审执行、Figma 对照、签名分发与内测执行待外部；worker 并发已限 2（FRD 内测门槛）。观测与质量（T18）本地部分已交付：结构化脱敏日志＋拒绝审计、运营报表脚本、非 AI p95 本地门禁（n=1600 p95 2.34ms）、MySQL 迁移回滚与备份恢复演练（修复 10 个 downgrade 的 MySQL 1553 缺陷）、全量回归 407+155；真机指标/Sentry/生产 HTTPS/告警/压测待外部，runbook 见 `OPERATIONS.md`。

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

worker 的 Redis 集成与全链路冒烟默认跳过。准备一次性 Redis 与上文 MinIO 测试桶后运行：

```sh
REDIS_TEST_URL=redis://127.0.0.1:6390 python -m unittest discover -s tests -p test_worker.py -v
E2E_SMOKE=1 REDIS_TEST_URL=redis://127.0.0.1:6390 python -m unittest discover -s tests -p test_e2e_smoke.py -v
```

运营报表与非 AI 接口本地 p95 采样（T18，详见 `OPERATIONS.md`）：

```sh
DATABASE_URL="$DATABASE_URL" python -m scripts.ops_report --days 7
python -m scripts.latency_sample --samples 200   # 退出码即 p95≤500ms 门禁
```

冒烟覆盖：登录→协议→建档→签名直传 MinIO→复核→提交分身（含幂等合并与占位清单）→占位片公开下载→动作映射→arq worker 生成→轮询到 succeeded 且 7/7 动作就绪→分身读取接口与签名播放地址下载→初筛（缺项定位、呕吐 >24h 派生红线 urgent＋就医卡＋模板即存零用量、normal 无卡、详情／历史回看、存证删除的引用保护）→建议异步链路（observe pending→fake LLM worker→ready＋ai_usage_logs 审计）→饮食快录（50g 干粮 190 kcal、零食不计热量）→日聚合与首页同源→删除重算→喂养参考无体重引导与尾注→体重录入（4.0→3.5 kg 骤变 loss −12.5% 提示初筛、档案/首页/喂养参考即时同步、超范围拦截）→饮食幂等回放（同键同记录、异 body 409）→聊天（线程复用、fake LLM 人设回复、幂等回放不再调 LLM、红线零 LLM 引导卡、倒序分页与用量审计）→录音解读（1 秒 WAV 直传复核、audio 202＋同音频合并 200、fake audio worker 解读 happy/0.82、情绪气泡与签名播放字节一致、audio/llm 用量审计、解读失败 unrecognized＋安抚且文字仍可用）→配额热调 429「明日再试」＋红线豁免＋plans/entitlement＋训练授权开关→GIF 导出（202＋同动作合并、真实占位片 ffmpeg 转码、签名下载 GIF89a 480p）→注销（202→幂等 200→登录冻结→到期 purge 物理清除：账号/猫咪/媒体消失、OSS 对象删除核验、审计日志匿名保留）。

MySQL 8.4 已验证最新迁移（含 body_type、初筛四表、ai_usage_logs、diet/weight、request_idempotency、聊天两表与 deletion_jobs/usage_counters/plans/entitlements 与 quota_denials，head 20261119_15）、任务并发去重、认领与失败重排；迁移回滚演练 head↔base 与 mysqldump 备份恢复（26 表逐表行数一致）已在 MySQL 8.4 执行（T18，详见 OPERATIONS.md）；观测 14 项单测覆盖脱敏／拒绝审计／worker 事件／报表聚合／p95 采样；隐私 16 项单测覆盖冻结／幂等注销／15 天清除模拟（含 OSS 删除与匿名统计）；配额 13 项单测覆盖原子计数／红线豁免／合并不计数／env 热调／429 文案；GIF 16 项单测覆盖就绪校验／合并／水印滤镜／480p≤5s 规格与签名下载；文案审计 9 项锁定 FRD 一字不差文案与移动端产品文案（T19）；worker 并发限 2（max_jobs，FRD 内测门槛）回归锁定；聊天 30 项单测覆盖上下文窗口／禁词／红线零 LLM／模板降级／幂等回放／分页与归属；音频 39 项单测覆盖时长校验／置信度阈值／未识别降级／人设解析／同音频合并／归属与 worker 解读链路；饮食公式 12 项单测覆盖 AC-07-2/4、月龄边界与 ±10% 区间，饮食 API 19 项单测覆盖本地日边界、删除重算、归属与 503；体重 23 项单测覆盖范围/精度/回改/同日保留/90 天窗口/骤变阈值与即时同步（AC-08-1/2）；MinIO 版本化桶已验证上传策略与版本固定；Redis/arq 已验证分发、租约回收与端到端冒烟（fake provider）；占位片库 21 条已按规格验收（h264/720p/无声/≤5s/首尾对齐）；初筛规则 22 项单测覆盖附录 A 分级表与附录 B 全部红线，视频存证经 ffprobe 双校验；建议链路（入队、禁词拦截、重试耗尽模板、60 秒读时降级、用量审计）经 fake LLM 单测与 e2e 验证。生产 OSS 适配、真实 DashScope 生成与建议质量、授权占位素材与 Figma 对照、真实 SMTP、正式协议、兽医评审、iOS/Android 真机及生产队列仍待验收。

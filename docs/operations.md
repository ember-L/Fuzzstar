# 绒星运维与质量 Runbook（T18）

本文档记录本地可执行的运维/质量设施、演练证据与生产待办。凡标注「待外部」的项目均未验证，不得当作已达成。

## 1. 环境变量清单

后端（`create_dev_app` 启动时读取；本机与 Docker Compose 共用 `backend/.env`）：

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | 必需。MySQL 8.4 的 SQLAlchemy URL（`mysql+pymysql://...?charset=utf8mb4`），运行时不支持 SQLite |
| `MYSQL_DATABASE`／`MYSQL_USER`／`MYSQL_PASSWORD`／`MYSQL_ROOT_PASSWORD` | 仅 Docker Compose：MySQL 容器初始化；容器内的 `DATABASE_URL` 由入口脚本用前三项生成 |
| `JWT_SECRET` | 必需，≥32 字节；HS256，access 30 分钟 |
| `PRIVACY_VERSION`／`TERMS_VERSION` | 必需，≤32 字符；协议版本 |
| `PRIVACY_URL`／`TERMS_URL` | 必需，HTTPS 链接 |
| `MEDIA_S3_ENDPOINT`／`MEDIA_S3_BUCKET`／`MEDIA_S3_ACCESS_KEY`／`MEDIA_S3_SECRET_KEY` | 四项同配；桶必须启用版本控制；http 仅限 127.0.0.1/localhost（开发） |
| `REDIS_URL` | worker 用，默认 `redis://127.0.0.1:6379`；Compose 覆盖为 `redis://redis:6379/0` |
| `DASHSCOPE_API_KEY` | 缺失时聊天走模板降级、worker 启动拒绝（分身/音频/建议需真实凭证验收） |
| `RULES_DIR` | 规则目录，默认 `backend/rules`（action-map/feeding/chat/redlines/symptoms/triage） |
| `PLACEHOLDER_DIR` | 占位片库，默认 `backend/assets/placeholders` |
| `QUOTA_SCREENING`／`QUOTA_AVATAR`／`QUOTA_CHAT` | 每日配额热调（>0），默认 10/3/50；UTC 自然日 |
| `GIF_WATERMARK_FONT` | GIF 水印字体路径；缺省自动探测 PingFang/Noto CJK |

测试专用（勿用于业务库）：`MEDIA_S3_SMOKE=1`、`REDIS_TEST_URL`、`E2E_SMOKE=1`、`TASK_TEST_DATABASE_URL`。
移动端：`EXPO_PUBLIC_API_URL`（发布版只接受 HTTPS）。

## 2. 结构化日志与脱敏政策

- 三个 JSON 行日志器：`rongxing.access`（每请求）、`rongxing.worker`（任务事件）、`rongxing.quota`（配额拒绝）。
- access 字段：`request_id`（复用合法 `X-Request-ID`，`^[A-Za-z0-9_-]{1,64}$`，否则 uuid4 hex，并回写响应头）、`method`、`path`（仅 URL path，**不含 query**）、`status`、`duration_ms`、`user_id`（JWT sub 尽力提取，不验签）。
- worker 事件：`claimed`／`finished`／`failed`，带 `task_id`、`task_type`、`attempts`、`status`。
- **绝不记录**：请求体、响应体、headers、邮箱、密码、令牌、手机号明文。单测 `backend/tests/test_observability.py` 以敏感值注入验证不落日志。
- 配额拒绝审计：`quota_denials` 表（migration 15，user_id/metric/day），业务回滚不抹拒绝记录（独立会话在请求收尾落库）；worker sweep 清理 90 天前记录。
- 注销清除时 `ai_usage_logs` 匿名化（user_id/task_id 置 NULL），仅保留聚合统计。
- 生产日志采集（Sentry/ELK 等）与告警接线**待外部**。

## 3. 统计与成本看板

```sh
cd backend
DATABASE_URL=... python -m scripts.ops_report --days 7        # 文本报表
DATABASE_URL=... python -m scripts.ops_report --days 7 --json # 机器可读
```

只读聚合：AI 调用（kind/model 的 calls/tokens_in/out/media_seconds/cost_est）、每日 AI 成本、单用户成本 Top10（NULL=已注销匿名桶）、任务健康（total/succeeded/failed/in_flight/retried/平均与 p95 时长=终态 updated_at−created_at）、配额拒绝按日、今日配额用量。单测 `backend/tests/test_ops_report.py`。

## 4. 性能采样（本地门禁）

```sh
cd backend
python -m scripts.latency_sample --samples 200        # 退出码即门禁
python -m scripts.latency_sample --samples 200 --json
```

- 方法：临时 SQLite＋种子账号/猫/饮食/体重/任务，TestClient 走完整中间件栈，perf_counter 计时；8 个非 AI GET 端点（health/pets/pet_health/quota/diet_day/weights/action_map/task）。
- 门禁：总体 p95 ≤500ms（FRD 非功能）。**这是进程内本地回归护栏，不是生产/真机性能结论。**
- 证据（2026-11-20，每端点 200 次，n=1600）：总体 p50 1.54ms／p95 2.34ms／max 22.11ms，门禁通过。各端点 p95：health 0.78／pets 2.22／pet_health 2.86／quota 1.72／diet_day 2.64／weights 2.40／action_map 1.96／task 2.03（ms）。
- **待外部**：生产 p95、首页冷启动 ≤3s、缓存分身首帧 ≤1s、crash-free ≥99%（需真机＋Sentry DSN＋测量样本/设备/环境记录）；100 宠并发压测（worker 并发限 2）。

## 5. 迁移与回滚 Runbook

```sh
cd backend
DATABASE_URL=... alembic upgrade head      # 当前 head 20261119_15
DATABASE_URL=... alembic current
DATABASE_URL=... alembic downgrade -1      # 有损：drop 表即丢数据
```

- **回滚优先备份恢复**（第 6 节）；`downgrade` 仅用于演练或确认无数据损失的场景。
- 演练证据（2026-11-20，MySQL 8.4.7 一次性容器）：head 15 → downgrade 14（quota_denials 消失）→ head → **downgrade base（仅剩 alembic_version）** → head（26 表完整重建），全程 exit 0。
- 演练发现并修复的真实缺陷：10 个迁移的 downgrade 显式 `DROP INDEX` 在 MySQL 触发 1553（索引被外键征用，如 `ix_chat_messages_session_time` 是 session_id 唯一索引）。修复：删除冗余 `drop_index`，`DROP TABLE` 自带索引/外键清理（SQLite 同样适用）。
- 应用代码回滚：git revert 对应提交后 `alembic upgrade head` 保持 schema 与代码匹配；跨 migration 回滚先评估数据损失。

## 6. 备份与恢复 Runbook

```sh
# 备份（一致性快照）
mysqldump -h HOST -u USER -p --single-transaction --routines --triggers DB > backup.sql
# 恢复到新库验证
mysql -h HOST -u USER -p -e "CREATE DATABASE DB_restore CHARACTER SET utf8mb4;"
mysql -h HOST -u USER -p DB_restore < backup.sql
# 逐表精确行数比对（information_schema.table_rows 是估算，必须 COUNT(*)）
```

- 演练证据（2026-11-20）：rongxing_test（含 test_tasks 数据 users 7/pets 7/tasks 8）→ dump 30,001 字节 → 恢复 rongxing_restore → **26 表逐表 COUNT(*) 完全一致**。
- 对象存储：桶版本化，媒体行固定 VersionId；恢复数据库后对象仍可按版本读取。生产 OSS 的桶级备份/跨区域复制**待外部**；注销 purge 按版本删除对象（e2e 已核验 head_object 404）。
- 备份频率/保留策略与恢复 RTO/RPO 目标**待生产决策**。

## 7. 告警阈值建议（待生产接线）

| 信号 | 建议阈值 | 数据来源 |
| --- | --- | --- |
| 任务失败率 | failed/(succeeded+failed) >5%（15 分钟窗） | tasks 表／worker 日志 |
| 任务积压 | pending 且 lease 过期 >10 条 | sweep 日志 |
| 非 AI p95 | >500ms（5 分钟窗） | access 日志 duration_ms |
| 存储不可用 | 503 MEDIA_UNAVAILABLE >1%（5 分钟窗） | access 日志 |
| LLM 降级率 | source=template 占比 >20%（1 小时窗） | chat 响应／ai_usage_logs |
| 配额拒绝激增 | 单用户日拒绝 >3×limit | quota_denials |
| 注销清除失败 | deletion_jobs 过期未 purged >24h | worker 日志 |

## 8. 回归覆盖矩阵（2026-11-20 全量证据）

| 层 | 命令 | 结果 |
| --- | --- | --- |
| 后端单测+集成 | `python -m unittest discover -s tests` | **417 OK**（skipped=3 opt-in） |
| 文案审计（T19） | `python -m unittest discover -s tests -p test_copy_audit.py` | **9 OK**：FRD 一字不差文案＋移动端产品文案回归锁 |
| worker 并发上限（FRD 内测门槛） | test_worker.WorkerSettingsTests | max_jobs=2（product/FRD.md:357，100 宠并发不雪崩） |
| 照片存储真实 S3 | `MEDIA_S3_SMOKE=1 ... test_media_storage.py` | 1 OK（MinIO 版本化桶） |
| worker Redis 集成 | `REDIS_TEST_URL=... test_worker.py` | 12 OK |
| 全链路冒烟 T05–T17 | `E2E_SMOKE=1 ... test_e2e_smoke.py` | 1 OK（含配额/隐私/GIF/注销清除段） |
| MySQL 任务并发 | `TASK_TEST_DATABASE_URL=... test_tasks.py` | 7 OK（MySQL 8.4.7） |
| 迁移回滚演练 | 第 5 节 | head↔base 全程通过 |
| 备份恢复演练 | 第 6 节 | 26 表行数一致 |
| 本地 p95 采样 | 第 4 节 | 门禁通过 |
| 移动端单测 | `node --test tests/*.test.mjs` | **155/155** |
| 移动端类型/规范 | `npm run typecheck && npm run lint` | 干净 |
| 网页导出 | `npx expo export --platform web` | EXIT=0（T17 证据） |

域覆盖：认证/会话轮换（test_auth_api、test_sessions）、所有权隔离 404（各 API 测试 other_headers 段）、协议版本（test_consents）、媒体校验（照片/视频/音频 ffprobe）、任务幂等/租约/重试（test_tasks、test_worker）、分身管线（test_avatar_*、test_worker）、初筛规则附录 A/B 全红线（test_triage 22）、建议降级（test_advice）、健康分衰减（test_health）、饮食/体重（test_diet_api、test_weights、test_feeding）、聊天上下文/禁词/红线/幂等（test_chat 27）、音频解读（test_audio* 39）、配额/隐私/GIF（test_quota 13、test_privacy 16、test_gif 16）、观测（test_observability 8、test_ops_report 5、test_latency_sample 1）。
弱网/离线：retry-queue/chat-cache/offline-sync 单测（mobile）；权限拒绝：录音/通知/相册路径单测与页面降级；无障碍：语义标签与状态色附文字（组件 accessibilityState/label）。
**待外部**：真实设备上的本地通知触发、媒体播放观感、后台轮询、双端交互走查；生产 HTTPS 证书与全链路 TLS。

## 9. 安全基线状态

- argon2id 密码哈希 ✓；JWT 30min＋刷新轮换＋重放吊销 ✓；跨用户资源一律 404 ✓（单测覆盖）。
- 认证 POST 按来源 IP 30 次/分钟（DB 固定分钟窗）——分布式防滥用**待生产**。
- CORS 仅 localhost/127.0.0.1 开发源；生产域名白名单与全链路 HTTPS **待部署**。
- 日志脱敏 ✓（第 2 节，单测验证）；训练授权默认关闭 ✓；注销 15 天物理清除 ✓（e2e 核验）。
- 依赖漏洞扫描与渗透测试**待外部**。

## 10. 外部待办汇总（不虚构）

真机性能指标与 crash-free（Sentry DSN）、生产 HTTPS/证书、100 宠并发压测、生产 OSS 备份策略、真实 SMTP、DASHSCOPE_API_KEY 真实生成/建议/音频质量、兽医评审（T19）、Figma 节点对照与授权素材（T19）、TestFlight/APK 签名与内测（T20）。

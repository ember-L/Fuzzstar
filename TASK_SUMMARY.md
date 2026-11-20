# 绒星 · 任务总结（T01–T20 本地交付）

> 本文是项目执行总结（README 形式）。运行手册见 [README.md](README.md)，运维与演练见 [OPERATIONS.md](OPERATIONS.md)，
> 设计评审见 [DESIGN_REVIEW.md](DESIGN_REVIEW.md)，发布与内测见 [RELEASE.md](RELEASE.md)。
> 最后更新：2026-11-20（T19/T20 收尾，提交 `a5db0b7`）。

## 1. 项目概述

绒星（RongXing）是一款猫健康管理 App：**FastAPI 后端 + Expo React Native 移动端**（mobile 为嵌套独立 Git 仓库）。
核心闭环：邮箱账号 → 猫咪档案 → 照片生成分身（7 动作虚拟猫）→ 健康初筛（规则分级＋红线就医）→ AI 护理建议 →
饮食/体重记录与喂养参考 → 文字聊天与录音情绪解读 → 时间线与提醒 → 配额、隐私注销与 GIF 分享。

- 后端：Python 3.11（`backend/.venv311`）、SQLAlchemy 2 + Alembic（MySQL 8.4 已验证，head `20261119_15`）、
  arq worker（Redis）、S3 兼容对象存储（MinIO 本地验收）、DashScope Provider（真实凭证待接入，fake 全链路已验证）。
- 移动端：Expo SDK 58 / RN 0.88 / expo-router；纯逻辑 lib 全部 Node 可测（155 项测试）；web 导出可用。
- 规则全部版本化于 `backend/rules/*.yaml`（红线/分级/建议/喂养/聊天/动作映射），热更新无需发版。

## 2. 任务完成总览

| 任务 | 主题 | 状态 | 外层提交 | mobile 提交 |
| --- | --- | --- | --- | --- |
| T01–T04 | 底座：环境/存储/账号协议/猫咪档案 | ✅ 完成（基线） | `3104bfe` | `4f48ece` |
| T05 | 任务底座、照片直传、arq worker、移动轮询 | ✅ 完成 | `9974408` | `05f8374` |
| T06 | 占位片库、动作映射、体型、分身读取 | ✅ 完成 | `6cee8a3` `a371cba` `0eb287d` | `ccae596` |
| T07 | 分身播放器与资产缓存（LRU 200MB） | ✅ 完成 | `1bae068` | `728ba11` |
| T08 | 首页健康聚合与健康分 | ✅ 完成 | `23ef153` | `dfe70b5` |
| T09 | 健康初筛问卷、规则分级、视频存证 | ✅ 完成 | `797efe8` | `f89c9c0` |
| T10 | AI 护理建议与降级模板 | ✅ 完成 | `a241bea` | `05437cf` |
| T11 | 时间线与 24h 复查提醒 | ✅ 完成 | `fdf1dd8` | `d7c2f23` |
| T12 | 饮食记录、日聚合、喂养参考 | ✅ 完成 | `b2a48bc` | — |
| T13 | 体重、90 天趋势、骤变提示 | ✅ 完成 | `1b81cfb` | `d97b9a9` |
| T14 | 喂养提醒与浅离线（幂等补发） | ✅ 完成 | `4cd4447` | `b615546` |
| T15 | 文字聊天与安全边界（红线零 LLM） | ✅ 完成 | `db9d967` | `fed86da` |
| T16 | 录音解读与会话反馈 | ✅ 完成 | `30e609f` | `0f606fa` |
| T17 | 配额、隐私注销、GIF 分享 | ✅ 完成 | `616cd6a` | `fa274f2` |
| T18 | 观测、质量与安全（日志/审计/演练） | ✅ 完成 | `c8823d7` | — |
| T19 | 设计与专业评审 | 📋 本地交付完成，评审执行待外部 | `a5db0b7` | — |
| T20 | 内测发布与指标 | 📋 本地交付完成，发布执行待外部 | `a5db0b7` | — |

## 3. 本轮任务详情（T17–T20）

### T17 · 配额、隐私与分享
- **配额（F11）**：`usage_counters` 按服务器 UTC 自然日原子计数，默认初筛 10／分身 3／聊天 50；
  `QUOTA_SCREENING/QUOTA_AVATAR/QUOTA_CHAT` 热调；超限 429 `QUOTA_EXCEEDED`「明日再试」；
  红线初筛豁免、分身仅新建计数（合并不计）、聊天仅文字计数（录音不占）；`GET /quota`＋移动端入口置灰。
- **隐私（F12）**：训练授权默认关闭（`POST /consents/training` 单独开关）；`DELETE /me` 202 `{purge_after}`（15 天）
  立即冻结账号（登录/刷新/访问全拒），重复申请 200 原期限；worker sweep 到期物理清除：先删 OSS 对象版本
  （照片/分身/GIF）再按外键级联删业务表，`ai_usage_logs` 匿名化保留聚合统计；存储不可用下轮重试。
- **会员（F11-4）**：`GET /plans` free/pro 代码目录（无价格）、`GET /me/entitlement` 默认 free＋「测试期免费」，不接支付。
- **GIF 分享（F13）**：`POST /pets/{id}/share/gif` 要求最近成功分身对应动作 ready（否则 409），同动作合并 200；
  ffmpeg 480p／≤5s／12fps＋水印「绒星 · AI 参考」；`GET /tasks` succeeded 追加 60 分钟签名 `download_url`；
  移动端 60s 超时，native expo-sharing 系统面板、web 降级下载。

### T18 · 观测、质量与安全
- **结构化日志**（`backend/app/observability.py`）：access/worker/quota 三通道 JSON 日志，
  request_id（可复用 X-Request-ID）/user_id/task_id/duration_ms；**绝不落** query/body/邮箱/密码/令牌。
- **配额拒绝审计**：`quota_denials` 表（migration 15，90 天清理）；拒绝记录经 `get_db` finally 延迟落库，
  业务回滚不抹审计（规避 SQLite 单写者死锁）。
- **运营报表** `python -m scripts.ops_report --days 7 [--json]`：AI 调用/成本、单用户日成本 Top10、
  任务成功率/重试/p95 时长、配额拒绝与今日用量（只读、无个人标识）。
- **性能门禁** `python -m scripts.latency_sample --samples 200`：8 个非 AI GET 端点进程内采样，
  本地 n=1600 总体 p95 **2.34ms**（门禁 500ms）；生产指标仍需真机/压测证据。
- **演练**（MySQL 8.4 一次性容器）：迁移 head↔base 全链回滚演练（修复 10 个迁移 downgrade 的 1553 索引缺陷）；
  mysqldump 备份→恢复新库→26 表行数逐一一致。runbook 与告警阈值建议见 OPERATIONS.md。

### T19 · 设计与专业评审（本地交付）
- [DESIGN_REVIEW.md](DESIGN_REVIEW.md)：13 条 P0 流程矩阵（界面/成功态/失败态/测试证据）、专业评审议程
  （兽医：红线/分级/就医/喂养/音频娱乐定位；隐私：正式协议待法务；设计：双端对照/对比度/读屏）、
  素材版权台账（程序化占位 v1 为临时素材，授权后整库版本化替换）、Figma 节点台账模板。
- **文案审计回归测试**（`backend/tests/test_copy_audit.py`，9 项）：FRD「一字不差」标准文案
  （免责/红线卡/就医清单/喂养尾注/音频尾注/水印）与 6 个移动端产品文案常量全部锁定，漂移即测试失败。

### T20 · 内测发布与指标（本地交付）
- [RELEASE.md](RELEASE.md)：TestFlight/APK 签名分发 runbook、测试账户方案、版本回滚（优先备份恢复）、
  问题收集分级、用户数据处理、内部验证 gate（先内部后 50–100 内测）。
- **指标定义 5 项**（事件/分母/去重/权限/责任人/数据源）：周活跃记录宠物数、7 日留存、初筛完成率、
  红线就医点击率、聊天使用；前两项服务端可算，后两项分母/点击需客户端埋点（SDK 选型待决策）。
- **门槛缺口修复**：worker 并发限 2（`max_jobs=2`，FRD:357「100 宠并发不雪崩」，TDD 锁定）。
- 留存≥30%、初筛完成率≥70% 是**内测观察目标**，不预先宣称达成。

## 4. 验证证据（最终，全部 exit 0）

| 项 | 结果 |
| --- | --- |
| backend 全量单测 | **417 OK**（skipped=3，均为 opt-in） |
| MinIO 真实存储冒烟 | 1 OK（presign→超限拒→上传→版本固定→重传不替换→下载一致） |
| Redis/arq worker 集成 | 13 OK（分发/租约/重试/并发上限配置） |
| 全链路 e2e 冒烟 | 1 OK（注册→分身→初筛→建议→饮食→体重→聊天→录音→配额→GIF→注销清除） |
| MySQL 8.4 | head `20261119_15`；任务并发测试 7 OK；回滚/备份恢复演练通过 |
| 非 AI 接口 p95 | 本地 n=1600，总体 p95 2.34ms ≤ 500ms 门禁 |
| mobile | **155/155** 测试；typecheck/lint 干净；web export 成功 |

## 5. 快速开始

```sh
# 后端（backend 目录，Python 3.11 虚拟环境）
.venv311/bin/python -m unittest discover -s tests          # 全量单测
DATABASE_URL=... JWT_SECRET=... .venv311/bin/python -m uvicorn app.main:create_dev_app --factory
.venv311/bin/python -m arq app.worker.WorkerSettings        # worker（需 REDIS_URL/DASHSCOPE_API_KEY/MEDIA_S3_*）

# 移动端（mobile 目录）
npm install && EXPO_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1 npm run web

# 运维
DATABASE_URL=... .venv311/bin/python -m scripts.ops_report --days 7
.venv311/bin/python -m scripts.latency_sample --samples 200
```

完整环境变量、一次性容器重建命令与 opt-in 验证步骤见 README.md「验证命令」与 OPERATIONS.md。

## 6. 文档索引

| 文档 | 内容 |
| --- | --- |
| [README.md](README.md) | 运行手册：环境/各功能节/API 表/验证命令/状态 |
| [OPERATIONS.md](OPERATIONS.md) | 运维：env 清单/日志脱敏/报表/采样/回滚与备份 runbook/告警阈值/回归矩阵 |
| [DESIGN_REVIEW.md](DESIGN_REVIEW.md) | T19：P0 流程矩阵/文案审计/专业评审议程/素材版权/无障碍 |
| [RELEASE.md](RELEASE.md) | T20：签名分发/测试账户/回滚/问题收集/指标定义/内测门槛证据 |
| PRD.md / FRD.md / ARCHITECTURE.md | 需求与架构契约（验收标准来源） |
| docs/superpowers/plans/2026-11-17-rongxing-full-stack.md | 执行计划 T01–T20（勾选状态；docs/ 不入库） |
| .superpowers/sdd/.../progress.md | 执行 ledger：全部 Rulings/Progress/教训（不入库） |

## 7. 仍待外部（不虚构完成）

- **评审执行**：兽医专业评审与签署、隐私正式协议法务评审、Figma 节点对照与双端视觉/对比度/读屏走查（T19）。
- **真机验收**：分身播放观感、通知准时性（±5 分钟/连续 3 天）、录音权限与音质、GIF 系统分享面板、
  冷启动≤3s、缓存首帧≤1s、crash-free≥99%（需 Sentry DSN）。
- **凭证与生产**：DASHSCOPE_API_KEY 真实生成/建议/解读质量、生产 OSS、真实 SMTP、100 宠并发压测。
- **发布执行**：TestFlight/APK 签名分发、埋点 SDK 选型、50–100 名猫主内测与指标观察（T20）。
- **素材**：授权占位素材整库替换（现 v1 为程序化临时素材）、Figma hero 图授权确认。

# T20 · 内测发布与指标 —— Runbook 与定义（本地交付）

状态（2026-11-20）：**本地可执行部分已完成**——发布 runbook、测试账户方案、回滚/问题收集/数据处理流程、指标定义、FRD 内测门槛证据映射。
**外部待办（不虚构完成）**：Apple/Google 签名凭证与 EAS 项目、TestFlight/APK 实际分发、埋点 SDK 上线与看板、50–100 名猫主内测执行。留存≥30%、初筛完成率≥70% 是**内测观察目标**，不是上线前可预先宣称达到的结果（plan:235）。

## 1. 发布前置条件（阻断项）

| 条件 | 状态 |
| --- | --- |
| T01–T18 P0 本地验证 | ✅ backend 417 项单测（含文案审计 9）＋opt-in 冒烟＋MySQL 迁移/回滚/备份演练＋mobile 155 项＋web export（OPERATIONS.md §8 覆盖矩阵） |
| T19 专业评审执行（兽医/隐私/设计） | ⛔ 外部（DESIGN_REVIEW.md §6） |
| 真机 P0 走查（播放/通知/录音/分享/冷启动） | ⛔ 外部设备 |
| 正式隐私政策/用户协议 | ⛔ 法务评审（当前占位 HTTPS 链接） |
| 生产凭证：DASHSCOPE_API_KEY、生产 OSS（版本化桶）、SMTP、Sentry DSN | ⛔ 外部 |
| 生产 HTTPS 域名与证书（发布版 API 只接受 HTTPS） | ⛔ 外部 |
| P1 是否进内测的产品决策（plan:249） | ⛔ 待决策；红线/安全 P0 不可省略 |

## 2. 构建 / 签名 / 分发 runbook（执行待凭证）

### iOS（TestFlight）
1. Apple Developer 账号＋App ID（bundle id 与 mobile/app.json 一致）；EAS 项目初始化（eas init）。
2. eas build --platform ios --profile preview（或 release）；签名证书由 EAS 托管或手动上传。
3. 出口合规：仅使用 HTTPS（标准加密豁免声明）；隐私清单按 Apple 要求申报（相机/麦克风/通知用途文案已在 app.json 权限描述）。
4. eas submit --platform ios → App Store Connect → TestFlight 内部组（≤100 人，无需 Beta 审核）；外部测试组需 Beta App Review。
5. 内测包 EXPO_PUBLIC_API_URL 指向生产 HTTPS API；构建号递增（app.json ios.buildNumber）。

### Android（APK 签名分发）
1. 生成上传 keystore（keytool -genkeypair -keyalg RSA -keysize 2048 -validity 10000）；**keystore 与口令离线保管，不入库**；EAS credentials 托管。
2. eas build --platform android --profile preview（buildType=apk）；versionCode 递增。
3. 分发：内部下载页/蒲公英/fir 或 Play 内部测试轨道；记录每个分发包的 versionCode＋SHA256。
4. 权限：录音（RECORD_AUDIO）、通知（POST_NOTIFICATIONS，Android 13+ 运行时请求）已声明。

### 版本纪律
- 每次分发记录：版本号/构建号、git commit（外层＋mobile 双仓库）、API 兼容迁移 head、规则版本（action-map/chat/triage/feeding/advice）。
- 规则与占位素材版本化可热更（无需发版）；客户端协议不兼容变更必须升 major 并保留旧 API 一个内测周期。

## 3. 测试账户与数据

- 专用测试邮箱域（如 beta@<test-domain>），不复用真实用户邮箱；注册→验证→同意→建档走真实链路（验证邮件经 DB 投递队列，测试环境可直读 verification_mail）。
- 种子脚本建议：backend/scripts 增加 seed_beta.py（待办）——批量建测试账号＋猫＋饮食/体重/初筛样本，便于看板与走查。
- 配额测试：QUOTA_SCREENING/QUOTA_AVATAR/QUOTA_CHAT 环境变量热调（OPERATIONS.md §1）；红线豁免用例必测。
- 内测数据与生产隔离：独立数据库＋独立版本化 OSS 桶；内测结束按注销流程清除或归档（§6）。

## 4. 版本回滚

- **移动端**：TestFlight 可指回旧 build；Android 重新分发上一签名包（versionCode 不回退，用更高 code 的旧内容包或引导重装）。回滚决策人：产品＋移动端负责人。
- **后端**：优先备份恢复（OPERATIONS.md §6，已演练 26 表行数一致）；alembic downgrade 有损（删表/列），仅在无数据损失风险时按 §5 runbook 执行；**先停 worker 再回滚 API**，避免新任务写入旧 schema。
- **规则/素材**：版本化目录回退即回滚（RULES_DIR/PLACEHOLDER_DIR 指回旧版本），客户端按版本比对自动失效缓存。
- 回滚后必跑：backend 全量＋opt-in 冒烟＋mobile 测试（OPERATIONS.md §8）。

## 5. 问题收集

- 应用内反馈入口：**待办**（内测版加 mailto 或表单，附版本号/设备/请求 ID）。
- Crash：Sentry（DSN 待配置；crash-free≥99% 为内测观察护栏）。
- 服务端关联：结构化日志 request_id（X-Request-ID 可回传）＋user_id/task_id（OPERATIONS.md §2）；问题模板要求附 request_id 与复现步骤。
- 分级：阻断（红线失效/数据丢失/崩溃循环）→ 立即停分发＋回滚；高（P0 功能不可用）→ 24h 内修复；中低 → 内测周期内排期。所有阻断问题关闭是内测放量前提（plan:235）。

## 6. 用户数据处理

- 隐私政策正式版须先过法务（DESIGN_REVIEW.md §3.2）；内测知情同意书说明：AI 参考非诊断、录音娱乐定位、数据清除方式。
- 训练授权默认关闭、单独开关（POST /consents/training）；v1 不读取任何训练数据。
- 注销：DELETE /me 冻结→15 天物理清除（DB＋OSS 版本，审计匿名化）；内测账户同样适用。
- 第三方分析/崩溃 SDK 引入前须更新隐私政策与数据处理清单；日志不落明文邮箱/手机号/令牌（已审计）。

## 7. 内部验证 gate（向 50–100 内测放量前）

1. backend 全量＋opt-in（media/worker/e2e）＋MySQL 迁移/备份演练全过。
2. mobile typecheck/lint/测试/web export 全过；真机 P0 走查清单（DESIGN_REVIEW.md §1 矩阵逐行）。
3. T19 评审关闭（兽医/隐私/设计签署），高风险修复复验。
4. 安全演练：AI 全挂降级（初筛模板/聊天安抚/分身占位）真机复核无白屏无死锁。
5. 阻断问题清零；回滚演练（§4）在 staging 执行一次。

## 8. 指标定义（plan:234；埋点 SDK 待决策，服务端可算项已标注）

| 指标 | 事件定义 | 分母 | 去重 | 权限 | 责任人 | 数据源/状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 周活跃记录宠物数（北极星） | 自然周内≥1 次记录事件：饮食/体重/初筛提交/聊天发送 | 全部活跃猫（status=active） | pet_id×周 | 登录+协议同意 | 产品 | 服务端可算：diet_records/weight_records/health_screenings/chat_messages（按 pet 关联）；**客户端事件埋点待 SDK** |
| 7 日留存 | 第 N 周新验证用户中，第 N+1 周≥1 次活跃事件（同上四类） | 第 N 周首次 verify_email 成功用户 | user_id×周 | 同上 | 产品 | 服务端可算：user_credentials.verified_at＋记录表；观察目标≥30%（不可预宣称） |
| 初筛完成率 | 提交成功（POST /screenings 201） | 问卷开始事件（首屏曝光） | session×次 | 同上 | 产品+测试 | 分子服务端可算；**分母需客户端 start 埋点（待 SDK）**；观察目标≥70% |
| 红线就医提示点击率 | 就医入口点击事件 | 红线卡曝光事件 | user×screening | 同上 | 产品 | **双端均需客户端埋点（待 SDK）**；服务端代理指标：urgent 初筛数（redline_card 返回次数） |
| 聊天使用 | 发送（text/audio 分开）、回复到达、情绪动作播放 | 日活用户 | user×日×类型 | 同上 | 产品 | 发送服务端可算（chat_messages.kind）；到达/播放需客户端埋点 |

看板：服务端成本/任务/配额拒绝日用量已可日跑（python -m scripts.ops_report --days 7，OPERATIONS.md §3）；完整指标看板待埋点 SDK 选型（plan:251 待决策）后搭建，**内测门槛「埋点上线＋看板可日跑」当前未满足**。

## 9. FRD 内测门槛证据映射（FRD.md:354-358）

| 门槛 | 要求 | 当前证据 | 缺口 |
| --- | --- | --- | --- |
| 用例覆盖 | F01–F13 P0 AC 逐条通过；红线用例 100% 且零 LLM | backend 417 项（test_triage 附录 B 6 项+派生、test_chat 红线零 LLM 断言）＋mobile 155 项＋e2e 全链路；AC 映射见 OPERATIONS.md §8 与 DESIGN_REVIEW.md §1 | 真机 AC 走查（通知准时/播放观感/分享面板） |
| 安全演练 | AI 全挂：初筛/聊天/分身降级，无白屏无死锁 | test_advice（重试耗尽模板）、test_chat（LLM 失败安抚）、player-machine（逐级回退）；e2e 音频失败段文字仍可用 | 真机复核 |
| 合规审查 | 免责四处全覆盖；注销 15 天清除演练；训练默认关 | test_copy_audit 9 项（四处+清单+尾注）；e2e 注销段（冻结→purge→OSS 删除核验→审计匿名）；test_privacy 训练默认关 | 正式隐私文案法务评审 |
| 性能 | 非 AI p95 达标；100 宠并发不雪崩（worker 并发限 2） | latency_sample 本地 n=1600 总体 p95 2.34ms（门禁 500ms，OPERATIONS.md §4）；WorkerSettings.max_jobs=2（test_worker 回归锁定） | 生产/真机 p95、100 宠并发压测 |
| 指标 | 北极星与护栏埋点上线，看板可日跑 | ops_report 服务端日用量/成本/任务可日跑；指标定义完成（§8） | 客户端埋点 SDK＋完整看板（待决策） |

## 10. 外部待办与待决策（plan:251）

- 待决策：项目开始日期/人员容量；导航方案与 Expo 原生模块兼容复核；云供应商/预算；测试账户域；隐私文案与兽医审核责任人；Figma 同步；埋点 SDK 选型。
- 待执行：签名凭证与 EAS 项目、TestFlight/APK 分发、50–100 内测招募与知情同意、内测观察（留存/完成率/点击率/crash-free）、阻断问题闭环。

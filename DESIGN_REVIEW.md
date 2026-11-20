# T19 · 设计与专业评审 —— 本地交付与评审议程

状态（2026-11-20）：**本地可执行部分已完成**——P0 流程矩阵、固定文案审计（回归测试锁定）、专业评审议程、素材版权台账、无障碍接线盘点。
**Figma 对照（2026-11-20 更新）**：四 Tab（首页/健康/聊聊/我的）+健康初筛入口已按 figwright 结构化 design context 逐节点对照重建（§7 台账与偏差清单）；对照基于坐标/颜色/字体/文案结构化数据，**非截图目测**（执行模型无图像输入）。
**外部待办（不虚构完成）**：双端真机视觉对照、兽医/隐私/设计专业评审的执行与签署、对比度与读屏真机抽查、其余子页面（饮食/体重/时间线/提醒/结果页）的 Figma 对照（设计稿未含）。责任人待 plan「尚需决策」确认（docs/superpowers/plans/2026-11-17-rongxing-full-stack.md:251）。

## 1. P0 流程设计 / 文案 / 状态验收矩阵

每行：需求 → 移动端界面 → 成功/失败状态 → 本地测试证据 → 设计对照状态。
「设计对照」：四 Tab+初筛入口已完成结构化对照（§7 台账，figwright 读取 Figma 文件 sGhmzVC6reNoJdpy73X1zI）；设计稿未覆盖的子页面沿用现有实现。测试证据为 backend/tests 与 mobile/tests 中可重跑文件。

| 需求 | 界面（mobile/src/app/） | 成功态 | 失败/边界态 | 本地测试证据 |
| --- | --- | --- | --- | --- |
| F01 账号 | (tabs)/profile.tsx 登录卡 | 登录/刷新轮换/退出 | 未验证 401 EMAIL_UNVERIFIED、错密 401、限频 429、注销冻结后登录/刷新拒绝 | test_auth_api.py、test_privacy.py；mobile tests/session.test.mjs |
| F02 档案 | (tabs)/profile.tsx 档案管理 | CRUD、body_type、latest_weight 同源 | 上限 5 只 409 PET_LIMIT_REACHED、字段 400 定位、软删 | test_pet_api.py、test_avatar_assets.py（体型） |
| F03 分身 | (tabs)/index.tsx + components/PhotoUpload.tsx、AvatarStage.tsx、avatar/AvatarPlayer.tsx | 上传→提交 202→占位首帧（≤5s 本地）→个人片循环边界淡入替换 | 未验证 409、超时 10min 兜底+重试、<5/7 动作提示、播放损坏逐级回退不白屏 | test_avatar_api.py、test_avatar_read.py、test_avatar_assets.py；mobile tests/avatar.test.mjs、task-poller.test.mjs、player-machine.test.mjs、asset-cache.test.mjs |
| F04 首页健康分 | (tabs)/index.tsx 健康卡 | 状态档+分数+扣分明细（衰减/规则版本） | 未评估「未评估 --」、urgent 红卡+常驻就医入口 | test_health_api.py、test_health.py；mobile tests/health.test.mjs |
| F05 初筛 | screening/[petId].tsx、screening/result/[screeningId].tsx | 规则硬判定 201+分级+免责；advice 异步 ready | 缺项 400 定位、红线 urgent 零 LLM+就医卡、advice 60s 超时/失败模板「AI 建议暂不可用」 | test_triage.py、test_screening_api.py、test_advice.py；mobile tests/screening.test.mjs |
| F06 历史与复查 | timeline/[petId].tsx、screening/history/[petId].tsx | 按日倒序混排（初筛/饮食/体重）、observe +24h 复查提醒 | 提醒权限拒绝→应用内横幅、复查/删猫自动取消 | test_timeline_api.py；mobile tests/timeline.test.mjs、recheck-reminder.test.mjs |
| F07 饮食 | diet/[petId].tsx、feeding/[petId].tsx | 快录≤3 步、日聚合、删除重算、RER/DER±10% | 克数/时间 400 定位、断网「待同步」联网≤10s 幂等补发、无体重引导 | test_diet_api.py、test_feeding.py、test_idempotency.py；mobile tests/diet.test.mjs、retry-queue.test.mjs |
| F08 体重 | weight/[petId].tsx + components/TrendChart.tsx | 录入即时同步档案/首页/喂养参考、90 天趋势 | 超范围/精度 400、±10% 骤变红卡跳初筛、空态引导 | test_weights.py；mobile tests/weight.test.mjs |
| F09 聊天+音频 | (tabs)/chat.tsx | 每猫线程、人设回复≤100 字、情绪联动分身播一次、录音解读情绪+置信度 | 红线零 LLM 就医卡、禁词/LLM 失败模板安抚、<0.4「不太确定」、失败「未识别」不阻塞文字、权限拒绝/网页不支持录音提示、离线补发 | test_chat.py、test_audio.py、test_audio_api.py、test_audio_worker.py；mobile tests/chat.test.mjs、chat-emotion.test.mjs、audio-message.test.mjs、chat-cache.test.mjs |
| F10 提醒 | reminders/[petId].tsx | 每猫多时段 DAILY 通知（默认关、上限 6） | 权限拒绝提示+重新授权、关闭/删猫取消、网页不支持 | mobile tests/feeding-reminder.test.mjs、notifications 适配层；**连续 3 天准时触发待真机** |
| F11 配额/会员 | profile/health/chat/index 用量与入口 | used/limit 展示、entitlement「测试期免费」 | 429「明日再试」+入口置灰（accessibilityState）、红线豁免、录音不占聊天配额 | test_quota.py、test_observability.py（拒绝审计）；mobile tests/quota.test.mjs |
| F12 隐私 | (tabs)/profile.tsx 授权/注销卡 | 协议版本同意、训练授权单独开关（默认关）、注销 202+15 天说明 | 注销两步确认、冻结即时、到期物理清除（DB+OSS）、版本不符 409 | test_privacy.py、test_auth_api.py（consents）；mobile tests/account.test.mjs |
| F13 GIF 分享 | (tabs)/index.tsx + components/GifExport.tsx | 导出 480p≤5s 水印+签名下载+系统分享面板 | 动作未就绪 409 AVATAR_NOT_READY、60s 超时提示、网页降级打开链接 | test_gif.py；mobile tests/gif-export.test.mjs；**真机分享面板待设备** |

## 2. 固定文案审计（本地完成，回归锁定）

FRD.md:342-348 要求「一字不差」。backend/tests/test_copy_audit.py（9 项）锁定：

| 文案 | FRD 出处 | 实现常量 |
| --- | --- | --- |
| 免责「AI 结果仅供日常健康管理参考,不替代专业兽医诊断」 | :344 | app/chat.py CHAT_DISCLAIMER、app/screening_api.py DISCLAIMER（聊天+初筛两处全覆盖） |
| 红线卡标题「建议立即就医」+副文案 | :345 | app/screening_api.py REDLINE_CARD、app/chat.py REDLINE_SUBTITLE/redline_response |
| 就医准备清单 4 条 | :346 | REDLINE_CARD.preparation、rules/advice_templates.yaml states.urgent.tips（逐条相等） |
| 喂养尾注「以上为公开营养学公式换算的参考值,非医嘱;请结合体况与兽医建议调整。」 | :347 | app/feeding.py FEEDING_DISCLAIMER |
| 音频尾注「情绪解读为娱乐性参考,置信度仅供判断展示。」 | :348 | app/audio.py AUDIO_FOOTER |
| 配额「明日再试」 | :338 | app/quota.py quota_gate 429 消息（审计断言） |
| GIF 水印「绒星 · AI 参考」 | F13 | app/gif.py WATERMARK_TEXT |

移动端产品文案（非 FRD 逐字要求，评审对象）同样被审计锁定：DELETION_NOTICE / DELETION_CONFIRM_LABEL / TRAINING_NOTICE（lib/account.ts）、QUOTA_EXHAUSTED_HINT（lib/quota.ts）、GIF_SHARE_HINT（lib/gif-export.ts）、SCREENING_SUGGESTION（lib/weight.ts）。

## 3. 专业评审议程（执行待外部）

### 3.1 兽医专业评审（责任人待确认）
评审材料（均版本化，可热更）：
- rules/redlines.yaml rl-2026-11-19：6 项红线（附录 B）＋派生规则（如呕吐 >24h）。
- rules/symptoms.yaml / triage 规则 sx/sc-2026-11-19：附录 A 分级表、扣分与 72h 衰减。
- REDLINE_CARD 与就医准备清单（§2）、rules/advice_templates.yaml at-2026-11-19（禁「确诊/治疗/诊断」）。
- rules/feeding.yaml fd-2026-11-19：RER=70×kg^0.75、DER 系数（<4月3.0 / 4–12月2.0 / 成年绝育1.2 / 未绝育1.4 / ≥11岁1.1）、干3.8/湿0.9 kcal/g、±10% 区间（附录 E）。
评审问题：① 分级阈值与红线覆盖是否有遗漏/误报风险；② 就医引导措辞是否足以驱动急诊行为且不引起过度恐慌；③ 喂养系数对特殊体况（哺乳/肥胖/慢性病）的边界提示是否充分；④ 免责与「非医嘱」定位是否合规；⑤ 音频情绪解读的娱乐边界是否清晰。
**高风险问题修复后必须复验**（规则版本号递增＋回归测试＋e2e）。

### 3.2 隐私合规评审
材料：协议版本化同意（consents）、训练授权默认关＋单独开关、注销 15 天物理清除（e2e 已验证 DB+OSS）、日志脱敏政策（OPERATIONS.md §2）、ai_usage_logs 匿名化。
待办：正式隐私政策/用户协议文本（当前为占位 HTTPS 链接）须法务/合规评审后替换；确认数据存储位置与跨境表述。

### 3.3 设计评审
待办：双端（iOS/Android）视觉对照 Figma；文本对比度（WCAG AA）抽查；读屏（VoiceOver/TalkBack）抽查；每个 P0 状态的设计证据归档（§7 台账）。

## 4. 素材版权与替代方案台账

| 素材 | 来源 | 版权状态 | 替代方案 |
| --- | --- | --- | --- |
| 占位片库 v1（3 体型×7 动作，backend/assets/placeholders） | 程序化生成（PIL+ffmpeg，app/placeholders.py） | 无第三方版权风险；**临时素材** | T19 评审后换授权/原创素材，manifest 版本递增整库替换（接口与缓存按版本失效，无需发版） |
| 首页 hero 图 mobile/assets/figma/59f10c90466cfa3aa84c0f88478dccedc8f69565.png | Figma 导出 | **授权待确认**（README 已注明） | 确认授权或替换为原创插画 |
| GIF 水印字体 | 系统 PingFang / Noto CJK 探测（GIF_WATERMARK_FONT 可指定） | 系统字体随 OS 许可；Noto 为 OFL | 指定自有授权 CJK 字体文件 |
| 个人分身素材 | 用户照片经 DashScope 生成 | 用户授权链路（上传即授权处理）；生成模型条款待 DashScope 凭证验收时核对 | 协议中明确生成内容使用权 |

## 5. 无障碍与视觉验收状态

已接线（本地可查）：入口超限置灰带 accessibilityState disabled；健康状态色恒附文字（状态档文案+分数）；GIF/录音/提醒权限拒绝均有文字提示路径；播放器损坏逐级回退不白屏。
待真机：对比度测量、读屏焦点顺序与朗读文案、动态字体/深色模式（当前浅色主题）、冷启动≤3s 与缓存首帧≤1s 观感。

## 6. 外部待办清单（T19 关闭条件）

1. Figma 节点对照：四 Tab+初筛入口结构化对照已完成（§7）；**剩余**：双端真机视觉对照、设计稿未覆盖子页面的补充设计或沿用确认。
2. 兽医评审执行与签署（§3.1），高风险修复复验。
3. 隐私文案法务评审（§3.2），正式协议替换占位链接。
4. 双端视觉对照+对比度+读屏抽查（§3.3/§5）。
5. 素材版权确认或替换（§4），占位库授权版本上线。

## 7. Figma 节点台账（2026-11-20 回填）

读取方式：figwright MCP（@figwright/mcp 0.7.0，Figma 插件 relay）get_variable_defs / get_design_context / get_vector / save_image_fills。文件 key sGhmzVC6reNoJdpy73X1zI，页「绒星」（18:93），设计基准 390×844。设计版本＝2026-11-20 读取快照；变量集＝「绒星 v2 / Foundations」（18:2，旧「绒星 / Design Tokens」2:2 已废弃不用）。验收方式＝结构化 design context 逐项对照（布局层级/坐标/颜色/字体/文案），非截图目测；真机视觉验收仍属外部待办。

| P0 流程 | 需求编号 | Figma 节点 ID | 变量/组件 | 设计版本 | 实现位置 | 验收结果 | 验收人/日期 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 品牌与基础规范 | 全局 | 21-115 | 绒星 v2/Foundations 全令牌 | 2026-11-20 快照 | mobile/src/theme.ts | 通过（色彩/字号/间距/圆角逐项一致） | lead/2026-11-20 |
| 组件规范 | 全局 | 21-116 | Button/StatusPill/Card/Input/导航 | 2026-11-20 快照 | mobile/src/components/ui/（Button/StatusPill/Card/TextField/EntryRow/SectionHeader/Icon）+ (tabs)/_layout.tsx DesignTabBar | 通过（h48 r24 按钮、四态 pill、r20 卡片、h56 r16 输入、白底导航选中 #A34400） | lead/2026-11-20 |
| 使用原则 | 全局 | 21-117 | 布局原则 | 2026-11-20 快照 | mobile/src/components/Screen.tsx（padding16/gap12/maxWidth560/安全区） | 通过 | lead/2026-11-20 |
| 首页 | F04/F07/F08/F03 | 22-309 | v2 令牌+画板专用色（heroBg #FFEDD7 等） | 2026-11-20 快照 | mobile/src/app/(tabs)/index.tsx | 通过（偏差 7/8/9） | lead/2026-11-20 |
| 健康 | F05/F06/F11 | 23-393 | v2 令牌+brand 底初筛入口+dangerBg 紧急入口 | 2026-11-20 快照 | mobile/src/app/(tabs)/health.tsx | 通过（偏差 7） | lead/2026-11-20 |
| 健康初筛入口 | F05-1 | 23-394 | 对象确认卡/01-03 内容卡/紧急提示 | 2026-11-20 快照 | mobile/src/app/screening/[petId].tsx（intro 阶段；form 阶段沿用原问卷逻辑换 v2 样式） | 通过（偏差 6） | lead/2026-11-20 |
| 聊聊 | F09 | 23-395 | 会话泡/输入胶囊/AI 提示卡 | 2026-11-20 快照 | mobile/src/app/(tabs)/chat.tsx | 通过（偏差 1/7；免责常量一字不差保留） | lead/2026-11-20 |
| 我的 | F01/F02/F10/F11/F12 | 23-396 | 用户卡/猫咪列表/分组菜单 | 2026-11-20 快照 | mobile/src/app/(tabs)/profile.tsx | 通过（偏差 2/3/4/5/7） | lead/2026-11-20 |

资产提取：cat-avatar.png（bfd9ce58…，头像/空态共用）、logo.png（48c27e42…）→ mobile/assets/figma/；hero 图 59f10c90… 与既有文件同哈希沿用（授权待确认，§4）；13 枚描边图标 get_vector → mobile/src/components/ui/icons.ts（不新增图标库）。

### 7.1 偏差清单（实现与设计稿的差异及理由）

1. **聊聊气泡映射**：画板为「猫左/助手右」的示意叙事；实现按视觉位置映射——pet（AI 猫）消息左侧带头像+surfaceRaised 泡，user 消息右侧 #FFE2B6 泡，消息语义与数据流不变。
2. **我的用户卡**：画板为 ● 占位+手机号；实现用 user 图标+账号昵称（GET /me）+「邮箱账号 · 已登录」（实际登录方式为邮箱验证）。
3. **我的「默认」标签**：首只猫咪加「默认」tag（对应首页默认选中 pets[0]）；画板未标注，语义补齐。
4. **提醒设置副标题**：画板「初筛、喂药与体重记录提醒」与实际功能不符（无喂药提醒）；改为「喂养时段与初筛复查提醒」（F10/F06 准确文案）。
5. **帮助与反馈**：无真实支持渠道，点击显示占位说明（帮助文档即将上线）；待产品提供渠道后接线。
6. **初筛入口尾注**：用设计稿文案「初筛结果仅供日常健康管理参考，不替代专业兽医诊断。」（非 FRD 逐字锁定常量）；锁定 DISCLAIMER 仍在结果页/聊聊/健康页一字不差使用（§2 审计不变）。
7. **画板外功能保留**：首页「分身与分享」区（PhotoUpload/GifExport/时间线入口）、我的配额卡+权益说明、聊聊录音/离线同步横幅、健康通知权限横幅——设计稿未画但属 P0 功能，按 v2 令牌风格保留。
8. **首页 hero**：用 AvatarStage 组件（无分身时静态兜底图＝画板视觉）；分身生成后播放个人片段，功能优先于静态画板。
9. **状态栏/系统适配**：画板状态栏为示意；实现跟随系统安全区与系统字号（文档规则要求）。
10. **画板外账号状态**：未登录/未同意协议态沿用原有登录/注册/补发验证/协议同意流程（账号入口在「我的」Tab，无独立登录路由）；注销与训练授权使用 lib/account 锁定文案（DELETION_NOTICE/DELETION_CONFIRM_LABEL/TRAINING_NOTICE）与应用内两步确认（原生无 window.confirm）；401 自动回退登录态、CONSENT_REQUIRED/VERSION_CHANGED 清空协议态等边界逻辑全部保留。

### 7.2 验证证据（2026-11-20）

mobile typecheck EXIT=0；eslint EXIT=0 无警告；node --test 155/155 pass（lib 纯逻辑与契约未改动，git diff 仅页面/theme/Screen/_layout+新增 ui kit+资产）；npx expo export --platform web EXIT=0。后端无改动（417 OK 基线不变）。

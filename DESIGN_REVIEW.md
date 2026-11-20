# T19 · 设计与专业评审 —— 本地交付与评审议程

状态（2026-11-20）：**本地可执行部分已完成**——P0 流程矩阵、固定文案审计（回归测试锁定）、专业评审议程、素材版权台账、无障碍接线盘点。
**外部待办（不虚构完成）**：Figma 节点逐项对照、兽医/隐私/设计专业评审的执行与签署、双端视觉对照、对比度与读屏真机抽查。责任人待 plan「尚需决策」确认（docs/superpowers/plans/2026-11-17-rongxing-full-stack.md:251）。

## 1. P0 流程设计 / 文案 / 状态验收矩阵

每行：需求 → 移动端界面 → 成功/失败状态 → 本地测试证据 → 设计对照状态。
「设计对照」统一为 **待 Figma 节点对照**（本会话无 Figma 访问；节点台账模板见 §7）。测试证据为 backend/tests 与 mobile/tests 中可重跑文件。

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

1. Figma 节点对照：按 §7 台账逐 P0 流程记录节点 ID/变量/组件/需求编号/设计版本/验收结果。
2. 兽医评审执行与签署（§3.1），高风险修复复验。
3. 隐私文案法务评审（§3.2），正式协议替换占位链接。
4. 双端视觉对照+对比度+读屏抽查（§3.3/§5）。
5. 素材版权确认或替换（§4），占位库授权版本上线。

## 7. Figma 节点台账模板（待填）

| P0 流程 | 需求编号 | Figma 节点 ID | 变量/组件 | 设计版本 | 实现位置 | 验收结果 | 验收人/日期 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| （示例）分身上传 | F03-1 | 待填 | 待填 | 待填 | components/PhotoUpload.tsx | 待对照 | 待填 |

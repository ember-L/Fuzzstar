# 团队协作与 Git 工作流

> 适用：绒星 RongXing 后端（FastAPI）与移动端（Expo）多人并行开发。读者：所有要往 `main` 提交代码的人。
> 生效日期：2026-11-21　维护：仓库管理员　冲突时以本文与 [FRD](product/FRD.md) 的事实源优先级为准。

## 0. 先回答：需要新开分支吗

**需要，但不是新开一个长期开发分支。**

| 问题 | 结论 |
| --- | --- |
| 要不要建 `develop` / 长期 `dev` 分支？ | **不要**。多一条长期分支就要多一轮合并，内测阶段只会增加冲突与"哪边是真相"的成本。 |
| 每次改代码要不要开分支？ | **要**。包括一行修复、文档、依赖升级。分支从 `main` 切出，1–3 天内合回并删除。 |
| `main` 能不能直接提交？ | **队员不能，管理员可以**。`main` 对队员只接受 PR；管理员（仓库 owner）保留直推能力，用于合并收尾与线上回滚。 |
| 发布怎么管？ | **用 tag 冻结**（`v0.1.0-beta.1`），不靠分支。只有"已上线版本要单独修 bug"时才临时切 `release/x.y`。 |

一句话：**`main` 受保护 + 任务分支（短命）+ Squash PR + 语义化 tag**，即主干开发（trunk-based）加 PR 门禁；管理员保留绕过门禁的直推通道。

```text
main   ──●────●─────────●─────────●──────▶  队员走 PR，管理员可直推
          \            /          /
 feat/a    ●──●──●─────            /        1–3 天，合并即删
                        \        /
 feat/b                  ●──●──●─            与 feat/a 并行，互不阻塞
          │            │         │
        tag v0.1.0   tag v0.2.0  tag v0.2.1
```

---

## 1. 当前仓库体检（2026-11-21）

引入团队前先看清现状，下表每一项都对应第 2 节的一个动作。

| 项目 | 现状 | 影响 / 动作 |
| --- | --- | --- |
| 远端 | `github.com/ember-L/Fuzzstar`，**public** | 任何 push 立即公开；涉密前先转 private |
| 默认分支 | `main`，与 `origin/main` 同步，最新 `2a57ff9 测试版上线` | 以此为协作基线 |
| 分支 | 只有 `main` | 团队进来后按第 3 节切分支 |
| tag | **0 个** | 发布点不可追溯，先补 `v0.1.0-beta.1` |
| `main` 保护 | **未保护**（GitHub API 返回 `Branch not protected`） | 任何人可直推、强推、删分支；必须开启 |
| CI | 无 `.github/`、无 workflow | PR "绿灯"不可信，门禁靠本地命令 + 评审 |
| 贡献者 | 单作者历史 | 协作规范、PR 模板、CODEOWNERS 均未建立 |
| 忽略规则 | 根 `.gitignore` 全局忽略 `*.png`、`视觉参考/`、`.codegraph/`、`.superpowers/`、`.impeccable/` | 新增图片默认不进仓库，见第 12 节 |
| 依赖产物 | `backend/.venv/`、`mobile/.expo/`、`mobile/dist/`、`mobile/ios`、`mobile/android` 已忽略 | 保持忽略，不要 `-f` 强加 |

---

## 2. 开工前的一次性设置（管理员，约 30 分钟）

### 2.1 冻结当前基线

先把"测试版上线"这个可用状态钉成 tag，团队才有回滚锚点。

```sh
git switch main
git pull --ff-only
git tag -a v0.1.0-beta.1 -m "内测基线：测试版上线"
git push origin v0.1.0-beta.1
```

### 2.2 确认仓库可见性

当前是 public。若仓库将包含商业计划、内测数据、未公开规则包：

`Settings → General → Danger Zone → Change visibility → Make private`

转 private 后要复核：成员是否仍有权限、Actions 额度、以及任何依赖 raw 链接的外部引用。

### 2.3 保护 `main`

`Settings → Branches → Add branch protection rule`，Branch name pattern 填 `main`：

| 选项 | 设置 | 原因 |
| --- | --- | --- |
| Require a pull request before merging | ✅ | 禁止队员直推（管理员可绕过） |
| Required approvals | **1** | 双人复核；3 人以下团队也不要设 0 |
| Dismiss stale approvals when new commits are pushed | ✅ | 改完要重新看 |
| Require review from Code Owners | 有 `CODEOWNERS` 时 ✅ | 领域 owner 兜底 |
| Require conversation resolution | ✅ | 评论不能"看过就算" |
| Require linear history | ✅ | 配合 Squash，保持 `main` 单线 |
| Do not allow bypassing the above settings | ❌（不勾 Include administrators） | 管理员可直推、可自合，用于收尾与回滚 |
| Allow force pushes | ❌ | 保护历史 |
| Allow deletions | ❌ | 防止误删主干 |
| Require status checks to pass | CI 落地后 ✅ | 勾选 `backend-tests`、`mobile-checks`（见附录 A） |

> **本仓库当前的实际状态**：`Include administrators` 已关闭（`enforce_admins=false`），其余保护照旧（1 approval、linear history、禁强推、禁删）。代价是管理员直推时这些限制一起失效，所以直推只用于两类场景：合并后的收尾提交、线上故障回滚。日常改动仍走 PR——少了 PR，diff 与评审记录就断了。

### 2.4 成员与权限

- 日常开发给 **Write**，不给 Admin；Admin 只保留 1 人。
- 要求所有成员开启 2FA（组织设置或 `Settings → Password and authentication`）。
- 离队当天移除权限；不要用共享账号。
- 3 人以上时用 GitHub Teams 管理，而不是逐个加人。

### 2.5 密钥与历史

- 真实 Key 只允许存在于 `backend/.env`（已忽略）和 GitHub Actions Secrets。
- 提交前自查：`git diff --cached | grep -iE 'sk-|password|secret|token'`。
- 一旦误提交：**先轮换 Key**，再用 `git filter-repo` 清历史；只删文件无效。
- 新人第一条规则：`cp backend/.env.example backend/.env`，永远不要提交 `.env`。

### 2.6 CI（强烈建议，先于团队扩张）

没有 CI 时，第 2.3 节的"必须通过检查"是空选项，评审人只能相信作者贴的本地输出。附录 A 给了可直接落地的最小 workflow；合并后把两个 job 设为必需检查。

### 2.7 协作模板（可选）

- `.github/pull_request_template.md`：见附录 B，复制即用。
- Issue 模板：`.github/ISSUE_TEMPLATE/bug.md`、`feature.md`，至少约定"现象 / 复现 / 期望 / 环境"。

---

## 3. 分支模型

### 3.1 分支类型

| 类型 | 命名 | 切自 | 合入 | 寿命 | 例子 |
| --- | --- | --- | --- | --- | --- |
| 主干 | `main` | — | — | 永久 | — |
| 功能 | `feat/<slug>` | `main` | `main` | 1–3 天 | `feat/diet-quick-add` |
| 修复 | `fix/<slug>` | `main` | `main` | < 1 天 | `fix/chat-keyboard-cover` |
| 文档 | `docs/<slug>` | `main` | `main` | < 1 天 | `docs/collaboration-guide` |
| 杂务 | `chore/<slug>` | `main` | `main` | < 1 天 | `chore/bump-expo-audio` |
| 重构 | `refactor/<slug>` | `main` | `main` | 1–3 天 | `refactor/screening-service` |
| 测试 | `test/<slug>` | `main` | `main` | < 2 天 | `test/quota-race` |
| 热修复 | `hotfix/<slug>` | 线上 tag | `main` + `release/*` | < 1 天 | `hotfix/consent-500` |
| 发布维护 | `release/<x.y>` | 线上 tag | 只进 `hotfix` | 按需 | `release/0.2` |

### 3.2 命名规则

- 全小写、连字符分隔、**不用中文、空格、下划线、日期**。
- 有 Issue 时带编号：`feat/diet-quick-add-42`。
- 长度 ≤ 40 字符，能一眼看出改什么。
- 一个分支只做一件事；"顺手改"另开分支。

### 3.3 明确禁止

- ❌ 长期 `develop` / `dev` / `test` 分支。
- ❌ 个人名分支（`ember-dev`）当共享区。
- ❌ 直接 push `main`、强推 `main`、删除 `main`。
- ❌ 两人共用一条分支（提交历史会互相踩）。
- ❌ 一个 PR 混入多个不相关任务。

---

## 4. 日常开发流程

```sh
# 0) 领任务：GitHub Issue 或看板卡片，确认验收标准

# 1) 同步主干（只允许快进，避免本地脏合并）
git switch main
git pull --ff-only

# 2) 切任务分支
git switch -c feat/diet-quick-add-42

# 3) 小步开发与提交（见第 5 节）
git add -p                       # 逐块确认，避免带入 .env / 无关文件
git commit -m "feat(backend): 饮食快录写入失败进入本机队列"

# 4) 提交前自检（见第 7 节），把命令与结果留在终端

# 5) 推送并开 PR（跨天任务第一天就开 Draft）
git push -u origin feat/diet-quick-add-42

# 6) 评审通过后：Squash and merge → Delete branch

# 7) 回到主干并清理
git switch main && git pull --ff-only
git branch -d feat/diet-quick-add-42
git fetch -p
```

**每天至少同步一次 `main`**（`git rebase main`，只在自己的未合并分支上做）。

---

## 5. 提交信息规范

格式：

```text
<type>(<scope>): <摘要>

<正文：为什么改、有什么取舍，可选>

<footer：BREAKING CHANGE / Closes #42，可选>
```

### 5.1 type

| type | 用途 |
| --- | --- |
| `feat` | 新功能（用户可感知） |
| `fix` | 修 bug |
| `docs` | 只改文档 |
| `refactor` | 不改行为的重构 |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `build` | 构建、依赖、打包 |
| `ci` | CI / 脚本 |
| `chore` | 杂务（版本号、忽略规则） |
| `revert` | 回滚某次提交 |

### 5.2 scope

`backend`、`mobile`、`docs`、`rules`、`db`、`ci`、`deps`；跨层可省略。

### 5.3 规则与示例

- 摘要 ≤ 50 字，不加句号，用祈使语气（"增加"而不是"增加了"）。
- 正文写**为什么**，不要复述 diff。
- 破坏性变更：`feat(api)!: 调整 /pets 响应结构`，并在 footer 写 `BREAKING CHANGE: ...`。

```text
feat(backend): 饮食快录失败进入本机队列并按原幂等键补发

fix(mobile): 修复聊聊页在 iOS 上键盘遮挡输入框
docs: 补充团队协作与分支规范
chore(deps): 将 expo-audio 升级到 58.0.12
feat(rules)!: 健康初筛规则包升到 v3
```

**禁止**：`update`、`fix bug`、`111`、`测试`、`WIP` 直接进 `main`。

---

## 6. PR 规范

### 6.1 标题与描述

- 标题与提交规范一致；Squash 后它就是 `main` 上的提交信息。
- 描述固定五段（模板见附录 B）：
  1. **改了什么**（模块 + 行为）
  2. **为什么**（Issue 链接 / 用户问题）
  3. **怎么验证**（命令 + 关键输出，UI 附截图或录屏）
  4. **风险与回滚**（迁移、配置、灰度、回滚步骤）
  5. **文档同步**（改了哪些文档 / 为什么不用改）

### 6.2 大小与节奏

- 有效 diff **≤ 400 行**；超过 800 行必须拆。
- 跨天任务第一天开 **Draft PR**，让评审人早看到方向。
- 纯格式化 / 重命名单独一个 PR，不和逻辑改动混在一起。

### 6.3 评审

- 至少 **1 位** reviewer；作者不能自批。管理员可以直推，但日常改动仍走 PR，否则评审记录会断。
- 首轮响应 **24 小时内**；超时在站会升级。
- 评审人只看 diff + 关联文档 + 测试证据，不要求作者口头解释。
- 评论用 `nit:` 标注非阻塞建议，避免"改了十轮还在抠格式"。

### 6.4 合并

- **只允许 `Squash and merge`**：一个 PR 一个提交，`main` 保持线性。
- 禁止 merge commit；不启用 Rebase and merge（避免与 Squash 混用产生两种历史形态）。
- 合并前确认：CI/本地门禁通过、对话已解决、文档已同步。
- 合并后**立即删除远端分支**。

---

## 7. 合并门禁（按改动范围执行）

| 改动范围 | 必跑 | 必须同步的文档 |
| --- | --- | --- |
| `backend/app/**` 业务逻辑 | `cd backend && python -m pytest -q` | 行为变化 → `docs/features.md` |
| `backend/migrations/**` | `pytest tests/test_migrations.py` + 真 MySQL `upgrade head` / `downgrade -1` 往返 | `docs/architecture.md` 数据模型 |
| `backend/rules/*.yaml` | 升 `version` + `pytest tests/test_health.py tests/test_screening_worker.py` | `docs/product/FRD.md` 规则附录 |
| 固定文案（免责声明 / 红线 / 错误码） | `pytest tests/test_copy_audit.py` | `docs/product/FRD.md` |
| `mobile/src/**` | `cd mobile && npm run typecheck && npm run lint && node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --test tests/*.test.mjs` | 交互变化 → `docs/features.md` |
| API 路由 / schema | `pytest` | `docs/features.md` + `docs/architecture.md` |
| 新增环境变量 | 本地启动一次 | `backend/.env.example` + `README.md` + `docs/operations.md` |
| Python 依赖 | `requirements.txt` 固定版本、全量测试 | — |
| 移动端依赖 | `npx expo install <pkg>`（**不要** `npm install` 直接加） | `README.md` 技术栈 |
| 隐私 / 配额 / 删除 | `pytest tests/test_privacy.py tests/test_quota.py tests/test_observability.py` | `docs/operations.md` |
| 迁移、部署、Compose | `docker compose build` + 冒烟 | `docs/operations.md` |

> 没有 CI 时，**把命令与关键输出贴进 PR 描述**；"我本地跑过了"不算证据。

---

## 8. Code Review 清单（本项目专属）

评审时按顺序过，任一项为"否"就退回：

- [ ] 健康初筛、健康分、红线分流仍在**规则层**，没有被 LLM、前端或 prompt 短路。
- [ ] 红线消息**零 LLM**，直接转就医引导；没有用 AI 文案覆盖固定文案。
- [ ] 写失败是否有本机队列 + **原幂等键**补发；重试不会重复扣配额。
- [ ] 迁移可回滚、`down_revision` 正确、无大表锁 / 长事务；SQLite 测试之外考虑 MySQL 8 行为。
- [ ] 隐私边界：训练授权默认关闭、注销 15 天冷静期与物理清除未被绕过。
- [ ] 日志脱敏：手机号、邮箱、token、音频/媒体 URL 不进明文日志。
- [ ] 错误码与固定文案和 FRD 一致；新增文案已进 `test_copy_audit.py`。
- [ ] 移动端遵守 Expo SDK 58 版本化 API；`ios/`、`android/` 未被手改。
- [ ] 新依赖必要、许可证可接受、体积可控；能用 Expo 官方模块就不引三方。
- [ ] 没有真实 Key、内网地址、个人绝对路径、调试后门。
- [ ] 文档与代码同步（第 7 节表格）。

---

## 9. 冲突与分支同步

- **只 rebase 自己的分支**；推送用 `git push --force-with-lease`（不要裸 `--force`）。
- 不 rebase `main`、`release/*`、别人的分支、已合并提交。
- 冲突解决后**必须重跑第 7 节门禁**，不能"解完就合"。
- 大范围重构用**扩张—收缩**三步，拆成多个 PR：
  1. 加新实现（不改调用方）
  2. 逐个迁移调用方
  3. 删旧实现
- 高频冲突文件约定：`backend/app/main.py`、`backend/app/routers/__init__.py`、`mobile/app.json`、`backend/requirements.txt`——谁先改谁先合，另一个负责 rebase。
- 冲突超过 30 分钟仍无头绪：停下来找对方对齐，不要靠"接受双方"硬合。

---

## 10. 发布与版本

- **主干发布**：`main` 每个可发布点打 annotated tag：`vMAJOR.MINOR.PATCH[-beta.N]`。
- 0.x 阶段：不兼容变更升 MINOR，修复升 PATCH；内测用 `-beta.N`。
- **tag 只增不改**：已推送的 tag 禁止移动或删除；打错了发新 tag 并在 Release notes 说明。
- Release notes 固定四段：**变更 / 迁移 / 配置 / 回滚**。
- **发布分支**：仅当 v0.2 已上线、`main` 已进入 v0.3 开发，却还要给 v0.2 修 bug 时，才从 tag 切 `release/0.2`；否则不要建。
- **热修复**：从线上 tag 切 `hotfix/xxx` → 修复 → PR 回 `main`（存在 `release/*` 时同步回合）→ 打新 PATCH tag。

```sh
git tag -a v0.2.0-beta.1 -m "内测：健康初筛与叫声解读"
git push origin v0.2.0-beta.1
# 生成 Release：GitHub → Releases → Draft a new release → 选 tag → 填四段
```

---

## 11. 协作节奏（3–5 人）

- **一人一分支**，不共享；分支即任务。
- 每日 15 分钟同步：昨天完成 / 今天计划 / 阻塞项。
- 看板四列：`Todo → Doing → Review → Done`；`Review` 超过 24 小时的 PR 在站会点名。
- 每周五清理：已合并本地/远端分支、stale PR、过期 Issue。
- 领域 owner（可选 `CODEOWNERS`）：`backend/`、`mobile/`、`backend/rules/` 各 1 人做最终 review。
- 排期以 Issue 为准，聊天记录里的口头承诺不算交付约定。

---

## 12. 常见坑（本仓库实测）

| 坑 | 现象 | 处理 |
| --- | --- | --- |
| 根 `.gitignore` 全局忽略 `*.png` | 新增截图/设计稿在 `git status` 里看不到 | 确需入库时 `git add -f path/to.png`；长期方案是把规则改成按目录忽略 |
| `视觉参考/` 被整体忽略 | 同事拉仓库后没有设计参考图 | 需要共享就放 `docs/` 或对象存储，不要 `-f` 硬塞大图 |
| `.codegraph/`、`.superpowers/`、`.impeccable/` 被忽略 | 本地工具产物不同步 | 正常，不要提交 |
| `backend/.venv/`、`mobile/.expo/`、`mobile/dist/` | 误提交导致仓库膨胀 | 保持忽略；提交前 `git status` 复核 |
| `EXPO_PUBLIC_*` 构建期内联 | 改了 API 地址 App 仍用旧值 | 重新构建或 `npx expo start -c`；PR 中注明需重新打包 |
| 仓库 public | 任何 push 立刻对外可见 | 涉密前转 private；提交前检查内网地址与真实 Key |
| 无 CI | PR "看起来没问题" | 贴本地命令与输出；尽快落地附录 A |
| 测试用 SQLite、运行时用 MySQL 8 | 本地全绿但迁移/查询线上失败 | 迁移类 PR 必须在 MySQL 8 上跑 `upgrade`/`downgrade` 往返 |
| `git commit -a` | 把 `.env`、`.venv` 一起提交 | 用 `git add -p`；commit 前 `git diff --cached --stat` |
| 直接 `git push origin main` | 被保护规则拒绝（开启后） | 这是预期行为；切分支开 PR |

---

## 13. 命令速查

```sh
# 看状态与差异
git status -sb
git diff --stat
git diff --cached            # 即将提交的内容

# 同步
git switch main && git pull --ff-only
git fetch -p                 # 清理远端已删分支引用

# 在自己的分支上跟进主干
git rebase main
git push --force-with-lease

# 提交（逐块挑选，避免带入无关文件）
git add -p
git commit -m "fix(mobile): 修复键盘遮挡"

# 撤销
git restore <file>                 # 丢弃工作区改动
git restore --staged <file>        # 取消暂存
git reset --soft HEAD~1            # 撤销最后一次提交，保留改动
git revert <sha>                   # 公共分支上的安全回滚

# 排查
git log --oneline --graph -20
git log -L 10,40:backend/app/services/screening.py
git blame -L 10,40 -- <file>
git reflog                         # 找回误删/误 reset 的提交

# 分支清理
git branch -d feat/xxx             # 已合并
git push origin --delete feat/xxx
```

---

## 14. 一页 checklist

**作者（开 PR 前）**

- [ ] 分支名符合第 3 节，基于最新 `main`
- [ ] 提交信息符合第 5 节，一个提交一件事
- [ ] 第 7 节对应门禁已跑，输出已贴
- [ ] 没有 `.env`、真实 Key、`.venv`、`.expo`、构建产物
- [ ] PR 描述五段齐全，UI 改动有截图/录屏
- [ ] 相关文档已改（或说明为什么不用改）

**评审者**

- [ ] 行为是否符合 Issue 验收标准
- [ ] 红线/分级是否绕过规则层
- [ ] 迁移、配额、隐私、幂等是否安全
- [ ] 测试是否覆盖新分支与失败路径
- [ ] 文档与配置是否同步

**合并者**

- [ ] 检查全绿、对话已解决
- [ ] Squash and merge，标题即提交信息
- [ ] 删除远端分支，提醒作者同步 `main`

---

## 15. 管理员：拉取并本地验收队员分支

> 场景：队员把 `feat/xxx` 推到远端，你要在自己的机器上跑起来验证，而不是只看 diff。
> 前提：队员的分支必须已经 push（`git push -u origin feat/xxx`），本地没推的分支谁也拉不到。

### 15.1 先确认分支在哪

| 队员权限 | 分支位置 | 拉取方式 |
| --- | --- | --- |
| 仓库 Write（同仓库分支） | `origin/feat/xxx` | `git fetch` 后直接切 |
| 只有 Read（用 fork 提 PR） | fork 的 `pull/<PR号>/head` | `gh pr checkout <PR号>` |
| 只给了 PR 链接 | 同上 | 同上 |

发现最近推送的分支：

```sh
git fetch --all --prune
git for-each-ref --sort=-committerdate \
  --format='%(refname:short)  %(committerdate:relative)  %(authorname)' \
  refs/remotes/origin | head -20

gh pr list --state open            # 需要先 gh auth login
gh pr view 42 --json headRefName,headRefOid,isCrossRepository
```

### 15.2 拉取（优先用 worktree，不动你当前的工作区）

**A. 同仓库分支 + 独立 worktree（推荐）**

```sh
git fetch origin
git worktree add ../rongxing-review feat/xxx   # 自动跟踪 origin/feat/xxx
cd ../rongxing-review
git log -1 --format='%H %s'                    # 记下 SHA，和 PR 页面对一下
```

**B. 直接切到本地（会切换你当前目录）**

```sh
git fetch origin
git switch feat/xxx            # 本地没有时自动建跟踪分支
```

**C. fork 来的 PR**

```sh
gh pr checkout 42              # 自动处理 fork 与 remote
# 没有 gh 时：
git fetch origin pull/42/head:review/pr-42
git switch review/pr-42
```

> 不要 `git clone` 整个仓库再切分支，除非你确实需要一份全新副本；worktree 更省空间。

### 15.3 核对版本：别验到旧提交

```sh
git log -1 --format='%H %s'
gh pr view 42 --json headRefOid,headRefName   # 两个 SHA 必须一致
git log --oneline main..HEAD                  # 这个分支比 main 多了什么
```

### 15.4 在本地跑起来

分支里**没有** `backend/.env`（被忽略），必须自己准备；建议用**独立数据库**，避免把主开发库迁到分支的 schema。

```sh
# 1) 配置：复制模板，DATABASE_URL 指向独立库（如 rongxing_review）
cp backend/.env.example backend/.env       # worktree 里没有就从上个项目目录拷
# JWT_SECRET 重新生成：python -c 'import secrets; print(secrets.token_urlsafe(32))'

# 2) 依赖：只在清单变化时重装
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # 对比 main 看 requirements.txt 是否变化
python -m alembic upgrade head             # 分支带迁移时必须跑

# 3) 起后端（业务联调必须用 create_dev_app）
uvicorn app.main:create_dev_app --factory --host 127.0.0.1 --port 8000

# 4) 起移动端（package-lock.json 变了就用 npm ci，不要 npm install）
cd ../mobile
npm ci
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1 npm start

# 5) 跑门禁（见第 7 节）
cd ../backend && python -m pytest -q
cd ../mobile && npm run typecheck && npm run lint && \
  node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --test tests/*.test.mjs
```

想用容器跑整套：

```sh
docker compose up -d --build     # 会执行 migrate，把 .env 指向的库升到分支 schema
docker compose logs -f api
```

> 端口 8000 只能有一个占用者：先停本地 uvicorn，或改 `docker-compose.yml` 的宿主端口。验收分支的迁移会改库，验完切回 `main` 要 `alembic downgrade` 或重建库——所以独立库最省事。

### 15.5 看差异、做验收

```sh
git diff main...HEAD --stat        # 三点：以 merge-base 为基准，不把 main 的新提交算进来
git diff main...HEAD -- backend/app
git log --oneline --graph main..HEAD
```

验收结论直接写进 PR：跑通的命令、失败项、截图、需要作者补的测试。通过后在 GitHub 上 **Squash and merge**。

### 15.6 合并后的清理

```sh
git worktree remove ../rongxing-review
git switch main && git pull --ff-only
git branch -d feat/xxx
git fetch -p
```

### 15.7 队员 rebase / force-push 之后

对方分支被改写，你本地的同名分支会分叉。**不要 merge**，直接对齐远端（确认本地没有自己的提交）：

```sh
git fetch origin
git switch feat/xxx && git reset --hard origin/feat/xxx
```

在 worktree 里同理。永远不要在别人的分支上做本地提交；要改就评论或让作者改。

### 15.8 安全边界

- **跑分支等于执行对方代码**：`npm ci` 会跑 `postinstall`，Python 导入即执行。先看 diff 再跑，尤其是新增脚本、`package.json` 的 install 钩子、`requirements.txt` 里的陌生包。
- 用独立 worktree + 独立 venv + 独立数据库；**不要**把生产 `.env`、真实 DashScope / S3 / SMTP Key 放进验收目录。
- 本仓库是 public：任何人都能看到分支内容；反过来，也别把内部地址、真实用户数据写进分支。
- 验收完删掉 worktree 与临时分支，避免以后误跑旧代码。

## 附录 A：最小 CI（可选，尚未落地）

仓库当前没有 CI。落地后把两个 job 设为 `main` 的必需检查。注意：`mobile/` 已有 `package-lock.json`，`mobile/tests/*.test.mjs` 已存在。

```yaml
# .github/workflows/ci.yml
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: backend/requirements.txt
      - run: pip install -r requirements.txt
      - run: python -m pytest -q

  mobile-checks:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: mobile/package-lock.json
      - run: npm ci
      - run: npm run typecheck
      - run: npm run lint
      - run: node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --test tests/*.test.mjs
```

> 依赖真实 Redis / S3 的用例默认跳过（见 README「测试」）；需要时再加 service container 与 `REDIS_TEST_URL`。

## 附录 B：PR 模板

```markdown
## 改了什么
-

## 为什么
Closes #

## 怎么验证
```sh
# 命令与关键输出
```

## 风险与回滚
- 迁移：
- 配置：
- 回滚：

## 文档同步
- [ ] features / architecture / FRD / operations 已更新，或说明不需要
```

---

## 相关文档

- [文档索引](README.md)：文档维护约定与事实源优先级
- [架构](architecture.md)：模块边界与数据模型（接口变更必须同步）
- [功能与 API](features.md)：当前行为与本地 API 范围
- [运维 Runbook](operations.md)：环境变量、迁移、发布与告警
- [FRD](product/FRD.md)：功能验收、错误码与固定文案（冲突时以此为准）

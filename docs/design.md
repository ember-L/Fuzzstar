---
name: 绒星 RongXing
description: 星光护绒，健康相伴 — 一盏暖灯下的猫咪健康起居室
colors:
  lamp-amber: "#FEAE36"
  lamp-amber-pressed: "#EE941D"
  ember-glow: "#FF9F24"
  honey-wash: "#FFF0DF"
  hero-peach: "#FFEDD7"
  bubble-peach: "#FFE2B6"
  burnt-caramel: "#A34400"
  spark-ember: "#ED7413"
  canvas-white: "#FFFFFF"
  linen-card: "#FAF8F6"
  cocoa-ink: "#4B2617"
  bark-ink: "#743A10"
  clay-gray: "#805535"
  sand-edge: "#D9BFA5"
  sand-edge-strong: "#89552F"
  mist-pill: "#F3EEE9"
  muted-fawn: "#C6A894"
  chevron-fawn: "#B59B88"
  timestamp-fawn: "#A78976"
  disabled-sand: "#E9DED2"
  disabled-clay: "#796B60"
  danger-red: "#B42318"
  danger-wash: "#FFF1F0"
  success-green: "#166534"
  success-wash: "#EDF8EE"
  warning-umber: "#8A4B00"
  warning-wash: "#FFF4D8"
  focus-azure: "#315CBE"
typography:
  display:
    fontFamily: "PingFang SC, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"
    fontSize: "25px"
    fontWeight: 600
    lineHeight: 1.4
  headline:
    fontFamily: "PingFang SC, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 600
    lineHeight: 1.33
  title:
    fontFamily: "PingFang SC, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.4
  subtitle:
    fontFamily: "PingFang SC, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.44
  body:
    fontFamily: "PingFang SC, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  caption:
    fontFamily: "PingFang SC, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "PingFang SC, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.5
rounded:
  sm: "8px"
  md: "12px"
  lg: "20px"
  xl: "24px"
  pill: "999px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "20px"
  s6: "24px"
  s7: "32px"
  s8: "40px"
components:
  button-primary:
    backgroundColor: "{colors.lamp-amber}"
    textColor: "{colors.cocoa-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    height: "48px"
    padding: "0 24px"
  button-primary-pressed:
    backgroundColor: "{colors.lamp-amber-pressed}"
    textColor: "{colors.cocoa-ink}"
    rounded: "{rounded.xl}"
    height: "48px"
    padding: "0 24px"
  button-secondary:
    backgroundColor: "{colors.honey-wash}"
    textColor: "{colors.burnt-caramel}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    height: "48px"
    padding: "0 24px"
  button-disabled:
    backgroundColor: "{colors.disabled-sand}"
    textColor: "{colors.disabled-clay}"
    rounded: "{rounded.xl}"
    height: "48px"
    padding: "0 24px"
  card:
    backgroundColor: "{colors.linen-card}"
    textColor: "{colors.bark-ink}"
    rounded: "{rounded.lg}"
    padding: "24px"
  entry-row:
    backgroundColor: "{colors.linen-card}"
    textColor: "{colors.bark-ink}"
    rounded: "{rounded.md}"
    padding: "14px"
    height: "50px"
  status-pill-success:
    backgroundColor: "{colors.success-wash}"
    textColor: "{colors.success-green}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    height: "42px"
    padding: "0 20px"
  status-pill-warning:
    backgroundColor: "{colors.warning-wash}"
    textColor: "{colors.warning-umber}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    height: "42px"
    padding: "0 20px"
  status-pill-danger:
    backgroundColor: "{colors.danger-wash}"
    textColor: "{colors.danger-red}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    height: "42px"
    padding: "0 20px"
  status-pill-neutral:
    backgroundColor: "{colors.honey-wash}"
    textColor: "{colors.clay-gray}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    height: "42px"
    padding: "0 20px"
  text-field:
    backgroundColor: "{colors.linen-card}"
    textColor: "{colors.bark-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    height: "56px"
    padding: "0 20px"
  chip-filter:
    backgroundColor: "{colors.canvas-white}"
    textColor: "{colors.bark-ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "0 12px"
  chip-filter-active:
    backgroundColor: "{colors.honey-wash}"
    textColor: "{colors.bark-ink}"
    rounded: "{rounded.md}"
    height: "40px"
    padding: "0 12px"
  tab-bar:
    backgroundColor: "{colors.canvas-white}"
    textColor: "{colors.burnt-caramel}"
    typography: "{typography.label}"
    height: "56px"
  hero-card:
    backgroundColor: "{colors.hero-peach}"
    textColor: "{colors.cocoa-ink}"
    typography: "{typography.display}"
    rounded: "{rounded.xl}"
    padding: "16px"
---
# Design System: 绒星 RongXing

## Overview

**Creative North Star: "星灯起居室 The Starlit Sitting Room"**

绒星不是一间诊室，是一间开着灯的起居室：暖光落在猫的身上，主人蹲下来看一眼，就够了。整个视觉系统只有一件「家具」——一盏橘色的灯（#FEAE36）。它照亮按钮、照亮选中项、照亮猫的轮廓，除此之外的一切都是米白与亚麻，安静得像墙面。安全感不靠冷色与表格堆出来，靠「这里不会吓我」的氛围，加上一条随时清晰可见的红线。

密度上，一屏只说一件事。首页是「今天它还好吗」，健康页是「分数与扣分项」，聊聊页是「对话」，我的页是「资料与设置」。留白是主要的排版手段：390×844 画板基准、左右 16px 边距、卡片间距 12px，内容容器最宽 560px 后居中，再宽就留白，不做双栏。

质感上，这个系统是严格平面的：全仓 shadowOpacity / shadowRadius / elevation / boxShadow 命中数为 0，零渐变、零毛玻璃。层次靠色阶（纸白 → 亚麻 → 蜜水 → 橘），反馈靠透明度按压与 300ms 的淡入淡出。形状语言圆润但不幼稚：按钮是 h48/r24 的胶囊，卡片 r20，列表行 r16，输入框 h56/r16——容器越大，圆角越大。

**Key Characteristics:**
- 单一暖色强调：橘色只做填充与选中，绝不做文字（#FEAE36 在纸白上仅 1.85:1）
- 严格平面：零投影、零渐变、零玻璃，深度来自四层色阶
- 大圆角、大留白，一屏一个主题
- 中文优先的系统中文字体（PingFang SC / 系统 sans），字重承担全部层级
- 语义色成对出现：底色 + 同色系深字，符号与颜色永不单独承载状态
- 红线红 #B42318 专用「立即就医」红线路径，不用于装饰

## Colors

只有一种暖色在说话，其余都是墙。

### Primary

- **灯芯橘 Lamp Amber** (#FEAE36): 唯一的实心强调色。主按钮底、首页 hero 的星芒、体重折线与数据点、Tab 选中图标与文字、健康分强调。它永远是被照亮的面，不是笔。
- **压下的灯芯 Amber Pressed** (#EE941D): 主按钮按下态。只降明度，不加阴影。
- **余烬橙 Ember Glow** (#FF9F24): 变量集合里的第二档强调，用于需要比主色更沉一点的橙。未大面积使用时保持留白。

### Secondary

- **焦糖字 Burnt Caramel** (#A34400): 除正文墨色外的「可点击 / 可推进」文字与图标：次级按钮文字、卡片 action、Tab 选中图标、返回箭头。它在纸白上 6.21:1、在亚麻上 5.86:1，是唯一能安全承载「橘色语感」的文字色。
- **蜜水洗 Honey Wash** (#FFF0DF): 次级强调底。次级按钮、说明块、选中 chip、返回按钮底盘、AI 免责声明卡。它是「橘色的余温」。
- **晨光蜜桃 Hero Peach** (#FFEDD7): 首页 hero 卡底。整块暖光区域只此一处，不与其它暖底同屏堆叠。
- **对话蜜桃 Bubble Peach** (#FFE2B6): 用户发言气泡底。比 hero 更饱和，因为它在对话里代表「你说的话」，需要被一眼区分。
- **星火 Spark Ember** (#ED7413): hero 的 ✦ 装饰与极少量点缀。单点使用，不成片。

### Tertiary — 状态色

- **红线红 Redline Red** (#B42318) ／ 底 **Redline Wash** (#FFF1F0): 仅「立即就医」路径。危险卡、危险 CTA、danger 态 pill。纸白上 6.57:1。
- **稳妥绿 Steady Green** (#166534) ／ 底 **Steady Wash** (#EDF8EE): normal 状态。6.54:1。
- **留意赭 Watch Umber** (#8A4B00) ／ 底 **Watch Wash** (#FFF4D8): observe 状态。6.21:1。
- **焦点蓝 Focus Azure** (#315CBE): 系统里唯一的冷色，只做键盘 / 网页焦点环。

### Neutral

- **纸白 Canvas White** (#FFFFFF): 页面底与 Tab 栏底。空的地方要真空。
- **亚麻卡 Linen Card** (#FAF8F6): 卡片、列表行、输入框、「抬起来的一点」——因为不能用阴影，这层色就是「浮起」。
- **可可墨 Cocoa Ink** (#4B2617): 橘底上的字、hero 标题、页面大标题。亚麻上 12.48:1。
- **树皮墨 Bark Ink** (#743A10): 正文与卡片标题。纸白上 8.92:1。
- **陶土灰 Clay Gray** (#805535): 次级文字、说明、时间、未选中 Tab。亚麻上 6.06:1。
- **沙边 Sand Edge** (#D9BFA5) ／ **深沙边 Sand Edge Strong** (#89552F): 描边与分隔线。默认用 hairlineWidth，不用固定 1px。
- **雾白药丸 Mist Pill** (#F3EEE9): 中性 pill 底，比蜜水更灰一点，用于「没有情绪」的标签。
- **褪色小鹿 Muted Fawn** (#C6A894) ／ **箭角 Fawn Chevron** (#B59B88) ／ **旧时标 Fawn Timestamp** (#A78976): 装饰性图标、› 箭头、旧时间戳。对比度 2.10–3.24:1，只做提示，不承载信息。
- **停用沙 Disabled Sand** (#E9DED2) ／ **停用陶 Disabled Clay** (#796B60): 停用态。禁用文字 3.88:1，属于可接受的低强调。

### Named Rules

**The Lamp Is Not Ink Rule.** 橘色 #FEAE36 永不作为纸白或亚麻底上的文字与小图标颜色（对比度仅 1.85:1）。它只做填充、选中态与描边；橘底上的文字一律用可可墨 #4B2617（7.13:1）。

**The One Lamp Rule.** 任意视口只允许一个橘色填充的主行动面。第二个想被强调的东西降级为蜜水底 #FFF0DF 或亚麻卡片，不得再加一盏灯。

**The Redline Red Rule.** #B42318 只出现在「立即就医」路径上：危险卡片、危险 CTA、状态 pill 的 danger 态。它永远配 #FFF1F0 底色与「!」符号出现，不做装饰色，不做 hover 色。

## Typography

**Display Font:** PingFang SC（iOS 自动落字体）／ 系统 sans（Android）
**Body Font:** 同族，仅用字重与字号分层
**Label/Mono Font:** 无独立标签字族；数字与标签同用系统中文字体

**Character:** 系统字是中文用户手里「不会错」的默认，绒星不试图用字体表达个性。层级全部由字重（400 / 500 / 600）与字号（12 → 25）承担，行高宽松，零字距——读起来像一张印得松快的说明卡，而不是报表。

### Hierarchy

- **Display** (600, 25/35): hero 问候语与 Card 标题。一屏至多一次。
- **Headline** (600, 24/32): 页面标题（typography.pageTitle）。「我的」「健康」「初筛结果」等页头。
- **Title** (600, 20/28): 区块标题（typography.sectionTitle）、健康分数、合计值。
- **Subtitle** (600, 18/26): 强调行、卡内小标题（typography.emphasis）、空态标题。
- **Body** (400, 16/24): 正文、按钮文字、输入文字。移动端单行不超过约 22 个汉字。
- **Caption** (400, 14/21): 说明、时间、次级按钮文字、状态 pill 文字。
- **Label** (500, 12/18): 字段名、Tab 未选中文字、极小元信息（Tab 文字实为 11px，属于该档的移动端收口）。

### Named Rules

**The Weight-Only Hierarchy Rule.** 层级只用 400 / 500 / 600。700 只残留在尚未回归规范的详情页（初筛结果、提醒、饮食、喂食、体重、时间线），新代码一律不得新增 700。

**The Airy Leading Rule.** 行高不低于字号的 1.33 倍（实测区间 1.33–1.5，如 25/35、24/32、16/24、12/18）。中文不靠压缩行距换取「信息量」。

**The No Tracking Rule.** 全仓没有一处 letterSpacing 声明，中文永远零字距。需要强调时改字重或改字号，不加字距、不做全大写。

## Layout

390×844 为画板基准，左右边距 16px。所有页面过 Screen：顶部安全区 + 纵向滚动，内容容器 maxWidth 560、alignSelf center、padding 16、paddingBottom 32、子元素间距 12。560 是「再宽就不好读」的界线，超过它只加留白，不加栏。

纵向节奏靠卡与卡之间的 12px 缝，卡内靠 16–24px 内距。Tab 栏固定在底部：paddingTop 12、paddingBottom max(insets.bottom, 10)、图标 24、文字 11、四项等分。首页 hero 卡 minHeight 195、左 16 右 45（右 45 是给分身舞台留的呼吸位），内部并列「左文案 / 右分身」。

密度：一屏一到两个信息块。健康页允许 4 个指标块 2×2 并排（各 r16、minHeight 94），但仍是单列结构里的一行。

### Named Rules

**The Single Column Rule.** 内容永远是单列。宽度超过 560px 时容器居中、两侧留白，不做双栏、不做侧边栏。卡内可以两列并排（首页指标块 minHeight 94），但页面结构不分栏。

## Elevation & Depth

**这个系统没有阴影。** 全仓 shadowOpacity / shadowRadius / elevation / boxShadow 命中数为 0，也没有渐变与毛玻璃。深度不靠投射，靠换色：纸白（画布）→ 亚麻（卡片 / 行 / 输入）→ 蜜水（次级强调）→ 灯芯橘（主行动）。四层色阶就是四层高度；想要「更近」，换更暖更饱和的底，而不是加深投影。

按压反馈也只降不浮：opacity 0.85（卡片、列表行）、0.65（气泡内操作）、0.45–0.6（次级文字按钮、图标按钮），不位移、不缩放。唯一的动效语言是分身舞台的 300ms 淡入淡出与 1200ms 呼吸缩放（1.00 ↔ 1.03），且只属于分身，不属于界面。

### Shadow Vocabulary

无。extensions.shadows 为空数组，这是这套系统的身份声明，不是待补项。

### Named Rules

**The Tonal Instead Of Shadow Rule.** 不使用任何投影表达层级。四层色阶即四层深度：纸白 #FFFFFF（画布）→ 亚麻 #FAF8F6（卡片、行、输入）→ 蜜水 #FFF0DF（次级强调、说明块）→ 灯芯橘 #FEAE36（唯一主行动）。

**The Press-Only Rule.** 状态反馈只降低透明度，不位移、不缩放、不浮起。卡片与列表行 0.85，气泡与次级按钮 0.65，弱操作 0.45–0.6。

## Shapes

形状语言是「圆润的容器」：容器越大，圆角越大。按钮 h48/r24 是标准胶囊；卡片、指标块、hero 卡 r20；列表行、入口行、快捷入口 r16；表单输入（h56）、chip（h40）r12；小标记 r8；pill 用 999。圆形一律取高度一半：状态 pill h42→r21、返回键 38×38→r19、气泡操作键 44×44→r22。

描边只做「边界」不做「装饰」：表单输入、chip、分隔线用 hairlineWidth 的 colors.border，选中态 chip 用 1px colors.brand。危险态换底不换边（dangerBg + danger 字），危险 chip 才加 1px danger 边。

实测圆角分布（mobile/src/**/*.tsx）：12px×27、16px×14、20px×13、18px×9、14px×9、22px×3、21px×3、24px×2、32px×2，其余为个位数——12/16/20 是主干，14/18/22/27/32 是旧页面的手工值，新代码只落刻度。

### Named Rules

**The Rounded Container Rule.** 圆角随容器规模增长，且必须落在刻度上：h48 的按钮 r24、卡片 r20、列表行 r16、表单输入与 chip r12、小标记 r8。胶囊与圆形一律取高度的一半（h42 → r21，38×38 → r19，44×44 → r22）。

**The Keyboard-Only Ring Rule.** 触屏不画焦点环；键盘与网页焦点用 #315CBE 2px 外描边（offset 2px）。这是系统里唯一的蓝色，只出现在焦点上。

## Components

### Buttons

- **Shape:** 标准胶囊（h48、r24、左右 24 内距），文字 16/w600，busy 时内联 ActivityIndicator 替换文字。
- **Primary:** 底 colors.brand #FEAE36，字 colors.onBrand #4B2617；按下换 colors.brandPressed #EE941D。
- **Secondary:** 底 colors.brandSoft #FFF0DF，字 colors.accent #A34400；按下为一次性硬编码 #F5E3CB（系统里唯一的例外值，见 Don’ts）。
- **Disabled:** 底 colors.disabledBg #E9DED2，字 colors.disabledText #796B60，不降透明度。
- **危险 CTA:** 仅出现在红线路径，底 colors.danger #B42318、白字、r24、minHeight 48。
- **Focus:** 触屏不画环；键盘 / 网页焦点 #315CBE 2px 外描边。

### Chips

- **Style:** h40（表单页 h44）、r12、1px colors.border 边、底 colors.canvas-white，文字 14 colors.text。
- **State:** 选中底换 colors.brandSoft 并加 1px colors.brand 边；危险 chip 底 colors.dangerBg、边与字为 colors.danger。chip 是筛选取值，不是按钮，不做实心橘。

### Cards / Containers

- **Corner Style:** r20（radius.lg），hero 卡 r22，指标块 r16。
- **Background:** 一律 colors.surfaceRaised #FAF8F6；urgent 时整卡换 colors.dangerBg #FFF1F0。
- **Shadow Strategy:** 无（见 Elevation & Depth）。
- **Border:** 无。危险卡靠底色与文字色识别。
- **Internal Padding:** Card 组件 24、gap 8；页面内联卡 16；列表卡左右 14。
- **Interaction:** 可点卡片按下 opacity 0.85；Card 的 action 是 colors.accent 的 16/w600 文字加三个空格与箭头。

### Inputs / Fields

- **Style:** h56、r16、无边框、底 colors.linen-card、左右 20、文字 16 colors.text、占位符 colors.disabledText。
- **Focus:** RN 内无内建视觉态；键盘 / 网页用 2px #315CBE 外描边（reserved token）。
- **Error / Disabled:** 错误用 colors.danger 文案 + dangerBg 提示块，输入框本身不变红；停用用 disabledBg 底 + disabledText 字。

### Navigation

- **底部 Tab:** 白底（colors.background），paddingTop 12、paddingBottom max(insets.bottom, 10)；四项 flex 等分，图标 24 + 文字 11，选中 colors.accent w600、未选中 colors.secondary w400。iOS 26+ 走 NativeTabs（SF Symbols，tintColor = colors.accent，minimizeBehavior=never），Android / web 用自绘 DesignTabBar——机制不同，视觉同一套。
- **页头:** 详情页 24/w600 colors.onBrand 标题 + 38×38 圆形返回键（底 colors.brandSoft，图标 colors.accent），无导航栏阴影、无分隔线。
- **列表入口:** EntryRow —— 亚麻底、r16、左右与上下 14、图标 22、标题 15/w600、副标题 12、右侧 › 25px colors.chevron。

### Signature: 健康状态卡 Health Card

首页的心脏。r20、内距 16/15/14、底 colors.surfaceRaised；左侧分数 25/35 w600（未评估时显示两个长横并降为次级色），右侧状态 pill（minHeight 26、r13、底与字取状态色）；下方一行提示语，再下方可展开「扣分明细（n 项）」。urgent 时整张卡底换 colors.dangerBg、分数转 colors.danger，并在卡下追加 colors.danger 实心「立即就医」CTA。状态映射：normal→success、observe→warning、vet / urgent→danger。

### Signature: 分身舞台 Avatar Stage

首页 hero 右侧、宽 54% 且 maxWidth 160 的正方形舞台：静态底图 + 循环动作（≤5s、≤3MB、480p），无分身时以静态首帧兜底。它上面没有边框、没有阴影、没有圆角遮罩——图片直接坐在 hero 的蜜桃底上，靠底图与底色过渡。动作切换 300ms 淡入淡出，待机 1200ms 呼吸缩放 1.00→1.03。

### Signature: 对话气泡 Chat Bubbles

用户发言在右，底 colors.assistantBubble #FFE2B6（比 hero 更饱和）；宠物侧在左，底 colors.surfaceRaised，带 24px 圆形猫头像。气泡 r16、内距 14/10，列宽上限 78%。输入条是 r27 的全胶囊，1px colors.border 边、底 colors.surfaceRaised、内距 5，左侧语音键与右侧发送键均 44×44 r22（发送底 colors.brand）。AI 免责声明用 colors.brandSoft 底 r14，医疗引导用 colors.dangerBg 底 r16——两者都不加图标库图标，只用文字与已有 stroke icon。

## Do’s and Don’ts

### Do:

- **Do** 用 colors.brand（#FEAE36）做填充，用 colors.onBrand（#4B2617）做它上面的字，保持 7.13:1 的对比。
- **Do** 让每个状态同时具备底色、同色系深字与符号：success ✓、warning !、danger !、neutral •。色盲用户靠符号与位置也能读懂。
- **Do** 把新容器套进既有圆角刻度：h48/r24、卡片 r20、列表行 r16、输入与 chip r12、标记 r8；胶囊取高度一半。
- **Do** 用 spacing 的 4/8/12/16/20/24/32/40 落位，页面留白优先于塞入内容。
- **Do** 复用 mobile/src/components/ui/ 里的 Button / Card / EntryRow / StatusPill / TextField / SectionHeader 与 theme.ts 的键；页面不重新发明基础件。
- **Do** 用 24px、圆头圆角、描边统一的 icons.ts 图标，Icon 默认色 colors.accent。
- **Do** 给图标按钮留 ≥44×44 的触控面（返回键 38×38 时补 hitSlop），文字按钮补 hitSlop 8。
- **Do** 让插画与照片落在亚麻或蜜水底上（hero 卡 #FFEDD7，r22），图片本身不加描边、不加阴影。

### Don’t:

- **Don’t** 把 #FEAE36 用在文字或 1px 线上——它只在纸白上 1.85:1、在亚麻上 1.76:1，读不清。
- **Don’t** 引入投影、elevation、渐变、毛玻璃或任何「浮起」效果：全仓目前 0 命中，这是系统身份，不是缺失。
- **Don’t** 把危险红 #B42318 用成强调色或促销色；它属于「立即就医」这一条路径。
- **Don’t** 新增 fontWeight 700，也不要用 letterSpacing 或全大写中文做强调。
- **Don’t** 用冷色（蓝、青、医院白）做安抚：焦点蓝 #315CBE 仅限键盘焦点环。
- **Don’t** 在同一个视口放两个橘色实心按钮，也不要在橘色上再叠一层橘色卡片。
- **Don’t** 把圆角随手写成 14/18/22/27/32 这类一次性数值；它们存在于旧页面（14×9、18×9、22×3、27×1、32×2），但不是刻度。
- **Don’t** 依赖 colors.mutedIcon（#C6A894，2.10:1）或 colors.chevron（2.48:1）传递信息——它们只做装饰性提示。
- **Don’t** 上线来路不明的图片素材；hero 图 mobile/assets/figma/59f10c90466cfa3aa84c0f88478dccedc8f69565.png 的授权仍未确认（原 `DESIGN_REVIEW.md` 已归档删除，需重新向素材方确认）。

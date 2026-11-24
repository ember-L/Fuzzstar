/* 绒星 · 运营管理台
   页面结构、视图与交互。数据来自 /api/v1/admin/*，登录复用 App 的账号体系。 */

import { adminApi, ApiError, hasSession } from './api.js';
import { lineChart, donut, sparkline, barSvg, dot, CHART_COLORS } from './charts.js';

/* ------------------------------------------------------------------ */
/* 常量与图标                                                          */

const ROUTES = {
  overview: { title: '运营总览', sub: '用户、猫咪、健康初筛与 AI 成本的全貌' },
  users: { title: '用户管理', sub: '查找账号、查看健康档案与停用 / 恢复账号' },
  pets: { title: '猫咪档案', sub: '全部猫咪档案、主人与最新体重' },
  screenings: { title: '健康初筛', sub: '按状态与红线筛选，核对规则分级的实际分布' },
  usage: { title: 'AI 与成本', sub: '模型调用、tokens、估算成本与后台任务健康度' },
  audit: { title: '审计日志', sub: '管理员的每一次写操作都有记录' },
};

const NAV = [
  { route: 'overview', label: '运营总览', icon: 'overview' },
  { route: 'users', label: '用户管理', icon: 'users' },
  { route: 'pets', label: '猫咪档案', icon: 'paw' },
  { route: 'screenings', label: '健康初筛', icon: 'pulse' },
  { route: 'usage', label: 'AI 与成本', icon: 'spark' },
  { route: 'audit', label: '审计日志', icon: 'list' },
];

const SCREENING_STATES = {
  normal: { label: '正常', cls: 'success', symbol: '✓', color: CHART_COLORS.success },
  observe: { label: '观察', cls: 'warning', symbol: '!', color: CHART_COLORS.warning },
  vet: { label: '就医', cls: 'danger', symbol: '!', color: CHART_COLORS.danger },
  urgent: { label: '急诊', cls: 'danger', symbol: '!', color: CHART_COLORS.danger },
};

const USER_STATUS = {
  active: { label: '正常', cls: 'success', symbol: '✓' },
  suspended: { label: '已停用', cls: 'warning', symbol: '!' },
  deletion_pending: { label: '注销中', cls: 'neutral', symbol: '•' },
  deleted: { label: '已删除', cls: 'mist', symbol: '•' },
};

const PET_STATUS = {
  active: { label: '在册', cls: 'success', symbol: '✓' },
  deleted: { label: '已删除', cls: 'mist', symbol: '•' },
};

const QUOTA_LABELS = { screening: '健康初筛', avatar_gen: '分身生成', chat_msg: '陪伴聊天' };
const TASK_LABELS = {
  avatar_batch: '分身生成', gif_export: 'GIF 导出', screening_advice: '初筛建议',
  audio_interpret: '叫声解读', motion_batch: '萌宠动图',
};
const AI_KIND_LABELS = { llm: '文本建议', chat: '陪伴聊天', audio: '叫声解读', image: '图像生成', video: '视频生成' };

const ICONS = {
  overview: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.8"/>',
  users: '<path d="M15.5 19v-1.4a3.6 3.6 0 0 0-3.6-3.6H7.1a3.6 3.6 0 0 0-3.6 3.6V19"/><circle cx="9.5" cy="8" r="3.2"/><path d="M16.5 11.2a3 3 0 0 0 0-6"/><path d="M20.5 19v-1.4a3.6 3.6 0 0 0-2.7-3.5"/>',
  paw: '<circle cx="7" cy="8" r="1.6"/><circle cx="12" cy="6.3" r="1.6"/><circle cx="17" cy="8" r="1.6"/><path d="M12 10.8c2.6 0 4.6 1.8 4.6 4.1 0 1.9-1.9 2.9-4.6 2.9s-4.6-1-4.6-2.9c0-2.3 2-4.1 4.6-4.1z"/>',
  pulse: '<path d="M3 12h3.6l2-5.2L12.5 17l2.2-5H21"/>',
  spark: '<path d="M12 3.2l1.9 5.2 5.2 1.9-5.2 1.9L12 17.4l-1.9-5.2L4.9 10.3l5.2-1.9z"/>',
  list: '<rect x="4.5" y="3.5" width="15" height="17" rx="2.4"/><path d="M8.2 8h7.6M8.2 12h7.6M8.2 16h4.8"/>',
  refresh: '<path d="M20 11.2A8 8 0 1 0 17.7 17"/><path d="M20 4.5V11h-6.5"/>',
  search: '<circle cx="11" cy="11" r="6.2"/><path d="M19.5 19.5L15.6 15.6"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  chevronRight: '<path d="M9 5l7 7-7 7"/>',
  chevronLeft: '<path d="M15 5l-7 7 7 7"/>',
  logout: '<path d="M10 5H6.5A2.5 2.5 0 0 0 4 7.5v9A2.5 2.5 0 0 0 6.5 19H10"/><path d="M15 8l4 4-4 4"/><path d="M19 12H9"/>',
  alert: '<path d="M12 4.5L21 19H3z"/><path d="M12 9.5v4M12 16.5v.2"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  lock: '<rect x="5" y="10.5" width="14" height="9.5" rx="2.4"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
  arrowUp: '<path d="M12 19V5M6.5 10.5L12 5l5.5 5.5"/>',
  info: '<circle cx="12" cy="12" r="8.2"/><path d="M12 11v5M12 8v.2"/>',
};

function icon(name, size = 18, stroke = 1.8) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
}

/* ------------------------------------------------------------------ */
/* 小工具                                                              */

const numberFormat = new Intl.NumberFormat('zh-CN');
const dateFormat = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
const dateTimeFormat = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
});

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

function fmtInt(value) {
  return numberFormat.format(Number(value) || 0);
}

function fmtPct(value, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return `${(number * 100).toFixed(digits)}%`;
}

function fmtCost(value) {
  const number = Number(value) || 0;
  if (number === 0) return '¥0';
  if (number < 0.01) return `¥${number.toFixed(4)}`;
  if (number < 1) return `¥${number.toFixed(3)}`;
  return `¥${number.toFixed(2)}`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : dateFormat.format(date);
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : dateTimeFormat.format(date);
}

function fmtRelative(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 0) return fmtDateTime(iso);
  if (seconds < 60) return '刚刚';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)} 天前`;
  return fmtDate(iso);
}

function fmtAge(birthDate) {
  if (!birthDate) return '生日未填';
  const birth = new Date(`${birthDate}T00:00:00`);
  if (Number.isNaN(birth.getTime())) return '生日未填';
  const now = new Date();
  let months = (now.getFullYear() - birth.getFullYear()) * 12 + (now.getMonth() - birth.getMonth());
  if (now.getDate() < birth.getDate()) months -= 1;
  if (months < 0) return '生日未填';
  if (months < 12) return `${months} 个月`;
  return `${Math.floor(months / 12)} 岁`;
}

function sexLabel(sex) {
  return { male: '公猫', female: '母猫', unknown: '性别未知' }[sex] || '性别未知';
}

function screeningState(state) {
  return SCREENING_STATES[state] || { label: state || '未知', cls: 'neutral', symbol: '•', color: CHART_COLORS.timestamp };
}

function pill(label, cls = 'neutral', symbol = '') {
  return `<span class="pill pill--${cls}">${symbol ? `<span class="pill-symbol" aria-hidden="true">${symbol}</span>` : ''}${esc(label)}</span>`;
}

function userStatusPill(status) {
  const meta = USER_STATUS[status] || { label: status, cls: 'mist', symbol: '•' };
  return pill(meta.label, meta.cls, meta.symbol);
}

function petStatusPill(status) {
  const meta = PET_STATUS[status] || { label: status, cls: 'mist', symbol: '•' };
  return pill(meta.label, meta.cls, meta.symbol);
}

function statePill(state) {
  const meta = screeningState(state);
  return pill(meta.label, meta.cls, meta.symbol);
}

function emptyBlock(title, sub = '') {
  return `<div class="empty"><div class="empty-mark" aria-hidden="true">✦</div><p class="empty-title">${esc(title)}</p>${sub ? `<p class="empty-sub">${esc(sub)}</p>` : ''}</div>`;
}

function inlineError(error) {
  const message = error instanceof ApiError ? error.message : '加载失败，请稍后重试';
  return `<div class="empty"><div class="empty-mark" aria-hidden="true">!</div><p class="empty-title">没有取到数据</p><p class="empty-sub">${esc(message)}</p><button class="btn btn-secondary btn-sm" type="button" data-action="retry">重新加载</button></div>`;
}

function errorCard(error) {
  const message = error instanceof ApiError ? error.message : '加载失败，请稍后重试';
  return `<section class="card"><div class="error-card"><h2>没有取到数据</h2><p>${esc(message)}</p><button class="btn btn-secondary btn-sm" type="button" data-action="retry">重新加载</button></div></section>`;
}

function tableSkeleton(rows = 6) {
  return `<div class="skeleton-table">${Array.from({ length: rows }, () => `
    <div class="skeleton-row">
      <div class="skeleton skeleton-line"></div>
      <div class="skeleton skeleton-line"></div>
      <div class="skeleton skeleton-line"></div>
      <div class="skeleton skeleton-line"></div>
    </div>`).join('')}</div>`;
}

function pageSkeleton() {
  return `<div class="kpi-grid">${Array.from({ length: 4 }, () => '<div class="skeleton skeleton-kpi"></div>').join('')}</div>
    <div class="dash-grid"><div class="skeleton skeleton-chart"></div><div class="skeleton skeleton-chart"></div></div>`;
}

function toast(message, tone = 'success') {
  const stack = document.getElementById('toast-stack');
  if (!stack) return;
  const symbols = { success: '✓', danger: '!', warning: '!', info: 'i' };
  const element = document.createElement('div');
  element.className = `toast toast--${tone}`;
  element.setAttribute('role', tone === 'danger' ? 'alert' : 'status');
  element.innerHTML = `<span class="toast-icon" aria-hidden="true">${symbols[tone] || '✓'}</span><span class="toast-text">${esc(message)}</span>`;
  stack.append(element);
  window.setTimeout(() => element.remove(), 3800);
}

/* ------------------------------------------------------------------ */
/* 全局状态                                                            */

const state = {
  session: null,
  route: 'overview',
  renderSeq: 0,
  overviewDays: 30,
  usageDays: 30,
  users: { query: '', status: 'all', page: 1, seq: 0 },
  pets: { query: '', status: 'all', page: 1, seq: 0 },
  screenings: { query: '', state: 'all', redline: 'all', page: 1, seq: 0 },
  audit: { page: 1, seq: 0 },
  drawerKey: null,
};

function currentRoute() {
  const hash = location.hash.replace(/^#\/?/, '').split('?')[0];
  return ROUTES[hash] ? hash : 'overview';
}

/* ------------------------------------------------------------------ */
/* 启动 / 登录                                                         */

async function boot() {
  if (!hasSession()) {
    renderLogin();
    return;
  }
  try {
    state.session = await adminApi.session();
    renderShell();
    await renderRoute();
  } catch (error) {
    if (error.status === 401) {
      adminApi.logout();
      renderLogin('登录已过期，请重新登录。');
    } else if (error.status === 403) {
      adminApi.logout();
      renderLogin('该账号没有管理员权限，请使用 ADMIN_EMAILS 中配置的账号。');
    } else if (error.status === 503) {
      renderConfig();
    } else {
      renderFatal(error);
    }
  }
}

function loginErrorMessage(error) {
  if (!(error instanceof ApiError)) return '登录失败，请稍后重试。';
  if (error.code === 'EMAIL_UNVERIFIED') return '这个邮箱还没验证，请先在 App 内完成邮箱验证。';
  if (error.status === 401) return '邮箱或密码不正确。';
  if (error.status === 403 || error.code === 'ADMIN_REQUIRED') {
    return '该账号不在 ADMIN_EMAILS 中，没有管理权限。';
  }
  if (error.status === 429) return '请求过于频繁，请一分钟后再试。';
  return error.message;
}

function renderLogin(message = '', email = '') {
  state.session = null;
  document.title = '登录 · 绒星运营管理台';
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="login">
      <div class="login-orb login-orb--peach" aria-hidden="true"></div>
      <div class="login-orb login-orb--honey" aria-hidden="true"></div>
      <span class="login-orb login-orb--dot" aria-hidden="true"></span>
      <span class="login-orb login-orb--dot2" aria-hidden="true"></span>
      <div class="login-content">
        <section class="login-panel" aria-labelledby="login-title">
          <div class="login-brand">
            <img class="brand-mark" src="/admin/assets/logo.png" alt="" aria-hidden="true">
            <div>
              <div class="login-brand-name">绒星</div>
              <div class="login-brand-sub">RongXing Operations</div>
            </div>
          </div>
          <span class="login-eyebrow">${icon('lock', 13)} 管理员入口</span>
          <h1 id="login-title">运营管理台</h1>
          <p class="login-lede">登录后查看用户与猫咪档案、健康初筛分布、AI 调用成本，并对账号做停用与恢复。</p>
          ${message ? `<div class="form-error form-error--spaced" role="alert">${icon('alert', 16)}<span>${esc(message)}</span></div>` : ''}
          <form id="login-form" class="login-form" novalidate>
            <div class="field">
              <label for="login-email">管理员邮箱</label>
              <input id="login-email" name="email" type="email" inputmode="email" autocomplete="username"
                placeholder="you@example.com" value="${esc(email)}" required>
            </div>
            <div class="field">
              <label for="login-password">密码</label>
              <input id="login-password" name="password" type="password" autocomplete="current-password"
                placeholder="至少 8 位，含字母和数字" required>
            </div>
            <button id="login-submit" class="btn btn-primary login-submit" type="submit">进入管理台</button>
          </form>
          <p class="login-hint">管理员权限由后端 <strong>ADMIN_EMAILS</strong> 控制：账号需先完成邮箱验证，再重启 API 生效。管理操作会写入审计日志。</p>
        </section>
        <p class="login-foot">绒星 RongXing · 星光护绒，健康相伴</p>
      </div>
    </div>`;
  document.getElementById('login-form').addEventListener('submit', submitLogin);
  const emailInput = document.getElementById('login-email');
  if (!email) emailInput.focus();
}

async function submitLogin(event) {
  event.preventDefault();
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  if (!email || !password) {
    renderLogin('请输入管理员邮箱和密码。', email);
    return;
  }
  const button = document.getElementById('login-submit');
  button.disabled = true;
  button.textContent = '正在登录…';
  try {
    await adminApi.login(email, password);
    state.session = await adminApi.session();
    history.replaceState(null, '', '#/overview');
    renderShell();
    await renderRoute();
  } catch (error) {
    adminApi.logout();
    if (error.status === 503) {
      renderConfig();
      return;
    }
    renderLogin(loginErrorMessage(error), email);
  }
}

function renderConfig() {
  document.title = '待配置 · 绒星运营管理台';
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="login">
      <div class="login-orb login-orb--peach" aria-hidden="true"></div>
      <div class="login-orb login-orb--honey" aria-hidden="true"></div>
      <div class="login-content">
        <section class="login-panel" aria-labelledby="config-title">
          <div class="login-brand">
            <img class="brand-mark" src="/admin/assets/logo.png" alt="" aria-hidden="true">
            <div><div class="login-brand-name">绒星</div><div class="login-brand-sub">RongXing Operations</div></div>
          </div>
          <span class="login-eyebrow">${icon('alert', 13)} 还差一步</span>
          <h1 id="config-title">配置管理员邮箱</h1>
          <p class="login-lede">后台已经就绪，但还没有指定谁能进入。在 <strong>backend/.env</strong> 中新增一行，然后重启 API：</p>
          <pre class="code-block code-block--spaced">ADMIN_EMAILS=ops@example.com,owner@example.com</pre>
          <p class="login-hint">只填已经注册并完成邮箱验证的账号；多个邮箱用英文逗号分隔。未配置时后台 API 会返回 503，配置后重新登录即可。</p>
          <button class="btn btn-secondary mt-18" type="button" data-action="retry-boot">我已配置，重新检查</button>
        </section>
        <p class="login-foot">绒星 RongXing · 星光护绒，健康相伴</p>
      </div>
    </div>`;
}

function renderFatal(error) {
  const app = document.getElementById('app');
  document.title = '连接失败 · 绒星运营管理台';
  app.innerHTML = `
    <div class="login">
      <div class="login-content">
        <section class="login-panel">
          <div class="login-brand"><img class="brand-mark" src="/admin/assets/logo.png" alt="" aria-hidden="true">
            <div><div class="login-brand-name">绒星</div><div class="login-brand-sub">RongXing Operations</div></div></div>
          <h1>暂时连不上运营数据</h1>
          <p class="login-lede">${esc(error instanceof ApiError ? error.message : '请确认后端已经启动。')}</p>
          <button class="btn btn-primary mt-20" type="button" data-action="retry-boot">重试连接</button>
        </section>
        <p class="login-foot">绒星 RongXing · 星光护绒，健康相伴</p>
      </div>
    </div>`;
}

/* ------------------------------------------------------------------ */
/* 外壳                                                                */

function renderShell() {
  const admin = state.session.admin;
  const initial = (admin.nickname || admin.email || '管').slice(0, 1);
  document.getElementById('app').innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <a class="sidebar-brand" href="#/overview" aria-label="绒星运营管理台首页">
          <img class="brand-mark" src="/admin/assets/logo.png" alt="" aria-hidden="true">
          <span class="brand-text">
            <span class="brand-name">绒星</span>
            <span class="brand-caption">运营管理台</span>
          </span>
        </a>
        <nav class="nav" aria-label="主导航">
          <span class="nav-label">运营</span>
          ${NAV.map((item) => `
            <a class="nav-item" href="#/${item.route}" data-nav="${item.route}">
              ${icon(item.icon, 19)}<span>${item.label}</span>
            </a>`).join('')}
        </nav>
        <div class="sidebar-foot">
          <div class="admin-id">
            <span class="admin-avatar" aria-hidden="true">${esc(initial)}</span>
            <div class="admin-meta">
              <div class="admin-name">${esc(admin.nickname)}</div>
              <div class="admin-mail">${esc(admin.email || '')}</div>
            </div>
          </div>
          <button class="sidebar-logout" type="button" data-action="logout">
            ${icon('logout', 17)}<span>退出登录</span>
          </button>
        </div>
      </aside>
      <div class="main">
        <header class="topbar">
          <div>
            <h1 id="page-title">运营总览</h1>
            <p class="topbar-sub" id="page-sub"></p>
          </div>
          <div class="topbar-actions" id="topbar-actions"></div>
        </header>
        <main class="content" id="content"></main>
        <div class="page-foot">数据按北京时间自然日聚合 · 管理操作会写入审计日志 · 绒星 RongXing</div>
      </div>
    </div>`;
  setActiveNav(state.route);
}

function setActiveNav(route) {
  document.querySelectorAll('[data-nav]').forEach((link) => {
    const active = link.dataset.nav === route;
    link.classList.toggle('is-active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

function refreshButton() {
  return `<button class="btn btn-secondary btn-sm" type="button" data-action="refresh">${icon('refresh', 15)}刷新数据</button>`;
}

function rangeGroup(kind, current) {
  return `<div class="range-group" role="group" aria-label="时间范围">
    ${[7, 14, 30, 90].map((days) => `<button class="chip" type="button" data-range="${kind}" data-days="${days}" aria-pressed="${days === current}">${days} 天</button>`).join('')}
  </div>`;
}

function setTopbar(route) {
  const actions = document.getElementById('topbar-actions');
  if (route === 'overview') actions.innerHTML = rangeGroup('overview', state.overviewDays) + refreshButton();
  else if (route === 'usage') actions.innerHTML = rangeGroup('usage', state.usageDays) + refreshButton();
  else actions.innerHTML = refreshButton();
}

async function renderRoute() {
  if (!state.session) return;
  closeDrawer();
  closeModal();
  // Invalidate any in-flight list request from the previous route.
  state.users.seq += 1;
  state.pets.seq += 1;
  state.screenings.seq += 1;
  state.audit.seq += 1;
  const route = currentRoute();
  state.route = route;
  const meta = ROUTES[route];
  document.getElementById('page-title').textContent = meta.title;
  document.getElementById('page-sub').textContent = meta.sub;
  document.title = `${meta.title} · 绒星运营管理台`;
  setActiveNav(route);
  setTopbar(route);
  const seq = ++state.renderSeq;
  if (route === 'overview') await viewOverview(seq);
  else if (route === 'users') viewUsers();
  else if (route === 'pets') viewPets();
  else if (route === 'screenings') viewScreenings();
  else if (route === 'usage') await viewUsage(seq);
  else if (route === 'audit') viewAudit();
}

/* ------------------------------------------------------------------ */
/* 总览                                                                */

function kpiCard({ label, iconName, value, foot = '', spark = '', accent = false }) {
  return `<article class="kpi-card${accent ? ' kpi-card--accent' : ''}">
    <div class="kpi-label">${icon(iconName, 15)}<span>${esc(label)}</span></div>
    <div class="kpi-value">${value}</div>
    ${spark ? `<div class="kpi-spark" aria-hidden="true">${spark}</div>` : ''}
    <div class="kpi-foot">${foot}</div>
  </article>`;
}

async function viewOverview(seq) {
  const content = document.getElementById('content');
  content.innerHTML = pageSkeleton();
  try {
    const data = await adminApi.overview(state.overviewDays);
    if (seq !== state.renderSeq) return;
    content.innerHTML = overviewHtml(data);
  } catch (error) {
    if (seq !== state.renderSeq) return;
    content.innerHTML = errorCard(error);
  }
}

function overviewHtml(data) {
  const kpis = data.kpis;
  const series = data.series;
  const days = data.window.days;
  const activeShare = kpis.users_total ? kpis.users_active / kpis.users_total : 0;
  const stateItems = [
    { name: '正常', value: (data.states.find((item) => item.state === 'normal') || {}).count || 0, color: SCREENING_STATES.normal.color },
    { name: '观察', value: (data.states.find((item) => item.state === 'observe') || {}).count || 0, color: SCREENING_STATES.observe.color },
    {
      name: '需就医',
      value: (data.states.find((item) => item.state === 'vet') || {}).count
        + (data.states.find((item) => item.state === 'urgent') || {}).count,
      color: SCREENING_STATES.vet.color,
    },
  ];
  const screeningTotal = stateItems.reduce((sum, item) => sum + item.value, 0);
  const vet = (data.states.find((item) => item.state === 'vet') || {}).count || 0;
  const urgent = (data.states.find((item) => item.state === 'urgent') || {}).count || 0;

  return `
    ${alertsHtml(data.alerts)}
    <section class="kpi-grid" aria-label="核心指标">
      ${kpiCard({
        label: '注册用户', iconName: 'users', value: fmtInt(kpis.users_total),
        foot: `<span class="delta delta--up">+${fmtInt(kpis.users_new)}</span><span>近 ${days} 天</span>`,
        spark: sparkline(series.users_new.slice(-14)),
      })}
      ${kpiCard({
        label: '活跃用户', iconName: 'pulse', value: fmtInt(kpis.users_active),
        foot: `<span class="delta delta--flat">${fmtPct(activeShare)}</span><span>占注册用户 · 有任一记录</span>`,
      })}
      ${kpiCard({
        label: '猫咪档案', iconName: 'paw', value: fmtInt(kpis.pets_total),
        foot: `<span class="delta delta--up">+${fmtInt(kpis.pets_new)}</span><span>近 ${days} 天</span>`,
        spark: sparkline(series.pets_new.slice(-14), { color: CHART_COLORS.strong }),
      })}
      ${kpiCard({
        label: '健康初筛', iconName: 'pulse', value: fmtInt(kpis.screenings), accent: true,
        foot: `<span class="delta ${kpis.redline_hits ? 'delta--down' : 'delta--flat'}">红线 ${fmtInt(kpis.redline_hits)} 次</span><span>命中率 ${fmtPct(kpis.redline_rate)}</span>`,
      })}
      ${kpiCard({
        label: 'AI 调用', iconName: 'spark', value: fmtInt(kpis.ai_calls),
        foot: `<span>估算成本</span><strong>${fmtCost(kpis.ai_cost)}</strong><span>· 配额拒绝 ${fmtInt(kpis.quota_denials)} 次</span>`,
      })}
      ${kpiCard({
        label: '聊天消息', iconName: 'overview', value: fmtInt(kpis.chat_messages),
        foot: `<span>饮食 ${fmtInt(kpis.diet_records)} 条 · 体重 ${fmtInt(kpis.weight_records)} 条</span>`,
      })}
      ${kpiCard({
        label: '待处理注销', iconName: 'alert', value: fmtInt(kpis.pending_deletions),
        foot: `<span>注销冷静期 15 天 · 已停用 ${fmtInt(kpis.users_suspended)} 个账号</span>`,
      })}
      ${kpiCard({
        label: '用户活跃率', iconName: 'check', value: fmtPct(activeShare),
        foot: `<span>活跃 ${fmtInt(kpis.users_active)} / 总 ${fmtInt(kpis.users_total)} · 近 ${days} 天</span>`,
      })}
    </section>

    <div class="dash-grid">
      <div class="stack">
        <section class="card">
          <div class="card-head">
            <div><h2 class="card-title">增长趋势</h2><p class="card-sub">新增用户与新增猫咪档案 · 近 ${days} 天</p></div>
            <a class="card-action" href="#/users">用户列表</a>
          </div>
          ${lineChart({
            labels: series.days,
            series: [
              { name: '新增用户', values: series.users_new },
              { name: '新增猫咪', values: series.pets_new, color: CHART_COLORS.strong },
            ],
            height: 216,
            yFormat: (value) => fmtInt(Math.round(value)),
            integer: true,
          })}
        </section>
        <section class="card">
          <div class="card-head">
            <div><h2 class="card-title">每日互动</h2><p class="card-sub">初筛、聊天与饮食记录次数</p></div>
          </div>
          ${lineChart({
            labels: series.days,
            series: [
              { name: '健康初筛', values: series.screenings },
              { name: '聊天消息', values: series.chat_messages, color: CHART_COLORS.accent },
              { name: '饮食记录', values: series.diet_records, color: CHART_COLORS.strong },
            ],
            height: 216,
            yFormat: (value) => fmtInt(Math.round(value)),
            integer: true,
          })}
        </section>
      </div>
      <div class="stack">
        <section class="card">
          <div class="card-head">
            <div><h2 class="card-title">初筛状态分布</h2><p class="card-sub">近 ${days} 天 · 共 ${fmtInt(screeningTotal)} 次</p></div>
            <a class="card-action" href="#/screenings">明细</a>
          </div>
          <div class="donut-wrap">
            ${donut({ items: stateItems, centerLabel: '初筛次数', size: 156, thickness: 17 })}
            <div class="donut-legend">
              ${stateItems.map((item) => `
                <div class="donut-row">
                  ${dot(item.color)}
                  <span class="donut-row-name">${esc(item.name)}</span>
                  <span class="donut-row-val">${fmtInt(item.value)}</span>
                  <span class="donut-row-pct">${fmtPct(screeningTotal ? item.value / screeningTotal : 0, 0)}</span>
                </div>`).join('')}
              <div class="donut-row">
                ${dot(CHART_COLORS.timestamp)}
                <span class="donut-row-name">就医 / 急诊拆分</span>
                <span class="donut-row-val">${fmtInt(vet)} / ${fmtInt(urgent)}</span>
                <span class="donut-row-pct"></span>
              </div>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <div><h2 class="card-title">最近红线</h2><p class="card-sub">命中紧急信号的最新记录</p></div>
            <a class="card-action" href="#/screenings">全部</a>
          </div>
          ${data.redlines.length ? `<div class="row-list">${data.redlines.map((item) => `
            <button class="row-item" type="button" data-action="open-screening" data-id="${item.id}">
              <span class="row-main">
                <span class="row-title">${esc(item.pet_name)} · ${esc(item.owner_nickname)}</span>
                <span class="row-sub">记录 #${item.id} · 用户 #${item.user_id}</span>
              </span>
              <span class="row-tail">${statePill(item.state)}<span class="row-time">${fmtRelative(item.created_at)}</span></span>
              ${icon('chevronRight', 16)}
            </button>`).join('')}</div>` : `<div class="insight insight--success">${icon('check', 17)}<div><strong>窗口内没有红线记录</strong><p>健康初筛未命中紧急信号。</p></div></div>`}
        </section>

        <section class="card">
          <div class="card-head">
            <div><h2 class="card-title">AI 成本</h2><p class="card-sub">${fmtInt(kpis.ai_calls)} 次调用 · ${fmtCost(kpis.ai_cost)}</p></div>
            <a class="card-action" href="#/usage">成本明细</a>
          </div>
          ${data.ai_models.length ? `<div class="bar-list">${data.ai_models.slice(0, 4).map((item) => {
            const max = Math.max(...data.ai_models.map((row) => row.calls), 1);
            return `<div class="bar-item">
              <div class="bar-line"><span class="bar-name">${esc(item.model)}<small>${esc(AI_KIND_LABELS[item.kind] || item.kind)}</small></span><span class="bar-value">${fmtInt(item.calls)} 次</span></div>
              <div class="bar-track">${barSvg(item.calls, max)}</div>
            </div>`;
          }).join('')}</div>` : `<p class="empty-sub">窗口内还没有 AI 调用。</p>`}
        </section>

        <section class="card">
          <div class="card-head">
            <div><h2 class="card-title">今日配额</h2><p class="card-sub">全体用户合计 · UTC 自然日 · 健康初筛红线不占配额</p></div>
          </div>
          ${data.quota_today.length ? `<div class="mini-table">${data.quota_today.map((item) => `
            <div class="mini-row">
              <span class="mini-name">${esc(QUOTA_LABELS[item.metric] || item.metric)}</span>
              <span class="mini-num">${fmtInt(item.used)}</span>
              <span class="mini-sub">次</span>
            </div>`).join('')}</div>` : `<p class="empty-sub">今天还没有产生配额用量。</p>`}
        </section>
      </div>
    </div>`;
}

function alertsHtml(alerts) {
  if (!alerts.length) {
    return `<div class="alert-stack"><div class="insight insight--success">${icon('check', 17)}
      <div><strong>运营指标平稳</strong><p>窗口内没有需要人工处理的异常提醒。</p></div></div></div>`;
  }
  return `<div class="alert-stack">${alerts.map((item) => `
    <div class="insight insight--${item.level === 'danger' ? 'danger' : 'warning'}">
      ${icon(item.level === 'danger' ? 'alert' : 'info', 17)}
      <div><strong>${esc(item.title)}</strong><p>${esc(item.detail)}</p></div>
    </div>`).join('')}</div>`;
}

/* ------------------------------------------------------------------ */
/* 用户                                                                */

function viewUsers() {
  const filters = [['all', '全部'], ['active', '正常'], ['suspended', '已停用'], ['deletion_pending', '注销中'], ['deleted', '已删除']];
  document.getElementById('content').innerHTML = `
    <section class="card card--flush table-card">
      <div class="table-head">
        <div><h2>用户列表</h2><p id="users-count">正在加载用户…</p></div>
        <div class="table-tools">${searchBox('user-search', '搜索昵称或邮箱', state.users.query)}</div>
      </div>
      <div class="filter-bar">${chipRow('user-status', filters, state.users.status)}</div>
      <div id="list-body">${tableSkeleton()}</div>
    </section>`;
  bindSearch('user-search', (value) => {
    state.users.query = value;
    state.users.page = 1;
    loadUsers();
  });
  bindChips('user-status', (value) => {
    state.users.status = value;
    state.users.page = 1;
    setChipPressed('user-status', value);
    loadUsers();
  });
  loadUsers();
}

function usersTable(data) {
  return `<div class="table-wrap"><table class="data-table">
    <caption class="sr-only">用户列表</caption>
    <thead><tr><th>用户</th><th>状态</th><th>猫咪</th><th>初筛</th><th>最近初筛</th><th>注册时间</th><th><span class="sr-only">操作</span></th></tr></thead>
    <tbody>${data.items.map((item) => `
      <tr class="is-clickable" data-action="open-user" data-id="${item.id}">
        <td><div class="cell-title">${esc(item.nickname)}</div><div class="cell-sub">${esc(item.email || '未绑定邮箱')}</div></td>
        <td>${userStatusPill(item.status)}</td>
        <td><span class="num">${fmtInt(item.pet_count)}</span>${item.pet_names.length ? `<div class="cell-sub">${esc(item.pet_names.slice(0, 2).join('、'))}${item.pet_names.length > 2 ? '…' : ''}</div>` : ''}</td>
        <td class="num">${fmtInt(item.screening_count)}</td>
        <td class="nowrap cell-muted">${item.last_screening_at ? fmtRelative(item.last_screening_at) : '—'}</td>
        <td class="nowrap cell-muted">${fmtDate(item.created_at)}</td>
        <td><button class="icon-btn icon-btn--quiet" type="button" data-action="open-user" data-id="${item.id}" aria-label="查看 ${esc(item.nickname)}">${icon('chevronRight', 17)}</button></td>
      </tr>`).join('')}</tbody>
  </table></div>`;
}

async function loadUsers() {
  const list = state.users;
  const seq = ++list.seq;
  const body = document.getElementById('list-body');
  if (!body) return;
  body.innerHTML = tableSkeleton();
  try {
    const data = await adminApi.users({
      query: list.query, status: list.status, page: list.page, page_size: 20,
    });
    if (seq !== list.seq || state.route !== 'users' || !document.getElementById('list-body')) return;
    const count = document.getElementById('users-count');
    if (count) count.textContent = `共 ${fmtInt(data.total)} 位用户 · 按注册时间倒序`;
    if (!data.items.length) {
      document.getElementById('list-body').innerHTML = emptyBlock('还没有符合条件的用户', '试试清空搜索，或切换到「全部」状态。');
      return;
    }
    document.getElementById('list-body').innerHTML = usersTable(data) + pagerHtml(data);
    bindPager(document.getElementById('list-body'), (page) => {
      list.page = page;
      loadUsers();
      document.getElementById('list-body').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  } catch (error) {
    if (seq !== list.seq) return;
    document.getElementById('list-body').innerHTML = inlineError(error);
  }
}

/* ------------------------------------------------------------------ */
/* 猫咪                                                                */

function viewPets() {
  const filters = [['all', '全部'], ['active', '在册'], ['deleted', '已删除']];
  document.getElementById('content').innerHTML = `
    <section class="card card--flush table-card">
      <div class="table-head">
        <div><h2>猫咪档案</h2><p id="pets-count">正在加载猫咪…</p></div>
        <div class="table-tools">${searchBox('pet-search', '搜索猫咪、主人或邮箱', state.pets.query)}</div>
      </div>
      <div class="filter-bar">${chipRow('pet-status', filters, state.pets.status)}</div>
      <div id="list-body">${tableSkeleton()}</div>
    </section>`;
  bindSearch('pet-search', (value) => {
    state.pets.query = value;
    state.pets.page = 1;
    loadPets();
  });
  bindChips('pet-status', (value) => {
    state.pets.status = value;
    state.pets.page = 1;
    setChipPressed('pet-status', value);
    loadPets();
  });
  loadPets();
}

function petsTable(data) {
  return `<div class="table-wrap"><table class="data-table">
    <caption class="sr-only">猫咪档案列表</caption>
    <thead><tr><th>猫咪</th><th>主人</th><th>性别 / 年龄</th><th>最新体重</th><th>初筛</th><th>状态</th><th>建档时间</th></tr></thead>
    <tbody>${data.items.map((item) => `
      <tr>
        <td><div class="cell-title">${esc(item.name)}</div><div class="cell-sub">#${item.id} · ${esc(item.breed || '品种未填')}</div></td>
        <td><div class="cell-title">${esc(item.owner_nickname)}</div><div class="cell-sub">${esc(item.owner_email || '未绑定邮箱')}</div></td>
        <td class="nowrap"><span>${esc(sexLabel(item.sex))}</span><div class="cell-sub">${esc(fmtAge(item.birth_date))}</div></td>
        <td class="num">${item.weight_kg ? `${item.weight_kg.toFixed(2)} kg` : '—'}</td>
        <td class="num">${fmtInt(item.screening_count)}</td>
        <td>${petStatusPill(item.status)}</td>
        <td class="nowrap cell-muted">${fmtDate(item.created_at)}</td>
      </tr>`).join('')}</tbody>
  </table></div>`;
}

async function loadPets() {
  const list = state.pets;
  const seq = ++list.seq;
  const body = document.getElementById('list-body');
  if (!body) return;
  body.innerHTML = tableSkeleton();
  try {
    const data = await adminApi.pets({
      query: list.query, status: list.status, page: list.page, page_size: 20,
    });
    if (seq !== list.seq || state.route !== 'pets' || !document.getElementById('list-body')) return;
    const count = document.getElementById('pets-count');
    if (count) count.textContent = `共 ${fmtInt(data.total)} 份猫咪档案 · 含已删除记录`;
    if (!data.items.length) {
      document.getElementById('list-body').innerHTML = emptyBlock('还没有符合条件的猫咪', '可以搜索猫咪名字，或切换状态筛选。');
      return;
    }
    document.getElementById('list-body').innerHTML = petsTable(data) + pagerHtml(data);
    bindPager(document.getElementById('list-body'), (page) => {
      list.page = page;
      loadPets();
      document.getElementById('list-body').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  } catch (error) {
    if (seq !== list.seq) return;
    document.getElementById('list-body').innerHTML = inlineError(error);
  }
}

/* ------------------------------------------------------------------ */
/* 初筛                                                                */

function viewScreenings() {
  const filters = [['all', '全部'], ['normal', '正常'], ['observe', '观察'], ['vet', '就医'], ['urgent', '急诊']];
  document.getElementById('content').innerHTML = `
    <section class="card card--flush table-card">
      <div class="table-head">
        <div><h2>初筛记录</h2><p id="screenings-count">正在加载初筛…</p></div>
        <div class="table-tools">${searchBox('screening-search', '搜索猫咪、主人或邮箱', state.screenings.query)}</div>
      </div>
      <div class="filter-bar">
        ${chipRow('screening-state', filters, state.screenings.state)}
        <button class="chip" type="button" id="redline-toggle" aria-pressed="${state.screenings.redline === 'only'}">
          ${icon('alert', 14)} 只看红线
        </button>
      </div>
      <div id="list-body">${tableSkeleton()}</div>
    </section>`;
  bindSearch('screening-search', (value) => {
    state.screenings.query = value;
    state.screenings.page = 1;
    loadScreenings();
  });
  bindChips('screening-state', (value) => {
    state.screenings.state = value;
    state.screenings.page = 1;
    setChipPressed('screening-state', value);
    loadScreenings();
  });
  const toggle = document.getElementById('redline-toggle');
  toggle.addEventListener('click', () => {
    state.screenings.redline = state.screenings.redline === 'only' ? 'all' : 'only';
    state.screenings.page = 1;
    toggle.setAttribute('aria-pressed', String(state.screenings.redline === 'only'));
    loadScreenings();
  });
  loadScreenings();
}

function screeningsTable(data) {
  return `<div class="table-wrap"><table class="data-table">
    <caption class="sr-only">健康初筛列表</caption>
    <thead><tr><th>猫咪 / 主人</th><th>状态</th><th>红线</th><th>精神 / 食欲</th><th>症状</th><th>规则版本</th><th>时间</th><th><span class="sr-only">操作</span></th></tr></thead>
    <tbody>${data.items.map((item) => `
      <tr class="is-clickable" data-action="open-screening" data-id="${item.id}">
        <td><div class="cell-title">${esc(item.pet_name)} · ${esc(item.owner_nickname)}</div><div class="cell-sub">#${item.id} · ${esc(item.owner_email || '未绑定邮箱')}</div></td>
        <td>${statePill(item.state)}</td>
        <td>${item.redline_hit ? pill('命中', 'danger', '!') : pill('无', 'mist', '•')}</td>
        <td class="nowrap">${esc(spiritLabel(item.spirit))}<div class="cell-sub">${esc(appetiteLabel(item.appetite))}</div></td>
        <td><div class="cell-chips">${item.symptoms.length ? item.symptoms.slice(0, 3).map((symptom) => `<span class="tag ${symptom.grade === 'vet' ? 'tag--danger' : symptom.grade === 'observe' ? 'tag--warning' : 'tag--mist'}">${esc(symptom.label)}</span>`).join('') : `<span class="cell-muted">无症状</span>`}${item.symptoms.length > 3 ? `<span class="tag tag--mist">+${item.symptoms.length - 3}</span>` : ''}</div></td>
        <td class="nowrap cell-muted">${esc(item.rules_version)}</td>
        <td class="nowrap cell-muted">${fmtDateTime(item.created_at)}</td>
        <td><button class="icon-btn icon-btn--quiet" type="button" data-action="open-screening" data-id="${item.id}" aria-label="查看初筛 #${item.id}">${icon('chevronRight', 17)}</button></td>
      </tr>`).join('')}</tbody>
  </table></div>`;
}

async function loadScreenings() {
  const list = state.screenings;
  const seq = ++list.seq;
  const body = document.getElementById('list-body');
  if (!body) return;
  body.innerHTML = tableSkeleton();
  try {
    const data = await adminApi.screenings({
      query: list.query, state: list.state, redline: list.redline, page: list.page, page_size: 20,
    });
    if (seq !== list.seq || state.route !== 'screenings' || !document.getElementById('list-body')) return;
    const count = document.getElementById('screenings-count');
    if (count) count.textContent = `共 ${fmtInt(data.total)} 条初筛记录 · 按时间倒序`;
    if (!data.items.length) {
      document.getElementById('list-body').innerHTML = emptyBlock('还没有符合条件的初筛记录', '可以清空搜索、切换状态，或关闭「只看红线」。');
      return;
    }
    document.getElementById('list-body').innerHTML = screeningsTable(data) + pagerHtml(data);
    bindPager(document.getElementById('list-body'), (page) => {
      list.page = page;
      loadScreenings();
      document.getElementById('list-body').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  } catch (error) {
    if (seq !== list.seq) return;
    document.getElementById('list-body').innerHTML = inlineError(error);
  }
}

function spiritLabel(value) {
  return { normal: '精神正常', slightly_down: '精神略差', markedly_down: '精神明显变差' }[value] || value || '—';
}

function appetiteLabel(value) {
  return { normal: '食欲正常', decreased: '食欲下降', refused: '拒食' }[value] || value || '—';
}

/* ------------------------------------------------------------------ */
/* AI 与成本                                                           */

async function viewUsage(seq) {
  const content = document.getElementById('content');
  content.innerHTML = pageSkeleton();
  try {
    const data = await adminApi.aiUsage(state.usageDays);
    if (seq !== state.renderSeq) return;
    content.innerHTML = usageHtml(data);
  } catch (error) {
    if (seq !== state.renderSeq) return;
    content.innerHTML = errorCard(error);
  }
}

function usageHtml(data) {
  const ai = data.ai;
  const totals = ai.totals;
  const tasks = data.tasks;
  const failed = tasks.reduce((sum, item) => sum + item.failed, 0);
  const taskTotal = tasks.reduce((sum, item) => sum + item.total, 0);
  const failureRate = taskTotal ? failed / taskTotal : 0;
  const byMetric = {};
  data.quota_denials.forEach((item) => {
    byMetric[item.metric] = byMetric[item.metric] || { metric: item.metric, count: 0, lastDay: item.day };
    byMetric[item.metric].count += item.count;
    if (item.day > byMetric[item.metric].lastDay) byMetric[item.metric].lastDay = item.day;
  });
  const metricRows = Object.values(byMetric).sort((a, b) => b.count - a.count);

  return `
    <section class="kpi-grid" aria-label="AI 成本指标">
      ${kpiCard({ label: 'AI 调用', iconName: 'spark', value: fmtInt(totals.calls), foot: `<span>近 ${data.window.days} 天</span>` })}
      ${kpiCard({ label: '输入 / 输出 tokens', iconName: 'overview', value: `${fmtInt(totals.tokens_in)}<small>/ ${fmtInt(totals.tokens_out)}</small>`, foot: '<span>仅统计已记录 tokens 的调用</span>' })}
      ${kpiCard({ label: '估算成本', iconName: 'spark', value: fmtCost(totals.cost_est), accent: true, foot: `<span>媒体时长 ${fmtInt(Math.round(totals.media_seconds || 0))} 秒</span>` })}
      ${kpiCard({ label: '任务失败率', iconName: 'alert', value: fmtPct(failureRate), foot: `<span>${fmtInt(failed)} / ${fmtInt(taskTotal)} 个任务失败</span>` })}
    </section>

    <div class="dash-grid dash-grid--even">
      <section class="card">
        <div class="card-head"><div><h2 class="card-title">每日调用次数</h2><p class="card-sub">近 ${data.window.days} 天</p></div></div>
        ${lineChart({ labels: ai.days, series: [{ name: '调用次数', values: ai.calls }], height: 208, yFormat: (value) => fmtInt(Math.round(value)), integer: true })}
      </section>
      <section class="card">
        <div class="card-head"><div><h2 class="card-title">每日估算成本</h2><p class="card-sub">人民币，按模型单价估算</p></div></div>
        ${lineChart({ labels: ai.days, series: [{ name: '估算成本', values: ai.cost, color: CHART_COLORS.accent }], height: 208, yFormat: (value) => `¥${Number(value).toFixed(1)}` })}
      </section>
    </div>

    <div class="dash-grid dash-grid--even section-gap">
      <section class="card">
        <div class="card-head"><div><h2 class="card-title">模型用量</h2><p class="card-sub">按调用次数排序</p></div></div>
        ${ai.models.length ? `<div class="table-wrap"><table class="data-table data-table--compact">
          <thead><tr><th>模型</th><th>调用</th><th>tokens</th><th>成本</th></tr></thead>
          <tbody>${ai.models.map((item) => `
            <tr>
              <td><div class="cell-title">${esc(item.model)}</div><div class="cell-sub">${esc(AI_KIND_LABELS[item.kind] || item.kind)}</div></td>
              <td class="num">${fmtInt(item.calls)}</td>
              <td class="num">${fmtInt(item.tokens_in)} / ${fmtInt(item.tokens_out)}</td>
              <td class="num">${fmtCost(item.cost_est)}</td>
            </tr>`).join('')}</tbody>
        </table></div>` : emptyBlock('窗口内没有 AI 调用')}
      </section>

      <section class="card">
        <div class="card-head"><div><h2 class="card-title">后台任务</h2><p class="card-sub">分身、GIF 与异步解读的成败</p></div></div>
        ${tasks.length ? `<div class="table-wrap"><table class="data-table data-table--compact">
          <thead><tr><th>任务</th><th>总数</th><th>成功</th><th>失败</th><th>成功率</th></tr></thead>
          <tbody>${tasks.map((item) => `
            <tr>
              <td><div class="cell-title">${esc(TASK_LABELS[item.type] || item.type)}</div><div class="cell-sub">重试 ${fmtInt(item.retried)} · 进行中 ${fmtInt(item.in_flight)}</div></td>
              <td class="num">${fmtInt(item.total)}</td>
              <td class="num">${fmtInt(item.succeeded)}</td>
              <td class="num">${item.failed ? `<span class="pill pill--danger">${fmtInt(item.failed)}</span>` : '0'}</td>
              <td class="num">${item.success_rate === null ? '—' : fmtPct(item.success_rate, 0)}</td>
            </tr>`).join('')}</tbody>
        </table></div>` : emptyBlock('窗口内没有后台任务')}
      </section>
    </div>

    <div class="dash-grid dash-grid--even section-gap">
      <section class="card">
        <div class="card-head"><div><h2 class="card-title">单用户成本 Top 10</h2><p class="card-sub">窗口内合计</p></div></div>
        ${data.per_user.length ? `<div class="mini-table">${data.per_user.map((item) => `
          <div class="mini-row">
            <span class="mini-name">${esc(item.nickname)}<small>${esc(item.email || `用户 #${item.user_id ?? '已注销'}`)}</small></span>
            <span class="mini-num">${fmtCost(item.cost_est)}</span>
            <span class="mini-sub">${fmtInt(item.calls)} 次</span>
          </div>`).join('')}</div>` : `<p class="empty-sub">窗口内还没有可归属到用户的调用。</p>`}
      </section>

      <section class="card">
        <div class="card-head"><div><h2 class="card-title">配额拒绝</h2><p class="card-sub">窗口内按指标聚合</p></div></div>
        ${metricRows.length ? `<div class="mini-table">${metricRows.map((item) => `
          <div class="mini-row">
            <span class="mini-name">${esc(QUOTA_LABELS[item.metric] || item.metric)}</span>
            <span class="mini-num">${fmtInt(item.count)}</span>
            <span class="mini-sub">最近 ${esc(item.lastDay)}</span>
          </div>`).join('')}</div>` : `<p class="empty-sub">窗口内没有被拒绝的配额请求。</p>`}
      </section>
    </div>`;
}

/* ------------------------------------------------------------------ */
/* 审计                                                                */

function viewAudit() {
  document.getElementById('content').innerHTML = `
    <section class="card card--flush table-card">
      <div class="table-head">
        <div><h2>审计日志</h2><p id="audit-count">正在加载审计记录…</p></div>
      </div>
      <div id="list-body">${tableSkeleton()}</div>
    </section>`;
  loadAudit();
}

function auditRows(data) {
  return data.items.map((item) => `
    <tr>
      <td class="nowrap cell-muted">${fmtDateTime(item.created_at)}</td>
      <td><div class="cell-title">${esc(item.admin_nickname)}</div><div class="cell-sub">${esc(item.admin_email || `#${item.admin_user_id}`)}</div></td>
      <td><div class="cell-title">${esc(actionLabel(item.action))}</div><div class="cell-sub">${esc(item.action)}</div></td>
      <td class="nowrap">${esc(targetLabel(item.target_type))}${item.target_id ? ` #${item.target_id}` : ''}</td>
      <td><span class="cell-muted">${esc(auditDetail(item))}</span></td>
    </tr>`).join('');
}

async function loadAudit() {
  const list = state.audit;
  const seq = ++list.seq;
  const body = document.getElementById('list-body');
  if (!body) return;
  body.innerHTML = tableSkeleton();
  try {
    const data = await adminApi.audit({ page: list.page, page_size: 20 });
    if (seq !== list.seq || state.route !== 'audit' || !document.getElementById('list-body')) return;
    const count = document.getElementById('audit-count');
    if (count) count.textContent = `共 ${fmtInt(data.total)} 条记录 · 写操作留痕`;
    if (!data.items.length) {
      document.getElementById('list-body').innerHTML = emptyBlock('还没有管理操作', '停用或恢复账号后，这里会出现记录。');
      return;
    }
    document.getElementById('list-body').innerHTML = `<div class="table-wrap"><table class="data-table">
      <caption class="sr-only">管理员审计日志</caption>
      <thead><tr><th>时间</th><th>管理员</th><th>操作</th><th>对象</th><th>详情</th></tr></thead>
      <tbody>${auditRows(data)}</tbody>
    </table></div>${pagerHtml(data)}`;
    bindPager(document.getElementById('list-body'), (page) => {
      list.page = page;
      loadAudit();
    });
  } catch (error) {
    if (seq !== list.seq) return;
    document.getElementById('list-body').innerHTML = inlineError(error);
  }
}

function actionLabel(action) {
  return { 'user.status': '变更用户状态' }[action] || action;
}

function targetLabel(type) {
  return { user: '用户', pet: '猫咪', screening: '初筛' }[type] || type;
}

function auditDetail(item) {
  if (item.action === 'user.status' && item.detail) {
    const from = USER_STATUS[item.detail.from]?.label || item.detail.from;
    const to = USER_STATUS[item.detail.to]?.label || item.detail.to;
    return `${from} → ${to}`;
  }
  try { return JSON.stringify(item.detail ?? {}); } catch { return '—'; }
}

/* ------------------------------------------------------------------ */
/* 通用列表部件                                                        */

function searchBox(id, placeholder, value = '') {
  return `<div class="search-box">${icon('search', 15)}<input id="${id}" type="search" value="${esc(value)}" placeholder="${esc(placeholder)}" autocomplete="off" aria-label="${esc(placeholder)}"></div>`;
}

function chipRow(attr, options, active) {
  return options.map(([value, label]) => `<button class="chip" type="button" data-${attr}="${value}" aria-pressed="${value === active}">${esc(label)}</button>`).join('');
}

function bindSearch(id, handler) {
  const input = document.getElementById(id);
  if (!input) return;
  let timer = 0;
  input.addEventListener('input', () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => handler(input.value.trim()), 260);
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      window.clearTimeout(timer);
      handler(input.value.trim());
    }
  });
}

function bindChips(attr, handler) {
  document.querySelectorAll(`[data-${attr}]`).forEach((button) => {
    button.addEventListener('click', () => handler(button.dataset[attr === 'user-status' ? 'userStatus' : attr === 'pet-status' ? 'petStatus' : 'screeningState']));
  });
}

function setChipPressed(attr, value) {
  document.querySelectorAll(`[data-${attr}]`).forEach((button) => {
    const key = attr === 'user-status' ? 'userStatus' : attr === 'pet-status' ? 'petStatus' : 'screeningState';
    button.setAttribute('aria-pressed', String(button.dataset[key] === value));
  });
}

function pagerHtml(data) {
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  return `<div class="pager">
    <span>第 ${data.page} / ${pages} 页 · 每页 ${data.page_size} 条</span>
    <div class="pager-btns">
      <button class="icon-btn" type="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''} aria-label="上一页">${icon('chevronLeft', 17)}</button>
      <button class="icon-btn" type="button" data-page="${data.page + 1}" ${data.page >= pages ? 'disabled' : ''} aria-label="下一页">${icon('chevronRight', 17)}</button>
    </div>
  </div>`;
}

function bindPager(container, handler) {
  container.querySelectorAll('[data-page]').forEach((button) => {
    button.addEventListener('click', () => {
      if (button.disabled) return;
      handler(Number(button.dataset.page));
    });
  });
}

/* ------------------------------------------------------------------ */
/* 抽屉：用户 / 初筛                                                   */

function lockBody() {
  document.body.classList.add('is-locked');
}

function unlockBody() {
  if (!document.getElementById('admin-drawer') && !document.getElementById('admin-modal')) {
    document.body.classList.remove('is-locked');
  }
}

function mountDrawer(title, sub) {
  closeDrawer();
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.id = 'drawer-overlay';
  overlay.dataset.action = 'close-drawer';
  const drawer = document.createElement('aside');
  drawer.className = 'drawer';
  drawer.id = 'admin-drawer';
  drawer.setAttribute('role', 'dialog');
  drawer.setAttribute('aria-modal', 'true');
  drawer.setAttribute('aria-label', title);
  drawer.innerHTML = `
    <div class="drawer-head">
      <div class="drawer-head-main">
        <h2 class="drawer-title" id="drawer-title">${esc(title)}</h2>
        <p class="drawer-sub" id="drawer-sub">${esc(sub || '')}</p>
      </div>
      <button class="icon-btn" type="button" data-action="close-drawer" aria-label="关闭详情">${icon('close', 18)}</button>
    </div>
    <div class="drawer-body" id="drawer-body"></div>
    <div class="drawer-actions" id="drawer-actions"></div>`;
  document.body.append(overlay, drawer);
  lockBody();
  drawer.querySelector('[data-action="close-drawer"]')?.focus();
}

function updateDrawer({ title, sub, body, actions = '' }) {
  const drawer = document.getElementById('admin-drawer');
  if (!drawer) return;
  document.getElementById('drawer-title').textContent = title;
  document.getElementById('drawer-sub').textContent = sub || '';
  document.getElementById('drawer-body').innerHTML = body || '';
  document.getElementById('drawer-actions').innerHTML = actions;
}

function closeDrawer() {
  state.drawerKey = null;
  document.getElementById('admin-drawer')?.remove();
  document.getElementById('drawer-overlay')?.remove();
  unlockBody();
}

function drawerSkeleton() {
  return `<div class="skeleton skeleton-block"></div>
    <div class="skeleton skeleton-block"></div>
    <div class="skeleton skeleton-block"></div>`;
}

async function openUser(id) {
  const key = `user:${id}`;
  mountDrawer('用户详情', '正在加载账号与健康档案…');
  state.drawerKey = key;
  document.getElementById('drawer-body').innerHTML = drawerSkeleton();
  try {
    const data = await adminApi.user(id);
    if (state.drawerKey !== key) return;
    renderUserDrawer(data);
  } catch (error) {
    if (state.drawerKey !== key) return;
    updateDrawer({ title: '用户详情', sub: '加载失败', body: inlineError(error), actions: '' });
  }
}

function renderUserDrawer(data) {
  const user = data.user;
  const petNames = Object.fromEntries(data.pets.map((pet) => [pet.id, pet.name]));
  const canManage = user.id !== state.session.admin.id
    && user.status !== 'deletion_pending' && user.status !== 'deleted';
  const suspend = user.status !== 'suspended';
  const actions = canManage
    ? `<button class="btn ${suspend ? 'btn-secondary' : 'btn-primary'}" type="button" data-action="ask-status"
         data-id="${user.id}" data-next="${suspend ? 'suspended' : 'active'}"
         data-name="${esc(user.nickname)}">${suspend ? '停用账号' : '恢复账号'}</button>
       <span class="cell-muted align-center">${suspend ? '停用后立即无法登录，数据保留。' : '恢复后可以重新登录。'}</span>`
    : `<span class="cell-muted align-center">${user.id === state.session.admin.id ? '这是当前登录的管理员账号。' : '注销冷静期内的账号不可变更状态。'}</span>`;

  const consentRows = [
    ['privacy', '隐私政策'], ['terms', '服务协议'], ['training', '训练授权'],
  ].map(([kind, label]) => {
    const consent = data.consents[kind];
    return `<div class="info-row">
      <span class="info-key">${label}</span>
      <span class="info-val">${consent ? `${consent.granted ? pill('已同意', 'success', '✓') : pill('未同意', 'mist', '•')} <span class="cell-sub">版本 ${esc(consent.version)}</span>` : '<span class="cell-muted">未记录</span>'}</span>
    </div>`;
  }).join('');

  const petCards = data.pets.length ? data.pets.map((pet) => `
    <div class="pet-card">
      <div class="pet-card-head">
        <span class="pet-avatar" aria-hidden="true">${esc(pet.name.slice(0, 1))}</span>
        <span class="pet-name">${esc(pet.name)}</span>
        ${petStatusPill(pet.status)}
      </div>
      <div class="pet-meta">
        <span>${esc(pet.breed || '品种未填')}</span>
        <span>${esc(sexLabel(pet.sex))}</span>
        <span>${esc(fmtAge(pet.birth_date))}</span>
        <span>${pet.weight_kg ? `${pet.weight_kg.toFixed(2)} kg` : '暂无体重'}</span>
      </div>
    </div>`).join('') : `<p class="empty-sub">该账号还没有猫咪档案。</p>`;

  const recent = data.recent_screenings.length ? `<div class="row-list">${data.recent_screenings.map((item) => `
    <button class="row-item" type="button" data-action="open-screening" data-id="${item.id}">
      <span class="row-main">
        <span class="row-title">${esc(petNames[item.pet_id] || `猫咪 #${item.pet_id}`)}</span>
        <span class="row-sub">初筛 #${item.id} · ${fmtDateTime(item.created_at)}</span>
      </span>
      <span class="row-tail">${statePill(item.state)}</span>
      ${item.redline_hit ? pill('红线', 'danger', '!') : ''}
      ${icon('chevronRight', 15)}
    </button>`).join('')}</div>` : `<p class="empty-sub">还没有初筛记录。</p>`;

  updateDrawer({
    title: user.nickname,
    sub: `${user.email || '未绑定邮箱'} · 用户 #${user.id}`,
    body: `
      <div class="inline-flex-row">
        ${userStatusPill(user.status)}
        <span class="cell-muted">注册于 ${fmtDateTime(user.created_at)}</span>
      </div>
      <div class="detail-grid detail-grid--spaced">
        <div class="stat-tile"><div class="stat-label">初筛</div><div class="stat-value">${fmtInt(data.counts.screenings)}</div></div>
        <div class="stat-tile"><div class="stat-label">红线命中</div><div class="stat-value">${fmtInt(data.counts.redlines)}</div></div>
        <div class="stat-tile"><div class="stat-label">聊天消息</div><div class="stat-value">${fmtInt(data.counts.chat_messages)}</div></div>
        <div class="stat-tile"><div class="stat-label">饮食 / 体重</div><div class="stat-value">${fmtInt(data.counts.diet_records)}<small>/ ${fmtInt(data.counts.weight_records)}</small></div></div>
        <div class="stat-tile"><div class="stat-label">AI 调用</div><div class="stat-value">${fmtInt(data.counts.ai_calls)}</div></div>
        <div class="stat-tile"><div class="stat-label">AI 估算成本</div><div class="stat-value">${fmtCost(data.counts.ai_cost)}</div></div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">账号信息</div>
        <div class="info-list">
          <div class="info-row"><span class="info-key">用户 ID</span><span class="info-val">#${user.id}</span></div>
          <div class="info-row"><span class="info-key">状态</span><span class="info-val">${userStatusPill(user.status)}</span></div>
          <div class="info-row"><span class="info-key">邮箱</span><span class="info-val">${esc(user.email || '未绑定')}</span></div>
          <div class="info-row"><span class="info-key">注册时间</span><span class="info-val">${fmtDateTime(user.created_at)}</span></div>
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">猫咪档案 <span class="cell-sub">${data.pets.length} 只</span></div>
        ${petCards}
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">协议与授权</div>
        <div class="info-list">${consentRows}</div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">最近初筛</div>
        ${recent}
      </div>

      ${data.deletion_job ? `<div class="drawer-section">
        <div class="drawer-section-title">注销任务</div>
        <div class="note-block note-block--danger">状态：${esc(data.deletion_job.status)} · 申请于 ${fmtDateTime(data.deletion_job.requested_at)}<br>预计物理清除：${fmtDateTime(data.deletion_job.purge_after)}</div>
      </div>` : ''}`,
    actions,
  });
}

async function openScreening(id) {
  const key = `screening:${id}`;
  mountDrawer('初筛详情', `正在加载记录 #${id}…`);
  state.drawerKey = key;
  document.getElementById('drawer-body').innerHTML = drawerSkeleton();
  try {
    const data = await adminApi.screening(id);
    if (state.drawerKey !== key) return;
    renderScreeningDrawer(data);
  } catch (error) {
    if (state.drawerKey !== key) return;
    updateDrawer({ title: '初筛详情', sub: '加载失败', body: inlineError(error), actions: '' });
  }
}

function renderScreeningDrawer(data) {
  const symptoms = data.symptoms.length ? `<table class="symptom-table">
    <thead><tr><th>症状</th><th>分级</th><th>时长</th><th>频次</th><th>备注</th></tr></thead>
    <tbody>${data.symptoms.map((item) => `
      <tr>
        <td>${esc(item.label)}${item.severe ? ' <span class="tag tag--danger">严重</span>' : ''}</td>
        <td>${item.grade === 'vet' ? pill('就医', 'danger', '!') : item.grade === 'observe' ? pill('观察', 'warning', '!') : pill('未分级', 'mist', '•')}</td>
        <td>${esc(item.duration || '—')}</td>
        <td>${esc(item.frequency || '—')}</td>
        <td>${esc(item.notes || '—')}</td>
      </tr>`).join('')}</tbody>
  </table>` : `<p class="empty-sub">本次初筛没有记录具体症状。</p>`;

  const advice = data.advice;
  const adviceBlock = advice
    ? `<div class="note-block">${esc(advice.text || '')}${advice.tips?.length ? `<ul class="bullet-list">${advice.tips.map((tip) => `<li>${esc(tip)}</li>`).join('')}</ul>` : ''}
        <div class="cell-sub mt-8">来源：${advice.source === 'llm' ? '模型生成 + 规则守卫' : '规则模板'}${advice.template_version ? ` · ${esc(advice.template_version)}` : ''}</div></div>`
    : data.llm_advice
      ? `<div class="note-block">${esc(data.llm_advice)}</div>`
      : `<p class="empty-sub">这条记录还没有生成建议文案。</p>`;

  updateDrawer({
    title: `初筛 #${data.id}`,
    sub: `${data.pet?.name || '未知猫咪'} · ${data.owner?.nickname || '未知主人'} · ${fmtDateTime(data.created_at)}`,
    body: `
      <div class="inline-flex-row">
        ${statePill(data.state)}
        ${data.redline_hit ? pill('命中红线', 'danger', '!') : pill('未命中红线', 'success', '✓')}
        <span class="cell-muted">规则版本 ${esc(data.rules_version)}</span>
      </div>

      ${data.redlines.length ? `<div class="drawer-section"><div class="note-block note-block--danger">
        <strong>红线信号</strong><br>${data.redlines.map((item) => esc(item.label)).join('、')}
      </div></div>` : ''}

      <div class="drawer-section">
        <div class="drawer-section-title">档案</div>
        <div class="info-list">
          <div class="info-row"><span class="info-key">猫咪</span><span class="info-val"><strong>${esc(data.pet?.name || '—')}</strong> · ${esc(data.pet?.breed || '品种未填')} · ${esc(sexLabel(data.pet?.sex))}</span></div>
          <div class="info-row"><span class="info-key">主人</span><span class="info-val">${esc(data.owner?.nickname || '—')} · ${esc(data.owner?.email || '未绑定邮箱')}</span></div>
          <div class="info-row"><span class="info-key">精神 / 食欲</span><span class="info-val">${esc(spiritLabel(data.spirit))} / ${esc(appetiteLabel(data.appetite))}</span></div>
          <div class="info-row"><span class="info-key">媒体存证</span><span class="info-val">${fmtInt(data.media_count)} 个</span></div>
          <div class="info-row"><span class="info-key">记录时间</span><span class="info-val">${fmtDateTime(data.created_at)}</span></div>
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">症状与分级</div>
        ${symptoms}
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">建议文案 <span class="cell-sub">AI 不参与分级</span></div>
        ${adviceBlock}
      </div>`,
    actions: '',
  });
}

/* ------------------------------------------------------------------ */
/* 状态确认弹窗                                                        */

function openStatusModal(id, next, name) {
  closeModal();
  const suspending = next === 'suspended';
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.id = 'admin-modal';
  modal.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <h2 id="modal-title">${suspending ? '停用这个账号？' : '恢复这个账号？'}</h2>
      <p>${suspending
        ? '停用后该账号立即无法登录，App 内所有会话失效；猫咪档案、初筛记录与聊天会保留，可随时恢复。恢复后需要重新登录。'
        : '恢复后该账号可以重新登录，已有档案与记录保持不变。'}</p>
      <div class="modal-target"><strong>${esc(name)}</strong> · 用户 #${id}</div>
      <div class="modal-actions">
        <button class="btn btn-ghost" type="button" data-action="close-modal">取消</button>
        <button class="btn ${suspending ? 'btn-warn' : 'btn-primary'}" type="button" data-action="confirm-status"
          data-id="${id}" data-next="${next}" data-name="${esc(name)}">${suspending ? '确认停用' : '确认恢复'}</button>
      </div>
    </div>`;
  modal.addEventListener('click', (event) => {
    if (event.target === modal) closeModal();
  });
  document.body.append(modal);
  lockBody();
  modal.querySelector('[data-action="close-modal"]')?.focus();
}

function closeModal() {
  document.getElementById('admin-modal')?.remove();
  unlockBody();
}

async function confirmStatus(button) {
  const { id, next, name } = button.dataset;
  const suspending = next === 'suspended';
  button.disabled = true;
  button.textContent = '处理中…';
  try {
    await adminApi.setUserStatus(id, next);
    closeModal();
    toast(suspending ? `已停用 ${name}` : `已恢复 ${name}`, 'success');
    await openUser(id);
    if (state.route === 'users' && document.getElementById('list-body')) loadUsers();
  } catch (error) {
    button.disabled = false;
    button.textContent = suspending ? '确认停用' : '确认恢复';
    toast(error.message || '操作失败', 'danger');
  }
}

/* ------------------------------------------------------------------ */
/* 全局事件                                                            */

document.addEventListener('click', (event) => {
  const range = event.target.closest('[data-range]');
  if (range) {
    const days = Number(range.dataset.days);
    if (range.dataset.range === 'overview') state.overviewDays = days;
    if (range.dataset.range === 'usage') state.usageDays = days;
    renderRoute();
    return;
  }
  const actionElement = event.target.closest('[data-action]');
  if (!actionElement) return;
  const action = actionElement.dataset.action;
  if (action === 'refresh') renderRoute();
  else if (action === 'retry') renderRoute();
  else if (action === 'retry-boot') boot();
  else if (action === 'logout') {
    adminApi.logout();
    state.session = null;
    history.replaceState(null, '', location.pathname);
    closeDrawer();
    closeModal();
    renderLogin();
  } else if (action === 'close-drawer') closeDrawer();
  else if (action === 'close-modal') closeModal();
  else if (action === 'open-user') openUser(actionElement.dataset.id);
  else if (action === 'open-screening') openScreening(actionElement.dataset.id);
  else if (action === 'ask-status') {
    openStatusModal(actionElement.dataset.id, actionElement.dataset.next, actionElement.dataset.name);
  } else if (action === 'confirm-status') confirmStatus(actionElement);
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  if (document.getElementById('admin-modal')) closeModal();
  else if (document.getElementById('admin-drawer')) closeDrawer();
});

window.addEventListener('hashchange', () => {
  if (state.session) renderRoute();
  else boot();
});

window.addEventListener('admin:session-expired', (event) => {
  state.session = null;
  closeDrawer();
  closeModal();
  renderLogin(event.detail || '登录已过期，请重新登录。');
});

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();

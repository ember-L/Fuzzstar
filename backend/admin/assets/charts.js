/* 轻量图表：纯 SVG、零依赖、严格平面（无渐变 / 无阴影）。
   颜色取自 App 的 Foundations，避免引入第二套色板。 */

export const CHART_COLORS = {
  brand: '#FEAE36',
  accent: '#A34400',
  strong: '#89552F',
  danger: '#B42318',
  success: '#166534',
  warning: '#8A4B00',
  timestamp: '#A78976',
  grid: 'rgba(217,191,165,0.55)',
  area: '#FFF0DF',
  empty: '#F3EEE9',
};

const SERIES_COLORS = [
  CHART_COLORS.brand,
  CHART_COLORS.accent,
  CHART_COLORS.strong,
  CHART_COLORS.success,
  CHART_COLORS.warning,
];

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

function niceMax(value) {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const exponent = Math.floor(Math.log10(value));
  const fraction = value / (10 ** exponent);
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return nice * (10 ** exponent);
}

function compact(value) {
  if (value === null || value === undefined) return '—';
  const abs = Math.abs(value);
  if (abs >= 1000000) return `${(value / 1000000).toFixed(abs >= 10000000 ? 0 : 1)}m`;
  if (abs >= 10000) return `${(value / 1000).toFixed(0)}k`;
  if (abs >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(Number.isInteger(value) ? value : Number(value.toFixed(2)));
}

function shortDay(label) {
  const text = String(label ?? '');
  return text.length >= 10 ? text.slice(5) : text;
}

export function dot(color, size = 8) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">`
    + `<circle cx="${size / 2}" cy="${size / 2}" r="${size / 2}" fill="${color}"/></svg>`;
}

/**
 * 折线图。
 * @param {{labels: string[], series: {name: string, values: number[], color?: string}[], height?: number, yFormat?: (v:number)=>string, fill?: boolean, unit?: string}} options
 */
export function lineChart({ labels = [], series = [], height = 226, yFormat = compact, fill = true, unit = '', integer = false }) {
  const width = 760;
  const pad = { top: 14, right: 16, bottom: 28, left: 46 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const count = labels.length;
  if (!count || !series.length) return emptyChart(height);

  const allValues = series.flatMap((item) => item.values || []);
  let max = niceMax(Math.max(1, ...allValues.map((value) => Number(value) || 0)));
  if (integer) {
    // Keep count ticks whole: step is a 1/2/5 decade value, so four steps stay integral.
    const step = Math.max(1, niceMax(max / 4));
    max = step * 4;
  }
  const x = (index) => pad.left + (count === 1 ? plotWidth / 2 : (index / (count - 1)) * plotWidth);
  const y = (value) => pad.top + (1 - (Number(value) || 0) / max) * plotHeight;

  const gridLines = [];
  for (let step = 0; step <= 4; step += 1) {
    const value = (max / 4) * step;
    const yPos = y(value);
    gridLines.push(
      `<line class="chart-grid" x1="${pad.left}" y1="${yPos.toFixed(1)}" x2="${width - pad.right}" y2="${yPos.toFixed(1)}"/>`
      + `<text class="chart-axis" x="${pad.left - 8}" y="${(yPos + 3.5).toFixed(1)}" text-anchor="end">${esc(yFormat(value))}</text>`,
    );
  }

  const tickIndexes = count <= 7
    ? labels.map((_, index) => index)
    : Array.from({ length: 6 }, (_, index) => Math.round((index / 5) * (count - 1)));
  const xLabels = [...new Set(tickIndexes)].map((index) => (
    `<text class="chart-axis" x="${x(index).toFixed(1)}" y="${height - 8}" text-anchor="middle">${esc(shortDay(labels[index]))}</text>`
  ));

  const paths = series.map((item, seriesIndex) => {
    const color = item.color || SERIES_COLORS[seriesIndex % SERIES_COLORS.length];
    const values = item.values || [];
    const points = values.map((value, index) => `${x(index).toFixed(1)},${y(value).toFixed(1)}`);
    const linePath = `M${points.join(' L')}`;
    let area = '';
    if (fill && seriesIndex === 0) {
      const base = pad.top + plotHeight;
      area = `<path d="M${x(0).toFixed(1)},${base} L${points.join(' L')} L${x(count - 1).toFixed(1)},${base} Z" fill="${CHART_COLORS.area}"/>`;
    }
    const dots = values.map((value, index) => (
      `<circle class="chart-hit" cx="${x(index).toFixed(1)}" cy="${y(value).toFixed(1)}" r="9">`
      + `<title>${esc(labels[index])} · ${esc(item.name)} ${esc(yFormat(value))}${esc(unit)}</title></circle>`
    )).join('');
    const last = values.length - 1;
    const endDot = last >= 0
      ? `<circle class="chart-dot" cx="${x(last).toFixed(1)}" cy="${y(values[last]).toFixed(1)}" r="3.6" fill="${color}"/>`
      : '';
    return `${area}<path class="chart-line" d="${linePath}" stroke="${color}"/>${dots}${endDot}`;
  }).join('');

  const legend = series.map((item, index) => {
    const color = item.color || SERIES_COLORS[index % SERIES_COLORS.length];
    return `<span class="legend-item">${dot(color)}${esc(item.name)}</span>`;
  }).join('');

  return `
    <div>
      <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(series.map((item) => item.name).join('、'))}趋势图">
        ${gridLines.join('')}
        ${xLabels.join('')}
        ${paths}
      </svg>
      <div class="chart-legend">${legend}</div>
    </div>`;
}

export function emptyChart() {
  return `<div class="empty"><div class="empty-mark" aria-hidden="true">✦</div><p class="empty-sub">暂无可以绘制趋势的数据。</p></div>`;
}

/**
 * 环形图，items: {name, value, color}
 */
export function donut({ items = [], size = 168, thickness = 18, centerLabel = '合计' }) {
  const total = items.reduce((sum, item) => sum + (Number(item.value) || 0), 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  const arcs = items.filter((item) => Number(item.value) > 0).map((item) => {
    const value = Number(item.value) || 0;
    const length = (value / total) * circumference;
    const visible = Math.max(length - 2.5, 0.5);
    const arc = `<circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="${item.color}" `
      + `stroke-width="${thickness}" stroke-dasharray="${visible.toFixed(2)} ${(circumference - visible).toFixed(2)}" `
      + `stroke-dashoffset="${(-offset).toFixed(2)}" transform="rotate(-90 ${size / 2} ${size / 2})">`
      + `<title>${esc(item.name)} ${value}</title></circle>`;
    offset += length;
    return arc;
  }).join('');

  const emptyRing = total === 0
    ? `<circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="${CHART_COLORS.empty}" stroke-width="${thickness}"/>`
    : '';

  return `
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${esc(centerLabel)}分布">
      <circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="${CHART_COLORS.empty}" stroke-width="${thickness}"/>
      ${arcs || emptyRing}
      <text x="${size / 2}" y="${size / 2 - 2}" text-anchor="middle" font-size="26" font-weight="600" fill="#4B2617">${total}</text>
      <text x="${size / 2}" y="${size / 2 + 20}" text-anchor="middle" font-size="12" fill="#805535">${esc(centerLabel)}</text>
    </svg>`;
}

export function sparkline(values = [], { width = 96, height = 30, color = CHART_COLORS.brand } = {}) {
  if (!values.length) return '';
  const max = Math.max(1, ...values.map((value) => Number(value) || 0));
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
    const y = height - 3 - ((Number(value) || 0) / max) * (height - 6);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const last = values[values.length - 1];
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" aria-hidden="true">`
    + `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`
    + `<circle cx="${width}" cy="${(height - 3 - ((Number(last) || 0) / max) * (height - 6)).toFixed(1)}" r="2.4" fill="${color}"/>`
    + '</svg>';
}

/** 迷你横条（HTML 内嵌 SVG，宽度不依赖内联 style）。 */
export function barSvg(value, max, color = CHART_COLORS.brand) {
  const ratio = max > 0 ? Math.max(0, Math.min(1, Number(value) / max)) : 0;
  const width = Math.max(ratio * 100, ratio > 0 ? 2 : 0);
  return `<svg width="100%" height="8" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">`
    + `<rect width="${width.toFixed(1)}" height="8" rx="4" fill="${color}"/></svg>`;
}

/**
 * لوحات الأدوات — المجموعة الثانية:
 *   تحسينات البكسل (مع المنحنيات) · الفلاتر
 */

import { state, setImageFromDataUrl, setPreview, clearPreview } from '../core/state.js';
import { api, toDataUrl } from '../core/api.js';
import { $, $$, toast, status, withBusy, makeSlider, val, num, checked } from './helpers.js';
import { applyResult } from './panels.js';

const needImage = () => {
  if (!state.image) { toast('افتح صورة أولاً.', 'warn'); return false; }
  return true;
};

/* ═══════════════════ تحسينات البكسل ═══════════════════ */

const ADJUST_KEYS = ['brightness', 'contrast', 'saturation', 'vibrance', 'exposure',
  'gamma', 'temperature', 'tint', 'hue'];

let sliders = {};
let curvesPoints = [];        // نقاط المنحنيات [x,y] بمجال 0..1
let previewTimer = null;
let previewBase = null;       // الصورة التي بُنيت عليها المعاينة الحالية

export function initAdjust() {
  // بناء المنزلقات
  $$('#panels [data-panel="adjust"] .slider').forEach((c) => {
    const s = makeSlider(c);
    sliders[s.key] = s;
    c.addEventListener('slider', () => schedulePreview());
  });

  // المنحنيات
  initCurves();

  // معاينة فورية منخفضة الدقة
  const live = $('#adj-live');
  live.addEventListener('change', () => { if (!live.checked) clearPreview(); });

  $('#btn-adj-reset').addEventListener('click', () => {
    Object.values(sliders).forEach((s) => s.reset());
    curvesPoints = [];
    drawCurves();
    $('#adj-wb').value = '';
    $('#lv-black').value = 0; $('#lv-gamma').value = 1; $('#lv-white').value = 1;
    clearPreview();
    status('أُعيدت الضبوطات إلى قيمها المحايدة.', 'ok');
  });

  $('#btn-auto-levels').addEventListener('click', () => run(() => api.autoLevels(state.image), 'مستويات تلقائية'));
  $('#btn-auto-contrast').addEventListener('click', () => run(() => api.autoContrast(state.image), 'تباين تلقائي'));
  $('#btn-invert').addEventListener('click', () => run(() => api.invert(state.image), 'عكس الألوان'));
  $('#btn-grayscale').addEventListener('click', () => run(() => api.grayscale(state.image), 'تدرّج رمادي'));
  $('#btn-posterize').addEventListener('click', () => run(() => api.posterize(state.image, 5), 'بوسترة'));
  $('#btn-threshold-otsu').addEventListener('click', () => run(() => api.threshold(state.image, { mode: 'otsu' }), 'عتبة Otsu'));

  $('#btn-adj-apply').addEventListener('click', async () => {
    if (!needImage()) return;
    const params = collectAdjust();
    if (!Object.keys(params).length) { toast('لا توجد تعديلات لتطبيقها.', 'warn'); return; }
    await run(() => api.adjust(state.image, params), 'تطبيق التعديلات');
    Object.values(sliders).forEach((s) => s.reset());
    curvesPoints = []; drawCurves();
    $('#adj-wb').value = '';
    $('#lv-black').value = 0; $('#lv-gamma').value = 1; $('#lv-white').value = 1;
    clearPreview();
  });
}

/** تجميع معاملات الضبط غير المحايدة */
function collectAdjust() {
  const p = {};
  for (const k of ADJUST_KEYS) {
    const s = sliders[k];
    if (s && !s.isDefault()) p[k] = s.value;
  }
  const wb = val('adj-wb');
  if (wb) p.white_balance = wb;
  const ib = num('lv-black', 0), ig = num('lv-gamma', 1), iw = num('lv-white', 1);
  if (ib !== 0 || ig !== 1 || iw !== 1) p.levels = { in_black: ib, gamma: ig, in_white: iw };
  if (curvesPoints.length >= 2) p.curves = curvesPoints;
  return p;
}

/** معاينة مؤجَّلة (debounced) حتى لا نُثقل الخادم أثناء السحب */
function schedulePreview() {
  if (!$('#adj-live')?.checked || !state.image) return;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 260);
}

async function runPreview() {
  const params = collectAdjust();
  if (!Object.keys(params).length) { clearPreview(); return; }
  try {
    const resp = await api.adjust(state.image, params);
    setPreview(toDataUrl(resp));
    status(`معاينة — ${resp.meta.elapsed_ms} ملّي ثانية`, '');
  } catch (e) {
    // المعاينة غير حرجة: نتجاهل أخطاءها بهدوء
    console.warn('preview failed', e.message);
  }
}

/** تنفيذ عملية وتطبيقها نهائياً */
async function run(fn, label) {
  if (!needImage()) return;
  await withBusy(label, async () => {
    const resp = await fn();
    clearPreview();
    await applyResult(resp, label);
  });
}

/* ═══════════════════ محرّر المنحنيات ═══════════════════ */
function initCurves() {
  const c = $('#curves-canvas');
  if (!c) return;
  const ctx = c.getContext('2d');
  curvesPoints = [[0, 0], [1, 1]];

  const toLocal = (e) => {
    const r = c.getBoundingClientRect();
    return [
      Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      Math.min(1, Math.max(0, 1 - (e.clientY - r.top) / r.height)),
    ];
  };

  c.addEventListener('click', (e) => {
    const [x, y] = toLocal(e);
    // استبدال نقطة قريبة بدل إضافة جديدة
    const near = curvesPoints.findIndex((p) => Math.abs(p[0] - x) < 0.04);
    if (near >= 0) curvesPoints[near] = [x, y];
    else curvesPoints.push([x, y]);
    curvesPoints.sort((a, b) => a[0] - b[0]);
    curvesPoints[0] = [0, curvesPoints[0][1]];
    curvesPoints[curvesPoints.length - 1] = [1, curvesPoints[curvesPoints.length - 1][1]];
    drawCurves();
    schedulePreview();
  });

  $('#btn-curves-reset').addEventListener('click', () => {
    curvesPoints = [[0, 0], [1, 1]];
    drawCurves();
    clearPreview();
  });
  $('#curves-channel').addEventListener('change', schedulePreview);

  drawCurves();
}

function drawCurves() {
  const c = $('#curves-canvas');
  if (!c) return;
  const ctx = c.getContext('2d');
  const W = c.width, H = c.height;
  ctx.clearRect(0, 0, W, H);

  // الشبكة
  ctx.strokeStyle = 'rgba(255,255,255,.07)';
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    ctx.beginPath(); ctx.moveTo((W * i) / 4, 0); ctx.lineTo((W * i) / 4, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, (H * i) / 4); ctx.lineTo(W, (H * i) / 4); ctx.stroke();
  }
  // الخط المرجعي
  ctx.strokeStyle = 'rgba(255,255,255,.2)';
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(0, H); ctx.lineTo(W, 0); ctx.stroke();
  ctx.setLineDash([]);

  // المنحنى (استيفاء ناعم)
  if (curvesPoints.length >= 2) {
    ctx.strokeStyle = '#5b8cff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i <= 100; i++) {
      const x = i / 100;
      const y = interp(x);
      const px = x * W, py = H - y * H;
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.stroke();
  }
  // النقاط
  ctx.fillStyle = '#ffd166';
  for (const [x, y] of curvesPoints) {
    ctx.beginPath();
    ctx.arc(x * W, H - y * H, 4.5, 0, Math.PI * 2);
    ctx.fill();
  }
}

/** استيفاء تكعيبي رتيب مبسّط (Catmull-Rom) لنقاط المنحنى */
function interp(x) {
  const pts = curvesPoints;
  if (x <= pts[0][0]) return pts[0][1];
  if (x >= pts[pts.length - 1][0]) return pts[pts.length - 1][1];
  let i = 0;
  while (i < pts.length - 1 && pts[i + 1][0] < x) i++;
  const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
  const t = (x - p1[0]) / Math.max(1e-6, p2[0] - p1[0]);
  const t2 = t * t, t3 = t2 * t;
  const y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t +
    (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
    (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3);
  return Math.min(1, Math.max(0, y));
}

/* ═══════════════════ الفلاتر ═══════════════════ */
const ART_FILTERS = [
  ['edges', 'حواف'], ['sobel', 'سوبل'], ['emboss', 'نحت'],
  ['oil_paint', 'زيتي'], ['sketch', 'رصاص'], ['pencil_color', 'رصاص ملوّن'],
  ['halftone', 'نقاط'], ['pixelate', 'فسيفساء'], ['vignette', 'تظليل'],
  ['grain', 'حبوب'], ['glow', 'توهّج'], ['hdr_look', 'HDR'],
];

const FILTER_PARAMS = {
  edges: { low: 50, high: 150 }, sobel: { scale: 1 }, emboss: { strength: 1 },
  oil_paint: { radius: 5 }, sketch: { threshold: 8 }, pencil_color: { sigma: 0.06 },
  halftone: { dot_size: 7 }, pixelate: { block: 14 }, vignette: { strength: 0.6 },
  grain: { amount: 0.25 }, glow: { amount: 0.5 }, hdr_look: { strength: 0.7 },
};

export function initFilters() {
  // المنزلقات الخاصة بالفلاتر (لا تُرسل مباشرة)
  $$('#panels [data-panel="filters"] .slider').forEach((c) => {
    const s = makeSlider(c);
    sliders[s.key] = s;
  });

  $('#btn-blur').addEventListener('click', () => {
    if (!needImage()) return;
    run(() => api.blur(state.image, {
      mode: val('blur-mode', 'gaussian'),
      radius: sliders['blur-radius']?.value ?? 3,
      angle: 25,
      strength: 1,
    }), `تنعيم ${val('blur-mode')}`);
  });

  $('#btn-sharpen').addEventListener('click', () => {
    if (!needImage()) return;
    run(() => api.sharpen(state.image, {
      mode: val('sharp-mode', 'unsharp'),
      amount: sliders['sharp-amount']?.value ?? 1,
      radius: 2,
    }), `تحديد ${val('sharp-mode')}`);
  });

  $('#btn-denoise').addEventListener('click', () => run(() => api.denoise(state.image, { strength: 1.2 }), 'تقليل الضوضاء'));
  $('#btn-surface-smooth').addEventListener('click', () => run(() => api.surfaceSmooth(state.image, { strength: 1.2, detail: 0.45 }), 'تنعيم بشرة'));

  // شبكة الفلاتر الفنية
  const grid = $('#filter-grid');
  for (const [name, label] of ART_FILTERS) {
    const b = document.createElement('button');
    b.className = 'chip';
    b.textContent = label;
    b.title = name;
    b.addEventListener('click', () => run(() => api.filter(state.image, name, FILTER_PARAMS[name] || {}), `فلتر ${label}`));
    grid.appendChild(b);
  }
}

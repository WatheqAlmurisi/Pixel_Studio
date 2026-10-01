/**
 * عميل الاتصال بالخادم (API Client).
 * ==================================
 * كل الطلبات JSON وتحتوي الصورة كـ Base64. الأخطاء تُحوَّل إلى استثناء
 * برسالة عربية جاهزة للعرض.
 */

const BASE = '/api/v1';

/** أوقات الاستجابة الأخيرة (تُعرض في شريط الحالة) */
export const stats = { lastMs: 0, calls: 0, failures: 0 };

/**
 * تنفيذ طلب POST وإرجاع الاستجابة المفكوكة.
 * @param {string} path  المسار بعد /api/v1
 * @param {object} body  جسم الطلب
 */
export async function post(path, body) {
  const started = performance.now();
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (err) {
    stats.failures++;
    throw new ApiError('تعذّر الاتصال بالخادم. تأكد من تشغيل الخدمة الخلفية.', 'network_error', 0);
  }
  stats.lastMs = Math.round(performance.now() - started);
  stats.calls++;

  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { /* استجابة غير JSON */ }

  if (!res.ok) {
    stats.failures++;
    const e = data.error || {};
    let msg = e.message || `فشل الطلب (HTTP ${res.status})`;
    if (Array.isArray(e.detail)) {
      msg += ' — ' + e.detail.map((d) => `${d.field}: ${d.message}`).join('، ');
    } else if (typeof e.detail === 'string' && e.detail) {
      msg += ` — ${e.detail}`;
    }
    throw new ApiError(msg, e.code || 'http_error', res.status);
  }
  return data;
}

/** تنفيذ طلب GET */
export async function get(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString();
  const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ''}`);
  if (!res.ok) {
    let msg = `فشل الطلب (HTTP ${res.status})`;
    try {
      const d = await res.json();
      if (d.error?.message) msg = d.error.message;
    } catch { /* تجاهل */ }
    throw new ApiError(msg, 'http_error', res.status);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.blob();
}

/** تحويل استجابة الخادم (Base64) إلى data URL */
export function toDataUrl(resp) {
  const mime = resp?.meta?.mime || 'image/png';
  return `data:${mime};base64,${resp.image}`;
}

/** فحص صحة الخادم وقدراته */
export async function health() {
  return get('/health');
}

/** تنزيل ملف ثنائي من الخادم */
export async function download(imageB64, filename, format, quality) {
  const res = await fetch(`${BASE}/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: imageB64, filename, format, quality }),
  });
  if (!res.ok) {
    let msg = `فشل التنزيل (HTTP ${res.status})`;
    try { const d = await res.json(); if (d.error?.message) msg = d.error.message; } catch { /* */ }
    throw new ApiError(msg, 'download_error', res.status);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return blob.size;
}

/** خطأ موحّد */
export class ApiError extends Error {
  constructor(message, code = 'error', status = 0) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

/* ═══════════ wrappers مختصرة لنقاط كثيرة الاستخدام ═══════════ */

export const api = {
  convert: (image, o = {}) => post('/convert', { image, ...o }),
  crop: (image, box, unit = 'px') => post('/geometry/crop', { image, box, unit }),
  cropAspect: (image, aspect, anchor = 'center') => post('/geometry/crop-aspect', { image, aspect, anchor }),
  cropAuto: (image, o = {}) => post('/geometry/crop-auto', { image, ...o }),
  cropContent: (image, padding = 0) => post('/geometry/crop-content', { image, padding }),
  resize: (image, o = {}) => post('/geometry/resize', { image, ...o }),
  rotate: (image, angle, o = {}) => post('/geometry/rotate', { image, angle, ...o }),
  rotate90: (image, times = 1) => post('/geometry/rotate90', { image, times }),
  flip: (image, direction = 'horizontal') => post('/geometry/flip', { image, direction }),
  transpose: (image, mode = 'transpose') => post('/geometry/transpose', { image, mode }),
  deskew: (image) => post('/geometry/deskew', { image }),
  perspective: (image, src, dst) => post('/geometry/perspective', { image, src, dst }),
  pad: (image, o = {}) => post('/geometry/pad', { image, ...o }),
  border: (image, o = {}) => post('/geometry/border', { image, ...o }),
  shadow: (image, o = {}) => post('/geometry/shadow', { image, ...o }),
  canvas: (image, o = {}) => post('/geometry/canvas', { image, ...o }),

  adjust: (image, o = {}) => post('/pixel/adjust', { image, ...o }),
  curves: (image, points, channel = 'rgb') => post('/pixel/curves', { image, points, channel }),
  levels: (image, o = {}) => post('/pixel/levels', { image, ...o }),
  threshold: (image, o = {}) => post('/pixel/threshold', { image, ...o }),
  autoLevels: (image) => post('/pixel/auto-levels', { image }),
  autoContrast: (image) => post('/pixel/auto-contrast', { image }),
  invert: (image) => post('/pixel/invert', { image }),
  grayscale: (image) => post('/pixel/grayscale', { image }),
  posterize: (image, levels = 4) => post('/pixel/posterize', { image, name: 'p', params: { levels } }),

  blur: (image, o = {}) => post('/filters/blur', { image, ...o }),
  sharpen: (image, o = {}) => post('/filters/sharpen', { image, ...o }),
  denoise: (image, o = {}) => post('/filters/denoise', { image, ...o }),
  surfaceSmooth: (image, o = {}) => post('/filters/surface-smooth', { image, ...o }),
  filter: (image, name, params = {}) => post('/filters/apply', { image, name, params }),
  filterCatalog: () => get('/filters/catalog'),

  removeBg: (image, o = {}) => post('/segmentation/remove-background', { image, ...o }),
  previewMask: (image, o = {}) => post('/segmentation/preview-mask', { image, ...o }),
  restoreOld: (image, o = {}) => post('/pro/restore-old-photo', { image, ...o }),
  retouchFaces: (image, o = {}) => post('/pro/retouch-faces', { image, ...o }),
  documentScan: (image, o = {}) => post('/pro/document-scan', { image, ...o }),
  segMethods: () => get('/segmentation/methods'),
  maskOnly: (image, o = {}) => post('/segmentation/preview-mask', { image, ...o }),
  applyMask: (image, mask, invert = false) => post('/segmentation/mask', { image, mask, invert }),

  blend: (image, second, o = {}) => post('/composite/blend', { image, second, ...o }),
  blendSeamless: (image, second, o = {}) => post('/composite/blend-seamless', { image, second, ...o }),
  merge: (images, o = {}) => post('/composite/merge', { images, ...o }),
  pip: (image, second, o = {}) => post('/composite/pip', { image, second, ...o }),
  watermarkText: (image, o = {}) => post('/composite/watermark-text', { image, ...o }),
  blendModes: () => get('/composite/blend-modes'),

  creative: (image, name, params = {}) => post('/creative/apply', { image, name, params }),
  doubleExposure: (image, second, o = {}) => post('/creative/double-exposure', { image, second, ...o }),
  creativeCatalog: () => get('/creative/catalog'),

  backgrounds: (category) => get('/backgrounds', { category }),
  backgroundPreviewUrl: (id, size = 160) => `${BASE}/backgrounds/preview/${id}?size=${size}`,
  composeBackground: (image, o = {}) => post('/backgrounds/compose', { image, ...o }),
  generateBackground: (background, size = 1200) => post('/backgrounds/generate', { background, size }),

  analyze: (image) => post('/analysis', { image }),
  suggestions: (image) => post('/analysis/suggestions', { image }),

  pipeline: (image, steps, strict = true) => post('/pipeline/run', { image, steps, strict }),
  batch: (images, steps, o = {}) => post('/pipeline/batch', { images, steps, ...o }),
  pipelineOps: () => get('/pipeline/operations'),
};

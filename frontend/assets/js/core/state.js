/**
 * الحالة المركزية للتطبيق (State + History).
 * ==========================================
 * مصدر الحقيقة الوحيد للصورة الحالية وسجل العمليات.
 * كل تعديل يمرّ عبر commit() ليُسجَّل في السجل مع صورة مصغّرة.
 */

const MAX_HISTORY = 30;

export const state = {
  /** الصورة الحالية كـ data URL (مصدر الحقيقة) */
  image: null,
  /** الصورة الأصلية عند أول فتح (للمقارنة) */
  original: null,
  width: 0,
  height: 0,
  fileName: 'untitled.png',
  format: 'png',
  mime: 'image/png',
  sizeBytes: 0,

  /** طبقة الرسم المؤقتة (data URL أو null) */
  drawLayer: null,

  /** الطبقات الإضافية فوق الصورة الأصل (رسم/نص/تحديد) */
  layers: [],

  /** السجل */
  history: [],
  historyIndex: -1,

  /** الطبقة المحددة حالياً (نص قابل للتعديل) أو null */
  selectedLayer: null,

  /** إعدادات العرض */
  zoom: 1,
  fitZoom: 1,

  /** الصورة الثانية للدمج */
  second: null,

  /** الخلفية المختارة من المكتبة */
  selectedBackground: null,

  /** صور الدفعة */
  batchImages: [],

  /** سلسلة عمليات الدفعة */
  batchSteps: [],

  /** آخر نتيجة تحليل */
  analysis: null,

  /** هل الخادم متاح؟ */
  online: false,
  capabilities: null,
};

const listeners = new Set();

/** الاشتراك في تغيّرات الحالة */
export function onChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** بثّ حدث تغيّر */
export function emit(kind = 'image', payload = null) {
  for (const fn of listeners) {
    try { fn(kind, payload); } catch (e) { console.error('[state]', e); }
  }
}

/* ═══════════════════ إدارة الصورة ═══════════════════ */

/** تحميل صورة من data URL أو رابط، مع تحديث الأبعاد */
export function setImageFromDataUrl(dataUrl, { label = 'فتح', push = true, asOriginal = false } = {}) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      state.image = dataUrl;
      state.width = img.naturalWidth;
      state.height = img.naturalHeight;
      const m = /^data:([^;]+);/.exec(dataUrl);
      if (m) state.mime = m[1];
      state.sizeBytes = Math.round((dataUrl.length - (dataUrl.indexOf(',') + 1)) * 0.75);
      state.format = mimeToExt(state.mime);
      if (asOriginal || !state.original) state.original = dataUrl;
      if (push) commit(label);
      emit('image', { label });
      resolve(img);
    };
    img.onerror = () => reject(new Error('تعذّر قراءة الصورة في المتصفح.'));
    img.src = dataUrl;
  });
}

/** تعيين الصورة دون دفعها إلى السجل (تُستخدم في المعاينات المؤقتة) */
export function setPreview(dataUrl) {
  state.previewImage = dataUrl;
  emit('preview');
}
export function clearPreview() {
  state.previewImage = null;
  emit('preview');
}
/** الصورة المعروضة حالياً (المعاينة إن وُجدت) */
export function currentImage() {
  return state.previewImage || state.image;
}

function mimeToExt(mime) {
  const map = {
    'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'image/bmp': 'bmp',
    'image/tiff': 'tiff', 'image/gif': 'gif', 'image/x-icon': 'ico', 'image/avif': 'avif',
    'image/x-portable-pixmap': 'ppm',
  };
  return map[mime] || 'png';
}

/* ═══════════════════ السجل (History) ═══════════════════ */

/** نسخ طبقة نسخاً عميقاً — يفصل لقطة السجل عن الطبقة الحيّة عند التعديل في المكان */
function cloneLayer(l) {
  return { ...l, meta: l.meta ? { ...l.meta, box: l.meta.box ? { ...l.meta.box } : null } : l.meta };
}

/** دفع حالة جديدة إلى السجل */
export function commit(label = 'تعديل') {
  // حذف أي حالات «مستقبلية» بعد المؤشر الحالي
  if (state.historyIndex < state.history.length - 1) {
    state.history = state.history.slice(0, state.historyIndex + 1);
  }
  state.history.push({
    image: state.image,
    label,
    width: state.width,
    height: state.height,
    layers: state.layers.map(cloneLayer),
    thumb: null,
    at: Date.now(),
  });
  if (state.history.length > MAX_HISTORY) state.history.shift();
  state.historyIndex = state.history.length - 1;
  emit('history');
}

/**
 * تحديث المدخل الحالي في السجل **في مكانه** — بلا نسخة جديدة.
 * تُستخدم بعد عمليات الطبقات (حذف/إخفاء/ترتيب/تعديل نص) كي تعود الصورة
 * إلى شكلها السابق دون إنشاء خطوة إضافية في السجل.
 */
export function updateCurrentHistory() {
  const entry = state.history[state.historyIndex];
  if (!entry) return false;
  entry.image = state.image;
  entry.width = state.width;
  entry.height = state.height;
  entry.layers = state.layers.map(cloneLayer);
  entry.thumb = null;                 // إبطال الصورة المصغّرة المحفوظة
  emit('history');
  return true;
}

/**
 * حذف خطوة من السجل (زر × بجانب كل صورة في القائمة الجانبية).
 * إن حُذفت الخطوة الحالية ينتقل المؤشر إلى أقرب خطوة باقية.
 * لا يمكن حذف آخر خطوة متبقية.
 */
export function deleteHistory(index) {
  if (state.history.length <= 1) return false;
  if (index < 0 || index >= state.history.length) return false;
  state.history.splice(index, 1);
  if (index < state.historyIndex) state.historyIndex -= 1;
  else if (index === state.historyIndex) state.historyIndex = Math.min(index, state.history.length - 1);
  applyHistoryEntry();
  return true;
}

/** هل يمكن التراجع؟ */
export const canUndo = () => state.historyIndex > 0;
/** هل يمكن الإعادة؟ */
export const canRedo = () => state.historyIndex < state.history.length - 1;

/** التراجع خطوة */
export function undo() {
  if (!canUndo()) return false;
  state.historyIndex -= 1;
  applyHistoryEntry();
  return true;
}

/** الإعادة خطوة */
export function redo() {
  if (!canRedo()) return false;
  state.historyIndex += 1;
  applyHistoryEntry();
  return true;
}

/** القفز إلى مدخل معيّن في السجل */
export function gotoHistory(index) {
  if (index < 0 || index >= state.history.length) return false;
  state.historyIndex = index;
  applyHistoryEntry();
  return true;
}

function applyHistoryEntry() {
  const entry = state.history[state.historyIndex];
  if (!entry) return;
  state.image = entry.image;
  state.width = entry.width;
  state.height = entry.height;
  state.layers = (entry.layers || []).map(cloneLayer);
  state.drawLayer = null;
  clearPreview();
  emit('image', { label: `سجل: ${entry.label}` });
  emit('history');
}

/* ═══════════════════ الطبقات ═══════════════════ */
let layerSeq = 0;

/** إضافة طبقة جديدة فوق الصورة (رسم/نص/تحديد…) */
export function addLayer({ name = 'طبقة', type = 'draw', dataUrl, opacity = 1, visible = true }) {
  layerSeq += 1;
  const layer = { id: `L${layerSeq}-${Date.now()}`, name, type, dataUrl, opacity, visible };
  state.layers.push(layer);
  emit('layers');
  return layer;
}

/** حذف طبقة بالمعرّف */
export function removeLayer(id) {
  const i = state.layers.findIndex((l) => l.id === id);
  if (i < 0) return false;
  state.layers.splice(i, 1);
  emit('layers');
  return true;
}

/** إظهار/إخفاء طبقة */
export function toggleLayer(id) {
  const l = state.layers.find((x) => x.id === id);
  if (!l) return false;
  l.visible = !l.visible;
  emit('layers');
  return true;
}

/** نقل طبقة لأعلى/لأسفل في ترتيب الرصّ */
export function moveLayer(id, dir) {
  const i = state.layers.findIndex((l) => l.id === id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= state.layers.length) return false;
  [state.layers[i], state.layers[j]] = [state.layers[j], state.layers[i]];
  emit('layers');
  return true;
}

/** إعادة تعيين كاملة (صورة جديدة) */
export function reset() {
  state.image = null;
  state.original = null;
  state.previewImage = null;
  state.drawLayer = null;
  state.layers = [];
  state.history = [];
  state.historyIndex = -1;
  state.width = state.height = 0;
  emit('reset');
}

/* ═══════════════════ أدوات مساعدة ═══════════════════ */

/** حجم ملف مقروء */
export function humanSize(bytes) {
  if (!bytes) return '—';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0, v = bytes;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

/** تحويل data URL إلى Base64 خام (بلا بادئة) */
export function toBase64(dataUrl) {
  if (!dataUrl) return '';
  const i = dataUrl.indexOf(',');
  return i >= 0 ? dataUrl.slice(i + 1) : dataUrl;
}

/** تحميل data URL إلى عنصر Image */
export function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = dataUrl;
  });
}

/** إنشاء صورة مصغّرة data URL (للسجل) */
export async function makeThumb(dataUrl, size = 72) {
  try {
    const img = await loadImage(dataUrl);
    const c = document.createElement('canvas');
    const s = Math.min(size / Math.max(img.width, img.height), 1);
    c.width = Math.max(1, Math.round(img.width * s));
    c.height = Math.max(1, Math.round(img.height * s));
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', 0.6);
  } catch {
    return null;
  }
}

// تصدير افتراضي لسهولة الوصول من أدوات الاختبار في المتصفح
export default state;

/**
 * أدوات واجهة مشتركة: تحديد العناصر، التنبيهات، مؤشر الانشغال، القوالب.
 */

/** اختصار لـ querySelector */
export const $ = (sel, root = document) => root.querySelector(sel);
/** اختصار لـ querySelectorAll → مصفوفة */
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/* ═══════════════ التنبيهات (Toasts) ═══════════════ */
export function toast(message, kind = 'info', ms = 3200) {
  const host = $('#toast-host');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .3s, transform .3s';
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    setTimeout(() => el.remove(), 320);
  }, ms);
}

/* ═══════════════ شريط الحالة ═══════════════ */
export function status(msg, kind = '') {
  const el = $('#status-msg');
  if (!el) return;
  el.textContent = msg;
  el.className = `status-msg ${kind}`;
}

export function statusTime(ms) {
  const el = $('#status-time');
  if (el) el.textContent = ms ? `${ms} ملّي ثانية` : '';
}

/* ═══════════════ مؤشر الانشغال ═══════════════ */
let busyCount = 0;
export function busy(text = 'جارٍ المعالجة…') {
  busyCount++;
  const el = $('#busy');
  $('#busy-text').textContent = text;
  el.hidden = false;
}
export function idle() {
  busyCount = Math.max(0, busyCount - 1);
  if (busyCount === 0) $('#busy').hidden = true;
}

/**
 * تغليف دالة غير متزامنة: مؤشر انشغال + معالجة أخطاء موحّدة.
 * @param {string} label نص يُعرض أثناء المعالجة
 * @param {Function} fn  الدالة
 */
export async function withBusy(label, fn) {
  busy(label);
  const started = performance.now();
  try {
    const out = await fn();
    statusTime(Math.round(performance.now() - started));
    return out;
  } catch (err) {
    console.error(err);
    status(err.message || 'حدث خطأ.', 'err');
    toast(err.message || 'حدث خطأ أثناء المعالجة.', 'err', 5200);
    throw err;
  } finally {
    idle();
  }
}

/* ═══════════════ بناء عناصر ═══════════════ */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

/** إنشاء منزلق (slider) موحّد داخل حاوية .slider */
export function makeSlider(container) {
  const key = container.dataset.key;
  const min = parseFloat(container.dataset.min ?? '0');
  const max = parseFloat(container.dataset.max ?? '100');
  const def = parseFloat(container.dataset.def ?? '0');
  const step = parseFloat(container.dataset.step ?? '1');
  const label = container.querySelector('label');
  const labelText = label ? label.textContent.trim() : key;

  const input = el('input', { type: 'range', min, max, step, value: def, id: `sl-${key}` });
  container.append(input);

  const show = () => {
    const v = parseFloat(input.value);
    label.textContent = labelText;
    label.dataset.val = Number.isInteger(v) ? String(v) : v.toFixed(2);
  };
  show();

  input.addEventListener('input', () => {
    show();
    container.dispatchEvent(new CustomEvent('slider', { detail: { key, value: parseFloat(input.value) } }));
  });

  return {
    input,
    key,
    get value() { return parseFloat(input.value); },
    set value(v) { input.value = v; show(); },
    reset() { input.value = def; show(); },
    isDefault() { return Math.abs(parseFloat(input.value) - def) < 1e-9; },
  };
}

/** قراءة قيمة عنصر بأمان */
export function val(id, fallback = '') {
  const e = document.getElementById(id);
  return e ? e.value : fallback;
}
export function num(id, fallback = 0) {
  const e = document.getElementById(id);
  const v = parseFloat(e?.value);
  return Number.isFinite(v) ? v : fallback;
}
export function checked(id) {
  return !!document.getElementById(id)?.checked;
}

/** تفعيل/تعطيل مجموعة أزرار */
export function setDisabled(ids, disabled) {
  for (const id of [].concat(ids)) {
    const e = document.getElementById(id);
    if (e) e.disabled = disabled;
  }
}

/** قراءة ملف كـ data URL */
export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(new Error('تعذّر قراءة الملف.'));
    fr.readAsDataURL(file);
  });
}

/** تنزيل data URL مباشرة من المتصفح (بديل عند تعطّل الخادم) */
export function saveDataUrl(dataUrl, filename) {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** منع السلوك الافتراضي للسحب والإفلات على النافذة كلها */
export function disableNativeDnd() {
  for (const ev of ['dragover', 'drop']) {
    window.addEventListener(ev, (e) => {
      if (!e.target.closest('.dropzone') && !e.target.closest('#canvas-wrap')) e.preventDefault();
    });
  }
}

/**
 * لوحات الأدوات — المجموعة الأولى:
 *   التحويل · العمليات الهندسية · القصّ التفاعلي · الرسم
 */

import { state, setImageFromDataUrl, toBase64, clearPreview, addLayer, commit } from '../core/state.js';
import { api, toDataUrl } from '../core/api.js';
import * as canvas from '../core/canvas.js';
import { $, $$, toast, status, withBusy, val, num, checked, makeSlider, fileToDataUrl } from './helpers.js';

/** تطبيق نتيجة الخادم على الحالة */
export async function applyResult(resp, label) {
  const url = toDataUrl(resp);
  await setImageFromDataUrl(url, { label });
  const ms = resp?.meta?.elapsed_ms;
  status(`${label} — ${resp.meta.width}×${resp.meta.height} · ${ms} ملّي ثانية`, 'ok');
  return url;
}

const needImage = () => {
  if (!state.image) { toast('افتح صورة أولاً.', 'warn'); return false; }
  return true;
};

/* ═══════════════════ 1) تحويل الصيغة ═══════════════════ */
export function initConvert() {
  const fmt = $('#conv-format');
  const q = $('#conv-quality');
  const qv = $('#conv-q-val');
  const row = $('[data-only-lossy]');

  const sync = () => {
    const lossy = ['jpeg', 'webp', 'avif'].includes(fmt.value);
    row.style.display = lossy ? '' : 'none';
    qv.textContent = q.value;
  };
  fmt.addEventListener('change', sync);
  q.addEventListener('input', sync);
  sync();

  $('#btn-convert').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ تحويل الصيغة…', async () => {
      const resp = await api.convert(state.image, {
        format: fmt.value,
        quality: num('conv-quality', 92),
        background: val('conv-bg', '#ffffff'),
        keep_alpha: checked('conv-keep-alpha'),
        keep_exif: checked('conv-keep-exif'),
      });
      await applyResult(resp, `تحويل إلى ${resp.meta.format.toUpperCase()}`);
      $('#conv-info').textContent =
        `${resp.meta.width}×${resp.meta.height} · ${(resp.meta.size_bytes / 1024).toFixed(1)} ك.بايت · ${resp.meta.mime}`;
      toast(`تم التحويل إلى ${resp.meta.format.toUpperCase()}`, 'ok');
    });
  });
}

/* ═══════════════════ 2) العمليات الهندسية ═══════════════════ */
export function initGeometry() {
  // أزرار الدوران/القلب/القصّ التلقائي
  $$('[data-geo]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!needImage()) return;
      const op = btn.dataset.geo;
      withBusy('جارٍ التنفيذ…', async () => {
        let resp;
        if (op === 'rotate90') resp = await api.rotate90(state.image, parseInt(btn.dataset.times, 10));
        else if (op === 'flip') resp = await api.flip(state.image, btn.dataset.dir);
        else if (op === 'transpose') resp = await api.transpose(state.image, 'transpose');
        else if (op === 'crop-auto') resp = await api.cropAuto(state.image, { tolerance: 12 });
        await applyResult(resp, btn.textContent.trim());
      });
    });
  });

  // الدوران الحر
  const angle = $('#geo-angle');
  angle.addEventListener('input', () => { $('#geo-angle-val').textContent = `${angle.value}°`; });
  $('#btn-rotate').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ التدوير…', async () => {
      const resp = await api.rotate(state.image, num('geo-angle'), {
        expand: checked('geo-expand'),
        fill: val('geo-fill', '#ffffff'),
        fill_transparent: true,
      });
      await applyResult(resp, `دوران ${angle.value}°`);
    });
  });

  // تغيير الحجم
  const w = $('#geo-w'), h = $('#geo-h'), lock = $('#geo-lock');
  let ratio = 1;
  const syncRatio = () => { if (state.width && state.height) ratio = state.width / state.height; };
  w.addEventListener('input', () => { syncRatio(); if (lock.checked && w.value) h.value = Math.round(w.value / ratio); });
  h.addEventListener('input', () => { syncRatio(); if (lock.checked && h.value) w.value = Math.round(h.value * ratio); });

  $('#btn-resize').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ تغيير الحجم…', async () => {
      const resp = await api.resize(state.image, {
        width: num('geo-w') || null,
        height: num('geo-h') || null,
        mode: val('geo-resize-mode', 'fit'),
        resample: val('geo-resample', 'lanczos'),
      });
      await applyResult(resp, 'تغيير الحجم');
      w.value = resp.meta.width; h.value = resp.meta.height;
    });
  });

  // القصّ إلى نسبة
  $$('#aspect-chips .chip').forEach((c) => {
    c.addEventListener('click', () => {
      if (!needImage()) return;
      withBusy('جارٍ القصّ…', async () => {
        const resp = await api.cropAspect(state.image, c.dataset.aspect, 'center');
        await applyResult(resp, `قصّ ${c.dataset.aspect}`);
      });
    });
  });

  // الإطار
  $('#btn-border').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ إضافة الإطار…', async () => {
      const resp = await api.border(state.image, {
        width: num('geo-border-w', 12),
        color: val('geo-border-color', '#111111'),
        style: val('geo-border-style', 'solid'),
      });
      await applyResult(resp, 'إطار');
    });
  });

  // توسيع اللوحة
  $('#btn-pad').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ توسيع اللوحة…', async () => {
      const resp = await api.pad(state.image, { percent: num('geo-pad', 6), color: val('geo-pad-color', '#ffffff') });
      await applyResult(resp, 'توسيع اللوحة');
    });
  });

  // الظل
  $('#btn-shadow').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ إضافة الظل…', async () => {
      const resp = await api.shadow(state.image, { opacity: 0.5, blur_radius: 14, offset: [10, 16] });
      await applyResult(resp, 'ظل سقوط');
    });
  });

  // الإمالة المنظورية: الزر نفسه يفعّل الشبكة ثم يطبّقها (حالتان)
  const perspBtn = $('#btn-perspective');
  perspBtn.addEventListener('click', async () => {
    if (!needImage()) return;

    if (perspBtn.dataset.armed !== '1') {
      canvas.initPerspective();
      perspBtn.dataset.armed = '1';
      perspBtn.textContent = 'تطبيق التحويل المنظوري';
      status('اسحب النقاط الأربع إلى زوايا الجسم، ثم اضغط الزر للتطبيق.', 'ok');
      return;
    }

    const pts = canvas.getPerspectivePoints();
    const { w: iw, h: ih } = canvas.imageSize();
    perspBtn.dataset.armed = '';
    perspBtn.textContent = 'تفعيل شبكة النقاط الأربع';
    canvas.setOverlayMode(null);
    await withBusy('جارٍ التحويل المنظوري…', async () => {
      const src = [[0, 0], [1, 0], [1, 1], [0, 1]];
      const dst = pts.map(([x, y]) => [x / iw, y / ih]);
      const resp = await api.perspective(state.image, src, dst);
      await applyResult(resp, 'تحويل منظوري');
    });
  });

  // تصحيح الميل التلقائي
  $('#btn-deskew').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ اكتشاف الميل…', async () => {
      const resp = await api.deskew(state.image);
      await applyResult(resp, 'تصحيح الميل');
      toast(`الزاوية المكتشفة: ${resp.detected_angle ?? 0}°`, 'ok');
    });
  });
}

/* ═══════════════════ 3) القصّ التفاعلي ═══════════════════ */
export function initCrop() {
  const info = $('#crop-info');
  const btnApply = $('#btn-crop-apply');
  const btnCancel = $('#btn-crop-cancel');
  let aspect = null;

  const open = () => {
    if (!needImage()) return;
    canvas.setOverlayMode('crop');
    status('اسحب على الصورة لتحديد منطقة القصّ.', 'ok');
    btnApply.disabled = true; btnCancel.disabled = false;
  };
  const close = () => {
    canvas.setOverlayMode(null);
    state.cropRect = null;
    info.textContent = 'لم يتم التحديد';
    btnApply.disabled = true; btnCancel.disabled = true;
    status('');
  };

  // يُفتح القصّ عند النقر على عنوان اللوحة أو زر «كل الصورة»
  $('[data-panel="crop"] .panel-title').addEventListener('dblclick', open);
  $('#btn-crop-all').addEventListener('click', () => {
    if (!needImage()) return;
    const { w, h } = canvas.imageSize();
    state.cropRect = { x1: 0, y1: 0, x2: w, y2: h };
    canvas.setOverlayMode('crop');
    update();
  });

  $('#crop-aspect').addEventListener('change', (e) => {
    aspect = e.target.value === 'free' ? null : evalRatio(e.target.value);
  });

  window.addEventListener('overlay:drag', (e) => {
    if (e.detail.mode !== 'crop' || !e.detail.rect) return;
    const r = e.detail.rect;
    info.textContent = `${r.w} × ${r.h} بكسل  ·  عند (${r.x}, ${r.y})`;
    btnApply.disabled = r.w < 2 || r.h < 2;
  });
  window.addEventListener('overlay:end', (e) => { if (e.detail.mode === 'crop') update(); });

  function update() {
    const r = state.cropRect;
    if (!r) return;
    const x = Math.min(r.x1, r.x2), y = Math.min(r.y1, r.y2);
    const w = Math.abs(r.x2 - r.x1), h = Math.abs(r.y2 - r.y1);
    info.textContent = `${w} × ${h} بكسل  ·  عند (${x}, ${y})`;
    btnApply.disabled = w < 2 || h < 2;
  }

  btnApply.addEventListener('click', () => {
    const r = state.cropRect;
    if (!r) return;
    const x = Math.min(r.x1, r.x2), y = Math.min(r.y1, r.y2);
    const w = Math.abs(r.x2 - r.x1), h = Math.abs(r.y2 - r.y1);
    withBusy('جارٍ القصّ…', async () => {
      const resp = await api.crop(state.image, [x, y, w, h], 'px');
      close();
      await applyResult(resp, 'قصّ');
    });
  });
  btnCancel.addEventListener('click', close);

  // تفعيل القصّ عند فتح اللوحة
  const panel = $('[data-panel="crop"]');
  new MutationObserver(() => { if (panel.classList.contains('open')) open(); })
    .observe(panel, { attributes: true, attributeFilter: ['class'] });
}

function evalRatio(str) {
  const [a, b] = str.split(':').map(Number);
  return b ? a / b : null;
}

/* ═══════════════════ 4) الرسم ═══════════════════ */
export function initDraw() {
  const color = $('#draw-color');
  const size = $('#draw-size');
  const sizeV = $('#draw-size-val');
  const opacity = $('#draw-opacity');
  const opacityV = $('#draw-opacity-val');
  const textRow = $('#draw-text-row');
  const textInput = $('#draw-text');
  let tool = 'brush';

  // لوحات الألوان السريعة
  const swatches = ['#e63946', '#f4a261', '#ffd166', '#2a9d8f', '#457b9d', '#1d3557',
    '#ffffff', '#000000', '#8338ec', '#ff006e', '#3a86ff', '#8ac926'];
  const host = $('#draw-swatches');
  for (const c of swatches) {
    const s = document.createElement('i');
    s.className = 'swatch';
    s.style.background = c;
    s.title = c;
    s.addEventListener('click', () => { color.value = c; sync(); });
    host.appendChild(s);
  }

  const sync = () => {
    sizeV.textContent = size.value;
    opacityV.textContent = `${opacity.value}%`;
    textRow.hidden = tool !== 'text';
    window.__drawConfig = {
      tool, color: color.value, size: parseFloat(size.value),
      opacity: parseFloat(opacity.value), text: textInput.value, fill: false,
    };
  };
  [size, opacity, color, textInput].forEach((e) => e.addEventListener('input', sync));

  $$('#draw-tools .tool').forEach((b) => {
    b.addEventListener('click', () => {
      $$('#draw-tools .tool').forEach((x) => x.classList.remove('active'));
      b.classList.add('active');
      tool = b.dataset.tool;
      sync();
      // تفعيل وضع الرسم على الطبقة العلوية
      if (state.image) {
        canvas.setOverlayMode('draw');
        status(`أداة الرسم: ${b.title}`, 'ok');
      }
    });
  });

  window.addEventListener('overlay:picked', (e) => {
    color.value = e.detail.hex;
    sync();
    toast(`اللون الملتقط: ${e.detail.hex}`, 'ok');
  });

  $('#btn-draw-undo').addEventListener('click', () => { canvas.popStroke(); });
  $('#btn-draw-clear').addEventListener('click', () => { canvas.clearStrokes(); });

  // تثبيت الرسم: نرسل طبقة الرسم إلى الخادم لدمجها
  $('#btn-draw-flatten').addEventListener('click', () => {
    if (!needImage()) return;
    const layer = canvas.exportDrawLayer();
    if (!layer) { toast('لا يوجد رسم لتثبيته.', 'warn'); return; }
    withBusy('جارٍ تثبيت الرسم…', async () => {
      const resp = await api.blend(state.image, layer, { mode: 'normal', opacity: 1, anchor: 'top-left', scale: 1 });
      canvas.clearStrokes();
      canvas.setOverlayMode(null);
      await applyResult(resp, 'تثبيت الرسم');
      toast('تم تثبيت الرسم على الصورة.', 'ok');
    });
  });

  // تثبيت الرسم كطبقة مستقلة قابلة للحذف (نظام الطبقات)
  $('#btn-draw-layer').addEventListener('click', () => {
    if (!needImage()) return;
    const layer = canvas.exportDrawLayer();
    if (!layer) { toast('لا يوجد رسم لتثبيته كطبقة.', 'warn'); return; }
    canvas.clearStrokes();
    addLayer({ name: `رسم ${state.layers.length + 1}`, type: 'draw', dataUrl: layer });
    commit('طبقة رسم جديدة');
    toast('أُضيف الرسم طبقةً مستقلة — يمكن حذفها من لوحة «الطبقات».', 'ok');
  });

  // تفعيل الرسم عند فتح اللوحة
  const panel = $('[data-panel="draw"]');
  new MutationObserver(() => {
    if (panel.classList.contains('open') && state.image) {
      canvas.setOverlayMode('draw');
      status(`أداة الرسم: ${$$('#draw-tools .tool.active')[0]?.title || 'فرشاة'}`, 'ok');
    }
  }).observe(panel, { attributes: true, attributeFilter: ['class'] });

  sync();
}

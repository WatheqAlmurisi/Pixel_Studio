/**
 * لوحات الميزات المضافة: النصوص · تحديد الكائنات · الطبقات
 * =========================================================
 * • النصوص: وضع بالنقر أو داخل منطقة مرسومة (صندوق نص)، محرر نص داخل الصورة
 *   (نقرة مزدوجة أو تلقائياً بعد الوضع)، تعديل فوري من اللوحة أثناء الاختيار،
 *   محاذاة أفقية/رأسية داخل الصندوق — وكل تعديل **في المكان** بلا نسخة جديدة.
 * • تحديد الكائنات: عصا سحرية (نقرة ⇒ انتقاء لوني فوري بمعاينة) + تلقائي/مستطيل/
 *   نقاط/يدوي + منزلق دقة (تكرارات GrabCut) وتحسين حواف ذكي (Matting).
 * • الطبقات: الأصل مقفل + طبقات مستقلة (إظهار/إخفاء/ترتيب/حذف) — وكلها
 *   عمليات في المكان تعود بالصورة إلى شكلها السابق دون إنشاء نسخة جديدة.
 */

import {
  state, addLayer, removeLayer, toggleLayer, moveLayer, commit, updateCurrentHistory,
  setImageFromDataUrl, onChange, emit,
} from '../core/state.js';
import { api, toDataUrl } from '../core/api.js';
import * as canvas from '../core/canvas.js';
import { $, $$, toast, status, withBusy, el, num, checked, makeSlider } from './helpers.js';

const needImage = () => {
  if (!state.image) { toast('افتح صورة أولاً.', 'warn'); return false; }
  return true;
};

/* ═══════════════════ أدوات النصوص (مستوى الوحدة) ═══════════════════ */
const tSliders = {};
let placingText = false;
let placingTextBox = false;
let boxDrag = null;       // سحب منطقة النص {x1,y1,x2,y2}
let txtDrag = null;       // سحب النص المحدد {kind,id,start,orig,bb}
let tAlign = 'center';    // محاذاة أفقية داخل الصندوق: start|center|end
let tValign = 'middle';   // محاذاة رأسية داخل الصندوق: top|middle|bottom
let inlineEd = null;      // محرر النص داخل الصورة {ta, id}

/** حالة تحديد الكائنات (تُستخدم في المعاينة ولوحة التحديد) */
const sel = { tool: 'auto', points: [], seeds: [], mask: null, painting: false, wandTint: null };

function textStyle() {
  const tv = (k, d) => (tSliders[k] ? tSliders[k].value : d);
  return {
    text: $('#txt-content').value,
    font: $('#txt-font').value,
    size: tv('txt-size', 24),
    color: $('#txt-color').value,
    bold: checked('txt-bold'),
    outline: checked('txt-outline'),
    shadow: checked('txt-shadow'),
    rotate: tv('txt-rotate', 0),
    opacity: tv('txt-opacity', 100) / 100,
    align: tAlign,
    valign: tValign,
  };
}

function fontOf(m, sizePx) {
  return `${m.bold ? 'bold ' : ''}${Math.max(6, sizePx)}px ${m.font}`;
}

/** لفّ النص كلمةً كلمة داخل عرض أقصى */
function wrapText(g, text, maxW) {
  const words = String(text).split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  for (const w of words) {
    const t = line ? `${line} ${w}` : w;
    if (line && g.measureText(t).width > maxW) { lines.push(line); line = w; }
    else line = t;
  }
  if (line) lines.push(line);
  return lines.length ? lines : [''];
}

/** رسم طبقة نص بحجم الصورة من بيانات meta (نقطة حرة أو صندوق منطقة) */
function renderTextLayer(m) {
  const c = document.createElement('canvas');
  c.width = Math.max(1, state.width); c.height = Math.max(1, state.height);
  const g = c.getContext('2d');
  g.globalAlpha = m.opacity ?? 1;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillStyle = m.color;

  const paint = (text, x, y, sizePx) => {
    g.font = fontOf(m, sizePx);
    if (m.shadow) {
      g.shadowColor = 'rgba(0,0,0,.55)';
      g.shadowBlur = sizePx * 0.35;
      g.shadowOffsetY = sizePx * 0.1;
    }
    if (m.outline) {
      g.save();
      g.lineWidth = Math.max(1, sizePx * 0.14);
      g.strokeStyle = '#101418';
      g.strokeText(text, x, y);
      g.restore();
    }
    g.fillText(text, x, y);
    g.shadowColor = 'transparent'; g.shadowBlur = 0; g.shadowOffsetY = 0;
  };

  if (m.box) {
    // نص داخل منطقة: لفّ تلقائي + تصغير الخط حتى يfit داخل الصندوق
    const { x, y, w, h } = m.box;
    let sizePx = Math.max(6, m.size * 2.4);
    let lines = [];
    for (;;) {
      g.font = fontOf(m, sizePx);
      lines = wrapText(g, m.text, Math.max(12, w - 12));
      const lineH = sizePx * 1.35;
      const fitsH = lines.length * lineH <= h - 6;
      const fitsW = lines.every((l) => g.measureText(l).width <= w - 12);
      if ((fitsH && fitsW) || sizePx <= 10) break;
      sizePx = Math.max(9, sizePx * 0.9);
    }
    const lineH = sizePx * 1.35;
    const total = lines.length * lineH;
    // المحاذاة الأفقية (RTL: البداية = اليمين)
    const al = m.align || 'center';
    g.textAlign = al === 'start' ? 'right' : al === 'end' ? 'left' : 'center';
    const cx = al === 'start' ? x + w - 8 : al === 'end' ? x + 8 : x + w / 2;
    // المحاذاة الرأسية
    const va = m.valign || 'middle';
    let ty = va === 'top'
      ? y + lineH / 2 + 4
      : va === 'bottom'
        ? y + h - total + lineH / 2 - 4
        : y + Math.max(lineH / 2, (h - total) / 2 + lineH / 2);
    if (m.rotate) {
      g.translate(x + w / 2, y + h / 2);
      g.rotate((m.rotate * Math.PI) / 180);
      g.translate(-(x + w / 2), -(y + h / 2));
    }
    for (const l of lines) { paint(l, cx, ty, sizePx); ty += lineH; }
  } else {
    const sizePx = Math.max(6, m.size * 2.4);
    if (m.rotate) {
      g.translate(m.x, m.y);
      g.rotate((m.rotate * Math.PI) / 180);
      g.translate(-m.x, -m.y);
    }
    paint(m.text, m.x, m.y, sizePx);
  }
  return c.toDataURL('image/png');
}

/** المستطيل المحيط بالنص (للإمساك والتحريك) */
function textBBox(m) {
  if (m.box) return { x: m.box.x, y: m.box.y, w: m.box.w, h: m.box.h };
  const sizePx = Math.max(6, m.size * 2.4);
  const g = document.createElement('canvas').getContext('2d');
  g.font = fontOf(m, sizePx);
  const w = Math.max(24, g.measureText(m.text || ' ').width + 10);
  const h = sizePx * 1.3;
  return { x: m.x - w / 2, y: m.y - h / 2, w, h };
}

function selectedTextLayer() {
  const l = state.layers.find((x) => x.id === state.selectedLayer);
  return l && l.type === 'text' && l.meta ? l : null;
}

/** أعلى طبقة نص تحوي النقطة (بحث من الأعلى للأسفل) */
function hitTextLayer(x, y) {
  for (let i = state.layers.length - 1; i >= 0; i--) {
    const l = state.layers[i];
    if (l.type !== 'text' || !l.meta || !l.visible) continue;
    const bb = textBBox(l.meta);
    if (x >= bb.x - 4 && x <= bb.x + bb.w + 4 && y >= bb.y - 4 && y <= bb.y + bb.h + 4) return l;
  }
  return null;
}

/** مزامنة أزرار المحاذاة مع القيم */
function syncAlignBtns() {
  $$('#panels [data-talign]').forEach((b) => b.classList.toggle('active', b.dataset.talign === tAlign));
  $$('#panels [data-tvalign]').forEach((b) => b.classList.toggle('active', b.dataset.tvalign === tValign));
}

/** اختيار نص مكتوب لتعديله (من زر ✎ أو نقرة مزدوجة) */
export function selectTextLayer(id) {
  const l = state.layers.find((x) => x.id === id);
  if (!l || l.type !== 'text' || !l.meta) { toast('هذه الطبقة ليست نصاً قابلاً للتعديل.', 'warn'); return; }
  closeInlineEditor();
  state.selectedLayer = id;
  const m = l.meta;
  // تعبئة لوحة النصوص ببيانات النص المحدد
  $('#txt-content').value = m.text;
  $('#txt-font').value = m.font;
  $('#txt-color').value = m.color;
  $('#txt-bold').checked = !!m.bold;
  $('#txt-outline').checked = !!m.outline;
  $('#txt-shadow').checked = !!m.shadow;
  tAlign = m.align || 'center';
  tValign = m.valign || 'middle';
  syncAlignBtns();
  if (tSliders['txt-size']) tSliders['txt-size'].value = m.size;
  if (tSliders['txt-rotate']) tSliders['txt-rotate'].value = m.rotate;
  if (tSliders['txt-opacity']) tSliders['txt-opacity'].value = Math.round((m.opacity ?? 1) * 100);
  const up = $('#btn-txt-update');
  if (up) up.disabled = false;
  canvas.setOverlayMode('textedit');
  canvas.refreshOverlay();
  emit('layers');
  status('نص محدّد: التعديل من اللوحة فوري · اسحبه للتحريك · المقبض ◢ للتحجيم · نقرة مزدوجة تفتح المحرر في المكان. (Esc للإلغاء)', 'ok');
}

/** إعادة وضع الطبقة العلوية حسب أداة التحديد النشطة (بعد إنهاء وضع النص) */
function restoreSelectMode() {
  const panelOpen = $('[data-panel="select"]')?.classList.contains('open');
  if (!panelOpen) { canvas.setOverlayMode(null); return; }
  if (sel.tool === 'rect') canvas.setOverlayMode('rect');
  else if (['wand', 'points', 'brush', 'eraser'].includes(sel.tool)) canvas.setOverlayMode('select');
  else canvas.setOverlayMode(null);
}

/** إلغاء اختيار النص */
export function deselectText() {
  closeInlineEditor();
  state.selectedLayer = null;
  const up = $('#btn-txt-update');
  if (up) up.disabled = true;
  if (canvas.getOverlayMode() === 'textedit') restoreSelectMode();
  emit('layers');
  status('');
}

/* ═══════════════════ محرر النص داخل الصورة ═══════════════════ */
function openInlineEditor(layer) {
  if (!layer || !layer.meta) return;
  if (layer.meta.rotate) return;   // النص المائل يُعدَّل من اللوحة (المحرر المستقيم لا ينطبق)
  closeInlineEditor();
  const stage = $('#canvas-stage');
  const m = layer.meta;
  const bb = textBBox(m);
  const z = state.zoom || 1;
  const sr = stage.getBoundingClientRect();
  const p0 = canvas.toScreen(bb.x, bb.y);

  const ta = el('textarea', { class: 'txt-inline' });
  ta.value = m.text;
  ta.style.left = `${p0.x - sr.left}px`;
  ta.style.top = `${p0.y - sr.top}px`;
  ta.style.width = `${Math.max(120, bb.w * z)}px`;
  ta.style.minHeight = `${Math.max(34, bb.h * z)}px`;
  ta.style.height = `${Math.max(34, bb.h * z)}px`;
  ta.style.fontSize = `${Math.max(12, m.size * 2.4 * z)}px`;
  ta.style.color = m.color;
  ta.style.fontFamily = m.font.replace(/"/g, '');
  ta.style.fontWeight = m.bold ? 'bold' : 'normal';
  stage.appendChild(ta);
  inlineEd = { ta, id: layer.id };
  // التركيز مؤجَّل: النقرة التي فتحت المحرر تُتمّ سلوكها الافتراضي (نقل التركيز)
  // أولاً، وإلا خطف المتصفح التركيز فوراً وأُغلق المحرر قبل الكتابة.
  setTimeout(() => {
    if (inlineEd && inlineEd.ta === ta) {
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
    }
  }, 0);

  let deb = null;
  ta.addEventListener('input', () => {
    clearTimeout(deb);
    deb = setTimeout(() => {
      const l = state.layers.find((x) => x.id === inlineEd?.id);
      if (!l) return;
      l.meta.text = ta.value;
      l.name = `نص: «${ta.value.trim().slice(0, 14)}»`;
      l.dataUrl = renderTextLayer(l.meta);
      canvas.render();
      const tc = $('#txt-content');
      if (tc) tc.value = ta.value;
    }, 180);
  });
  ta.addEventListener('blur', () => closeInlineEditor());
  ta.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Escape') { e.preventDefault(); ta.blur(); }
  });
  status('محرر النص: اكتب مباشرة على الصورة — الإغلاق (نقرة خارجه أو Esc) يحفظ التعديل في المكان.', 'ok');
}

function closeInlineEditor() {
  if (!inlineEd) return;
  const { ta, id } = inlineEd;
  inlineEd = null;
  ta.remove();
  const l = state.layers.find((x) => x.id === id);
  if (!l) return;
  const txt = ta.value;
  if (!txt.trim()) {
    // أُغلق بلا نص ⇒ تُحذف الطبقة الفارغة (بلا نسخة في السجل)
    if (state.selectedLayer === id) state.selectedLayer = null;
    removeLayer(id);
    updateCurrentHistory();
    emit('layers');
    return;
  }
  l.meta.text = txt;
  l.name = `نص: «${txt.trim().slice(0, 14)}»`;
  l.dataUrl = renderTextLayer(l.meta);
  updateCurrentHistory();     // حفظ في المكان — بلا نسخة جديدة
  canvas.render();
  emit('layers');
}

/* ═══════════════════ معاينات الطبقة العلوية ═══════════════════ */
function drawSelectPreviewOn(octx) {
  if (canvas.getOverlayMode() !== 'select') return;
  octx.save();
  if (sel.tool === 'wand' && sel.wandTint) {
    octx.globalAlpha = 0.5;
    octx.drawImage(sel.wandTint, 0, 0);
    octx.globalAlpha = 1;
  } else if (sel.mask) {
    octx.globalAlpha = 0.4;
    octx.drawImage(sel.mask, 0, 0);
    octx.globalAlpha = 1;
  }
  const z = state.zoom || 1;
  const marks = sel.tool === 'wand'
    ? sel.seeds.map((s) => ({ x: s.x, y: s.y, kind: s.kind ? 'fg' : 'bg' }))
    : sel.points;
  for (const p of marks) {
    octx.beginPath();
    octx.arc(p.x, p.y, 9 / z, 0, Math.PI * 2);
    octx.fillStyle = p.kind === 'fg' ? 'rgba(53,201,138,.85)' : 'rgba(230,57,70,.85)';
    octx.fill();
    octx.strokeStyle = '#fff';
    octx.lineWidth = 2 / z;
    octx.beginPath();
    if (p.kind === 'fg') {
      octx.moveTo(p.x - 5 / z, p.y); octx.lineTo(p.x + 5 / z, p.y);
      octx.moveTo(p.x, p.y - 5 / z); octx.lineTo(p.x, p.y + 5 / z);
    } else {
      octx.moveTo(p.x - 4 / z, p.y - 4 / z); octx.lineTo(p.x + 4 / z, p.y + 4 / z);
      octx.moveTo(p.x + 4 / z, p.y - 4 / z); octx.lineTo(p.x - 4 / z, p.y + 4 / z);
    }
    octx.stroke();
  }
  octx.restore();
}

function drawTextBoxPreview(octx) {
  if (!boxDrag || !placingTextBox) return;
  const z = state.zoom || 1;
  const x = Math.min(boxDrag.x1, boxDrag.x2), y = Math.min(boxDrag.y1, boxDrag.y2);
  const w = Math.abs(boxDrag.x2 - boxDrag.x1), h = Math.abs(boxDrag.y2 - boxDrag.y1);
  octx.save();
  octx.strokeStyle = '#ffd166';
  octx.lineWidth = 2 / z;
  octx.setLineDash([8 / z, 5 / z]);
  octx.strokeRect(x, y, w, h);
  octx.fillStyle = 'rgba(255,209,102,.12)';
  octx.fillRect(x, y, w, h);
  octx.setLineDash([]);
  octx.fillStyle = '#ffd166';
  octx.font = `${12 / z}px "Segoe UI", Tahoma, sans-serif`;
  octx.textAlign = 'center';
  octx.fillText('منطقة النص', x + w / 2, Math.max(12 / z, y - 6 / z));
  octx.restore();
}

function drawTextEditPreview(octx) {
  if (canvas.getOverlayMode() !== 'textedit') return;
  const l = selectedTextLayer();
  if (!l) return;
  const bb = textBBox(l.meta);
  const z = state.zoom || 1;
  octx.save();
  octx.strokeStyle = '#5b8cff';
  octx.lineWidth = 2 / z;
  octx.setLineDash([7 / z, 5 / z]);
  octx.strokeRect(bb.x, bb.y, bb.w, bb.h);
  octx.setLineDash([]);
  const hs = 8 / z;
  octx.fillStyle = '#5b8cff';
  for (const [hx, hy] of [[bb.x, bb.y], [bb.x + bb.w, bb.y], [bb.x, bb.y + bb.h]]) {
    octx.fillRect(hx - hs / 2, hy - hs / 2, hs, hs);
  }
  // مقبض التحجيم (الزاوية السفلية اليمنى)
  octx.fillStyle = '#ffd166';
  const s2 = 11 / z;
  octx.fillRect(bb.x + bb.w - s2 / 2, bb.y + bb.h - s2 / 2, s2, s2);
  octx.restore();
}

/* ═══════════════════ 1) النصوص على الصورة ═══════════════════ */
export function initText() {
  $$('#panels [data-panel="text"] .slider').forEach((c) => { const s = makeSlider(c); tSliders[s.key] = s; });
  syncAlignBtns();

  const placeBtn = $('#btn-txt-place');
  placeBtn.addEventListener('click', () => {
    if (!needImage()) return;
    placingText = !placingText;
    placingTextBox = placingText && checked('txt-box');
    placeBtn.classList.toggle('btn-primary', placingText);
    // تنشيط الطبقة العلوية لتلتقط النقرات/السحب أثناء الوضع
    canvas.setOverlayMode(placingText ? 'select' : null);
    if (placingText) {
      status(placingTextBox
        ? 'وضع النص: اسحب مستطيلاً على الصورة لتحديد منطقة النص، ثم اكتب في المحرر. (Esc للإلغاء)'
        : 'وضع النص: انقر على الصورة لوضع النص، ثم اكتب في المحرر مباشرة. (Esc للإلغاء)', 'ok');
    } else status('');
  });

  // أزرار المحاذاة: تُطبَّق فوراً على النص المحدد
  $$('#panels [data-talign]').forEach((b) => b.addEventListener('click', () => {
    tAlign = b.dataset.talign;
    syncAlignBtns();
    applyPanelToSelected();
  }));
  $$('#panels [data-tvalign]').forEach((b) => b.addEventListener('click', () => {
    tValign = b.dataset.tvalign;
    syncAlignBtns();
    applyPanelToSelected();
  }));

  // تعديل فوري: أي تغيير في اللوحة أثناء اختيار نص يُطبَّق في المكان مباشرة
  const live = () => applyPanelToSelected();
  ['#txt-content', '#txt-font', '#txt-color'].forEach((s) => $(s)?.addEventListener('input', live));
  ['#txt-bold', '#txt-outline', '#txt-shadow'].forEach((s) => $(s)?.addEventListener('change', live));
  ['txt-size', 'txt-rotate', 'txt-opacity'].forEach((k) => {
    const inp = $(`#sl-${k}`);
    if (inp) inp.addEventListener('input', live);
  });

  // زر التحديث الصريح (يبقى متاحاً لمن يفضّله)
  $('#btn-txt-update').addEventListener('click', () => {
    if (!selectedTextLayer()) { toast('اختر نصاً (زر ✎ من «الطبقات» أو نقرة مزدوجة على النص) أولاً.', 'warn'); return; }
    if (applyPanelToSelected()) toast('حُدّث النص المحدد (بلا نسخة جديدة في السجل).', 'ok');
  });

  const overlay = $('#overlay-canvas');

  // — وضع النص: نقرة حرة أو سحب منطقة (صندوق) —
  overlay.addEventListener('pointerdown', (e) => {
    if (!placingText) return;
    e.stopImmediatePropagation();
    const p = canvas.toImageCoords(e);
    if (placingTextBox) { boxDrag = { x1: p.x, y1: p.y, x2: p.x, y2: p.y }; return; }
    placeAndEdit({ x: p.x, y: p.y, box: null });
  }, true);

  window.addEventListener('pointermove', (e) => {
    if (!boxDrag) return;
    const p = canvas.toImageCoords(e);
    boxDrag.x2 = p.x; boxDrag.y2 = p.y;
    canvas.refreshOverlay();
  });

  window.addEventListener('pointerup', () => {
    if (!boxDrag) return;
    const b = boxDrag; boxDrag = null;
    canvas.refreshOverlay();
    const x = Math.min(b.x1, b.x2), y = Math.min(b.y1, b.y2);
    const w = Math.abs(b.x2 - b.x1), h = Math.abs(b.y2 - b.y1);
    if (w < 24 || h < 16) { toast('المنطقة صغيرة جداً — ارسم منطقة أكبر.', 'warn'); return; }
    placeAndEdit({
      x: Math.round(x + w / 2), y: Math.round(y + h / 2),
      box: { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) },
    });
  });

  // — نقرة مزدوجة على أي نص في الصورة ⇒ اختيار + محرر في المكان —
  $('#canvas-stage').addEventListener('dblclick', (e) => {
    if (!state.image || placingText || boxDrag) return;
    if (e.target instanceof HTMLTextAreaElement) return;
    const p = canvas.toImageCoords(e);
    const l = hitTextLayer(p.x, p.y);
    if (!l) return;
    selectTextLayer(l.id);
    openInlineEditor(l);
  });

  // — الإمساك بالنص المحدد: تحريك من الداخل، تحجيم من المقبض ◢ —
  overlay.addEventListener('pointerdown', (e) => {
    if (canvas.getOverlayMode() !== 'textedit') return;
    const l = selectedTextLayer();
    if (!l) { deselectText(); return; }
    e.stopImmediatePropagation();
    const p = canvas.toImageCoords(e);
    const bb = textBBox(l.meta);
    const tol = 16 / (state.zoom || 1);
    const hx = bb.x + bb.w, hy = bb.y + bb.h;
    const orig = { ...l.meta, box: l.meta.box ? { ...l.meta.box } : null };
    if (Math.abs(p.x - hx) <= tol && Math.abs(p.y - hy) <= tol) {
      txtDrag = { kind: 'resize', id: l.id, start: p, orig, bb };
    } else if (p.x >= bb.x - tol && p.x <= bb.x + bb.w + tol && p.y >= bb.y - tol && p.y <= bb.y + bb.h + tol) {
      txtDrag = { kind: 'move', id: l.id, start: p, orig, bb };
    } else {
      deselectText();
    }
  }, true);

  window.addEventListener('pointermove', (e) => {
    if (!txtDrag) return;
    const l = state.layers.find((x) => x.id === txtDrag.id);
    if (!l) { txtDrag = null; return; }
    const p = canvas.toImageCoords(e);
    const dx = p.x - txtDrag.start.x, dy = p.y - txtDrag.start.y;
    if (txtDrag.kind === 'move') {
      l.meta.x = Math.round(txtDrag.orig.x + dx);
      l.meta.y = Math.round(txtDrag.orig.y + dy);
      if (l.meta.box && txtDrag.orig.box) {
        l.meta.box.x = Math.round(txtDrag.orig.box.x + dx);
        l.meta.box.y = Math.round(txtDrag.orig.box.y + dy);
      }
    } else if (l.meta.box && txtDrag.orig.box) {
      l.meta.box.w = Math.max(40, Math.round(txtDrag.orig.box.w + dx));
      l.meta.box.h = Math.max(24, Math.round(txtDrag.orig.box.h + dy));
    } else {
      // تحجيم نص حر: نسبة البعد عن مركز المستطيل
      const cx = txtDrag.bb.x + txtDrag.bb.w / 2, cy = txtDrag.bb.y + txtDrag.bb.h / 2;
      const d0 = Math.max(8, Math.hypot(txtDrag.start.x - cx, txtDrag.start.y - cy));
      const d1 = Math.hypot(p.x - cx, p.y - cy);
      const scale = Math.min(4, Math.max(0.25, d1 / d0));
      l.meta.size = Math.max(6, Math.min(120, Math.round(txtDrag.orig.size * scale * 10) / 10));
      if (tSliders['txt-size']) tSliders['txt-size'].value = Math.round(l.meta.size);
    }
    l.dataUrl = renderTextLayer(l.meta);
    canvas.render();
    canvas.refreshOverlay();
  });

  window.addEventListener('pointerup', () => {
    if (!txtDrag) return;
    txtDrag = null;
    updateCurrentHistory();     // تعديل في المكان — بلا نسخة جديدة
    emit('layers');
  });

  // — Esc: إلغاء الوضع أو إلغاء التحديد —
  window.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (placingText) endPlacing();
    else if (state.selectedLayer) deselectText();
  });

  // — خطاف المعاينات فوق الطبقة العلوية —
  canvas.setOverlayHook((octx) => {
    drawSelectPreviewOn(octx);
    drawTextBoxPreview(octx);
    drawTextEditPreview(octx);
  });

  onChange((kind) => {
    if (kind === 'reset') {
      placingText = false; placingTextBox = false; boxDrag = null; txtDrag = null;
      placeBtn.classList.remove('btn-primary');
      closeInlineEditor();
      state.selectedLayer = null;
      const up = $('#btn-txt-update');
      if (up) up.disabled = true;
    }
  });
}

/** تطبيق قيم اللوحة على النص المحدد — في المكان بلا نسخة جديدة */
function applyPanelToSelected() {
  const l = selectedTextLayer();
  if (!l) return false;
  const st = textStyle();
  if (inlineEd && inlineEd.id === l.id) st.text = inlineEd.ta.value;  // المحرر المفتوح أولى
  l.meta = { ...l.meta, ...st };
  l.name = `نص: «${st.text.trim().slice(0, 14)}»`;
  l.dataUrl = renderTextLayer(l.meta);
  updateCurrentHistory();
  canvas.render();
  emit('layers');
  return true;
}

/** وضع نص جديد ثم اختياره وفتح المحرر في المكان */
function placeAndEdit(pos) {
  const st = textStyle();
  const m = { ...st, ...pos };
  const layer = addLayer({ name: `نص: «${m.text.trim().slice(0, 14) || '…'}»`, type: 'text', dataUrl: renderTextLayer(m), opacity: 1 });
  layer.meta = m;
  commit('إضافة نص');
  endPlacing();
  selectTextLayer(layer.id);
  openInlineEditor(layer);
}

function endPlacing() {
  placingText = false; placingTextBox = false; boxDrag = null;
  $('#btn-txt-place').classList.remove('btn-primary');
  restoreSelectMode();
  status('');
}

/* ═══════════════════ 2) تحديد الكائنات ═══════════════════ */
function newMask() {
  const c = document.createElement('canvas');
  c.width = state.width; c.height = state.height;
  const g = c.getContext('2d');
  g.fillStyle = '#000';               // 0 = مجهول
  g.fillRect(0, 0, c.width, c.height);
  return c;
}

function maskCtx() { return sel.mask.getContext('2d', { willReadFrequently: true }); }

export function initSelect() {
  const overlay = $('#overlay-canvas');
  const sSliders = {};
  $$('#panels [data-panel="select"] .slider').forEach((c) => { const s = makeSlider(c); sSliders[s.key] = s; });
  const sv = (k, d) => (sSliders[k] ? sSliders[k].value : d);

  const setTool = (tool) => {
    sel.tool = tool;
    $$('#sel-tools .chip').forEach((c) => c.classList.toggle('active', c.dataset.stool === tool));
    if (tool === 'rect') { canvas.setOverlayMode('rect'); status('اسحب مستطيلاً حول الكائن.', 'ok'); }
    else if (tool === 'auto') { canvas.setOverlayMode(null); status('التحديد التلقائي: تُجرَّب كل الخوارزميات (ومن ضمنها GrabCut والعصا الذكية) ويُختار الأدق.', 'ok'); }
    else if (tool === 'wand') {
      canvas.setOverlayMode('select');
      status('العصا السحرية: انقر على الكائن لانتقائه بلونه فوراً — نقرة أخرى تضيف منطقة، ومع Shift تستثني. عدّل «تسامح العصا» حسب تشابه الألوان.', 'ok');
    } else {
      canvas.setOverlayMode('select');
      if (!sel.mask || sel.mask.width !== state.width) sel.mask = newMask();
      if (tool === 'points') status('انقر لإضافة نقطة جسم (أخضر)، ومع Shift نقطة خلفية (أحمر).', 'ok');
      else status(tool === 'brush' ? 'ارسم فوق الكائن لتحديده يدوياً.' : 'ارسم لمحو أجزاء من التحديد.', 'ok');
    }
    canvas.refreshOverlay();
  };

  $$('#sel-tools .chip').forEach((c) => c.addEventListener('click', () => { if (needImage()) setTool(c.dataset.stool); }));

  // فتح اللوحة ⇒ تفعيل الوضع الحالي
  const panel = $('[data-panel="select"]');
  new MutationObserver(() => { if (panel.classList.contains('open') && state.image) setTool(sel.tool); })
    .observe(panel, { attributes: true, attributeFilter: ['class'] });

  // معاينة العصا السحرية (منقّاة ضد التكرار)
  let wandTimer = null;
  const scheduleWandPreview = () => {
    clearTimeout(wandTimer);
    if (!sel.seeds.length) { sel.wandTint = null; canvas.refreshOverlay(); return; }
    wandTimer = setTimeout(async () => {
      if (!state.image || sel.tool !== 'wand' || !sel.seeds.length) return;
      try {
        const resp = await api.previewMask(state.image, {
          method: 'wand',
          seeds: sel.seeds.map((s) => [s.x, s.y, s.kind]),
          wand_tolerance: sv('sel-wandtol', 32),
          iterations: sv('sel-iter', 10),
        });
        const img = new Image();
        img.onload = () => {
          // تلوين القناع بالأخضر للوضوح
          const tc = document.createElement('canvas');
          tc.width = img.width; tc.height = img.height;
          const tg = tc.getContext('2d');
          tg.drawImage(img, 0, 0);
          tg.globalCompositeOperation = 'source-in';
          tg.fillStyle = 'rgba(53,201,138,.95)';
          tg.fillRect(0, 0, tc.width, tc.height);
          sel.wandTint = tc;
          canvas.refreshOverlay();
        };
        img.src = toDataUrl(resp);
      } catch (err) {
        toast(err.message || 'تعذّرت معاينة التحديد.', 'warn');
      }
    }, 420);
  };

  // تفاعلات الطبقة العلوية في وضع select
  overlay.addEventListener('pointerdown', (e) => {
    if (canvas.getOverlayMode() !== 'select') return;
    const p = canvas.toImageCoords(e);
    if (sel.tool === 'wand') {
      sel.seeds.push({ x: p.x, y: p.y, kind: e.shiftKey ? 0 : 1 });
      canvas.refreshOverlay();
      scheduleWandPreview();
    } else if (sel.tool === 'points') {
      sel.points.push({ x: p.x, y: p.y, kind: e.shiftKey ? 'bg' : 'fg' });
      canvas.refreshOverlay();
    } else if (sel.tool === 'brush' || sel.tool === 'eraser') {
      sel.painting = true;
      const g = maskCtx();
      g.lineCap = 'round'; g.lineJoin = 'round';
      g.lineWidth = Math.max(4, sv('sel-brush', 24) / state.zoom);
      g.strokeStyle = sel.tool === 'brush' ? '#ffffff' : '#7f7f7f'; // 255 جسم / 128 خلفية
      g.beginPath(); g.moveTo(p.x, p.y); g.lineTo(p.x + 0.01, p.y + 0.01); g.stroke();
      canvas.refreshOverlay();
    }
  }, true);
  overlay.addEventListener('pointermove', (e) => {
    if (!sel.painting) return;
    const p = canvas.toImageCoords(e);
    const g = maskCtx();
    g.lineTo(p.x, p.y); g.stroke();
    canvas.refreshOverlay();
  });
  window.addEventListener('pointerup', () => { sel.painting = false; });

  $('#btn-sel-clear').addEventListener('click', () => {
    sel.points = [];
    sel.seeds = [];
    sel.wandTint = null;
    if (sel.mask) { const g = maskCtx(); g.fillStyle = '#000'; g.fillRect(0, 0, sel.mask.width, sel.mask.height); }
    state.subjectRect = null;
    canvas.refreshOverlay();
    status('صُفّرت مدخلات التحديد.', 'ok');
  });

  $('#btn-sel-apply').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ استخراج الكائن…', async () => {
      const opts = {
        feather: sv('sel-feather', 1.5),
        despeckle: 60,
        iterations: sv('sel-iter', 10),          // دقة GrabCut
        matte: checked('sel-matte'),             // تحسين الحواف الذكي
      };

      if (sel.tool === 'wand') {
        if (!sel.seeds.length) { toast('انقر بالعصا السحرية على الكائن أولاً.', 'warn'); return; }
        opts.method = 'wand';
        opts.seeds = sel.seeds.map((s) => [s.x, s.y, s.kind]);
        opts.wand_tolerance = sv('sel-wandtol', 32);
      } else if (sel.tool === 'auto') {
        opts.method = 'auto';
      } else {
        opts.method = 'grabcut';
        const r = state.subjectRect;
        if (r && Math.abs(r.x2 - r.x1) > 4 && Math.abs(r.y2 - r.y1) > 4) {
          const w = state.width, h = state.height;
          opts.rect = [r.x1 / w, r.y1 / h, (r.x2 - r.x1) / w, (r.y2 - r.y1) / h];
        }
        if (sel.points.length || sel.mask) {
          const hint = newMask();
          const g = hint.getContext('2d');
          if (sel.mask) g.drawImage(sel.mask, 0, 0);
          const rad = Math.max(5, Math.round(state.width / 90));
          for (const p of sel.points) {
            g.fillStyle = p.kind === 'fg' ? '#ffffff' : '#7f7f7f';
            g.beginPath(); g.arc(p.x, p.y, rad, 0, Math.PI * 2); g.fill();
          }
          opts.hint_mask = hint.toDataURL('image/png');
        }
        if (!opts.rect && !opts.hint_mask) {
          toast('حدّد بمستطيل أو نقاط أو رسم يدوي أولاً (أو اختر «تلقائي» أو «عصا سحرية»).', 'warn');
          return;
        }
      }

      const resp = await api.removeBg(state.image, opts);
      addLayer({ name: `تحديد ${state.layers.length + 1}`, type: 'select', dataUrl: toDataUrl(resp) });
      commit('استخراج الكائن كطبقة');
      if (sel.tool === 'wand') { sel.seeds = []; sel.wandTint = null; canvas.refreshOverlay(); }
      toast(`استُخرج الكائن طبقةً مستقلة فوق الأصل (${resp.method || 'auto'}).`, 'ok');
    });
  });

  // إعادة ضبط مدخلات التحديد عند صورة جديدة
  onChange((kind) => {
    if (kind === 'reset' || kind === 'image') { sel.points = []; sel.seeds = []; sel.wandTint = null; sel.mask = null; }
  });
}

/* ═══════════════════ 3) الطبقات ═══════════════════ */
export function initLayers() {
  const list = $('#layers-list');

  function render() {
    list.innerHTML = '';
    // الطبقة الأصل (مقفلة)
    const base = el('div', { class: 'layer-row base' });
    base.append(
      el('span', { class: 'l-ico', text: '🖼' }),
      el('span', { class: 'l-name', text: 'الصورة الأصل (أساس)' }),
      el('span', { class: 'l-lock', text: '🔒' }),
    );
    list.appendChild(base);

    if (!state.layers.length) {
      list.appendChild(el('p', { class: 'hint', text: 'لا طبقات إضافية بعد — ثبّت رسماً، أضف نصاً، أو استخرج تحديداً.' }));
    }

    [...state.layers].reverse().forEach((l) => {
      const cls = ['layer-row'];
      if (!l.visible) cls.push('hidden-l');
      if (l.id === state.selectedLayer) cls.push('selected');
      const row = el('div', { class: cls.join(' ') });
      const ico = l.type === 'text' ? '🅣' : l.type === 'select' ? '✂' : '✏';
      row.append(el('span', { class: 'l-ico', text: ico }), el('span', { class: 'l-name', text: l.name, title: l.name }));

      const mk = (txt, title, fn) => {
        const b = el('button', { class: 'btn icon-btn small', text: txt, title });
        b.addEventListener('click', fn);
        return b;
      };
      if (l.type === 'text' && l.meta) {
        row.append(mk('✎', 'اختيار النص وتعديله', () => selectTextLayer(l.id)));
      }
      row.append(
        mk('👁', l.visible ? 'إخفاء' : 'إظهار', () => {
          toggleLayer(l.id);
          updateCurrentHistory();     // في المكان — بلا نسخة جديدة
        }),
        mk('↑', 'أعلى', () => { if (moveLayer(l.id, 1)) updateCurrentHistory(); }),
        mk('↓', 'أسفل', () => { if (moveLayer(l.id, -1)) updateCurrentHistory(); }),
        mk('🗑', 'حذف الطبقة (يعود للصورة السابقة بلا نسخة جديدة)', () => {
          if (state.selectedLayer === l.id) deselectText();
          removeLayer(l.id);
          updateCurrentHistory();     // تعود الصورة السابقة دون إنشاء نسخة
          toast(`حُذفت الطبقة «${l.name}» — عادت الصورة السابقة (بلا نسخة جديدة).`, 'ok');
        }),
      );
      list.appendChild(row);
    });

    $('#layers-count').textContent = `${state.layers.length} طبقات`;
  }

  onChange((kind) => { if (kind === 'layers' || kind === 'history' || kind === 'image' || kind === 'reset') render(); });
  render();

  // دمج كل الطبقات في الصورة الأصل (عملية صريحة تُنشئ نسخة جديدة)
  $('#btn-layers-flatten').addEventListener('click', async () => {
    if (!needImage() || !state.layers.length) { toast('لا طبقات للدمج.', 'warn'); return; }
    await withBusy('جارٍ دمج الطبقات…', async () => {
      if (state.selectedLayer) deselectText();
      const c = document.createElement('canvas');
      c.width = state.width; c.height = state.height;
      const g = c.getContext('2d');
      const base = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = state.image; });
      g.drawImage(base, 0, 0);
      for (const l of state.layers) {
        if (!l.visible) continue;
        const li = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = l.dataUrl; });
        g.globalAlpha = l.opacity ?? 1;
        g.drawImage(li, 0, 0);
        g.globalAlpha = 1;
      }
      const url = c.toDataURL('image/png');
      state.layers = [];
      await setImageFromDataUrl(url, { label: 'دمج الطبقات بالصورة' });
      toast('دُمجت كل الطبقات في الصورة الأصل.', 'ok');
    });
  });

  // حذف كل الطبقات — في المكان، تعود الصورة السابقة بلا نسخة جديدة
  $('#btn-layers-clear').addEventListener('click', () => {
    if (!state.layers.length) { toast('لا طبقات.', 'warn'); return; }
    if (state.selectedLayer) deselectText();
    state.layers = [];
    updateCurrentHistory();
    emit('layers');
    toast('حُذفت كل الطبقات وعادت الصورة السابقة (بلا نسخة جديدة).', 'ok');
  });
}

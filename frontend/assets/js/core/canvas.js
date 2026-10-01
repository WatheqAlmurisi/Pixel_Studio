/**
 * محرك العرض على Canvas.
 * ======================
 * • عرض الصورة مع تكبير/تصغير وتحريك.
 * • طبقة Overlay للأدوات التفاعلية: القصّ، الرسم، مستطيل الجسم، نقاط الإمالة.
 * • تحويل الإحداثيات بين الشاشة والصورة في الاتجاهين.
 */

import { state, currentImage, loadImage } from './state.js';

const els = {};
let ctx = null;
let octx = null;
let baseImg = null;         // كائن Image الحالي
let drawStrokes = [];       // خطوط الرسم المؤقتة
let overlayMode = null;     // null | crop | draw | rect | perspective
let drag = null;            // حالة السحب الحالية
let pan = null;             // حالة التحريك

/* ═══════════════ التهيئة ═══════════════ */
export function initCanvas() {
  els.wrap = document.getElementById('canvas-wrap');
  els.stage = document.getElementById('canvas-stage');
  els.canvas = document.getElementById('img-canvas');
  els.overlay = document.getElementById('overlay-canvas');
  els.empty = document.getElementById('empty-state');
  ctx = els.canvas.getContext('2d');
  octx = els.overlay.getContext('2d');

  els.wrap.addEventListener('wheel', onWheel, { passive: false });
  els.overlay.addEventListener('pointerdown', onDown);
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  els.overlay.addEventListener('pointerleave', () => { if (drag?.kind === 'draw') onUp(); });
  window.addEventListener('resize', () => { if (state.image) fitToScreen(false); });

  document.getElementById('btn-zoom-in')?.addEventListener('click', () => setZoom(state.zoom * 1.25));
  document.getElementById('btn-zoom-out')?.addEventListener('click', () => setZoom(state.zoom / 1.25));
  document.getElementById('btn-zoom-fit')?.addEventListener('click', () => fitToScreen(true));
}

/* ═══════════════ العرض ═══════════════ */
export async function render() {
  const src = currentImage();
  if (!src) {
    els.stage.hidden = true;
    els.empty.hidden = false;
    return;
  }
  els.empty.hidden = true;
  els.stage.hidden = false;

  try {
    baseImg = await loadImage(src);
  } catch (e) {
    console.error(e);
    return;
  }
  els.canvas.width = baseImg.width;
  els.canvas.height = baseImg.height;
  els.overlay.width = baseImg.width;
  els.overlay.height = baseImg.height;

  ctx.clearRect(0, 0, baseImg.width, baseImg.height);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(baseImg, 0, 0);

  // رصّ الطبقات الإضافية فوق الصورة الأصل بترتيبها وشفافيتها
  for (const layer of state.layers) {
    if (!layer.visible || !layer.dataUrl) continue;
    try {
      const li = await loadImage(layer.dataUrl);
      ctx.save();
      ctx.globalAlpha = layer.opacity ?? 1;
      ctx.drawImage(li, 0, 0);
      ctx.restore();
    } catch (e) { /* طبقة تالفة تُتجاهل */ }
  }

  applyTransform();
  redrawOverlay();
}

/** تطبيق التكبير على العناصر */
export function applyTransform() {
  const w = Math.max(1, Math.round(baseImg?.width * state.zoom || 1));
  const h = Math.max(1, Math.round(baseImg?.height * state.zoom || 1));
  els.canvas.style.width = `${w}px`;
  els.canvas.style.height = `${h}px`;
  els.overlay.style.width = `${w}px`;
  els.overlay.style.height = `${h}px`;
  els.stage.style.width = `${w}px`;
  els.stage.style.height = `${h}px`;
  document.getElementById('zoom-label').textContent = `${Math.round(state.zoom * 100)}%`;
}

export function setZoom(z, center = true) {
  state.zoom = Math.min(16, Math.max(0.05, z));
  applyTransform();
}

export function fitToScreen(smooth = true) {
  if (!baseImg) return;
  const pad = 48;
  const aw = els.wrap.clientWidth - pad;
  const ah = els.wrap.clientHeight - pad;
  state.fitZoom = Math.min(aw / baseImg.width, ah / baseImg.height, 4);
  state.zoom = Math.max(0.05, state.fitZoom);
  applyTransform();
  if (smooth) els.wrap.scrollTo({ left: 0, top: 0, behavior: 'smooth' });
}

/* ═══════════════ تحويل الإحداثيات ═══════════════ */
export function toImageCoords(evt) {
  const r = els.canvas.getBoundingClientRect();
  return {
    x: Math.round((evt.clientX - r.left) / state.zoom),
    y: Math.round((evt.clientY - r.top) / state.zoom),
  };
}
export function toScreen(x, y) {
  const r = els.canvas.getBoundingClientRect();
  return { x: r.left + x * state.zoom, y: r.top + y * state.zoom };
}

/* ═══════════════ أدوات Overlay ═══════════════ */
export function setOverlayMode(mode) {
  overlayMode = mode;
  els.overlay.classList.toggle('active', mode !== null && mode !== 'pan');
  if (mode === null) {
    drag = null;
    redrawOverlay();
  }
}
export const getOverlayMode = () => overlayMode;
/** سياق الطبقة العلوية (لرسم معاينات أدوات التحديد) */
export const getOverlayCtx = () => octx;

/** خطّاف يُستدعى في نهاية كل إعادة رسم للطبقة العلوية (لمعاينات الأدوات) */
let overlayHook = null;
export function setOverlayHook(fn) { overlayHook = fn; }

function redrawOverlay() {
  if (!octx || !baseImg) return;
  octx.clearRect(0, 0, els.overlay.width, els.overlay.height);

  // خطوط الرسم
  for (const s of drawStrokes) paintStroke(octx, s);
  if (drag?.kind === 'draw' && drag.stroke) paintStroke(octx, drag.stroke);

  // مستطيل القصّ / الجسم
  if ((overlayMode === 'crop' || overlayMode === 'rect') && state[overlayMode === 'crop' ? 'cropRect' : 'subjectRect']) {
    const r = state[overlayMode === 'crop' ? 'cropRect' : 'subjectRect'];
    drawSelection(octx, r, overlayMode === 'crop' ? '#ffd166' : '#5b8cff');
  }

  // نقاط الإمالة المنظورية
  if (overlayMode === 'perspective' && state.perspPoints) {
    octx.save();
    octx.strokeStyle = '#35c98a';
    octx.lineWidth = 2 / state.zoom;
    octx.beginPath();
    state.perspPoints.forEach((p, i) => {
      if (i === 0) octx.moveTo(p[0], p[1]); else octx.lineTo(p[0], p[1]);
    });
    octx.closePath();
    octx.stroke();
    octx.fillStyle = '#35c98a';
    for (const p of state.perspPoints) {
      octx.beginPath();
      octx.arc(p[0], p[1], 8 / state.zoom, 0, Math.PI * 2);
      octx.fill();
    }
    octx.restore();
  }

  // معاينات الأدوات الخارجية (التحديد/النصوص) — تُرسم فوق كل شيء
  if (overlayHook) {
    try { overlayHook(octx); } catch (e) { console.error('[overlayHook]', e); }
  }
}

function drawSelection(c, r, color) {
  const { x, y, w, h } = normRect(r);
  c.save();
  // تعتيم الخارج
  c.fillStyle = 'rgba(0,0,0,.52)';
  c.fillRect(0, 0, els.overlay.width, els.overlay.height);
  c.globalCompositeOperation = 'destination-out';
  c.fillRect(x, y, w, h);
  c.globalCompositeOperation = 'source-over';
  // الحدود
  c.strokeStyle = color;
  c.lineWidth = 2 / state.zoom;
  c.setLineDash([7 / state.zoom, 5 / state.zoom]);
  c.strokeRect(x, y, w, h);
  c.setLineDash([]);
  // شبكة الأثلاث
  c.strokeStyle = 'rgba(255,255,255,.3)';
  c.lineWidth = 1 / state.zoom;
  for (let i = 1; i < 3; i++) {
    c.beginPath(); c.moveTo(x + (w * i) / 3, y); c.lineTo(x + (w * i) / 3, y + h); c.stroke();
    c.beginPath(); c.moveTo(x, y + (h * i) / 3); c.lineTo(x + w, y + (h * i) / 3); c.stroke();
  }
  // المقابض
  c.fillStyle = color;
  const hs = 7 / state.zoom;
  for (const [hx, hy] of [[x, y], [x + w, y], [x, y + h], [x + w, y + h]]) {
    c.fillRect(hx - hs / 2, hy - hs / 2, hs, hs);
  }
  c.restore();
}

function normRect(r) {
  return {
    x: Math.min(r.x1, r.x2), y: Math.min(r.y1, r.y2),
    w: Math.abs(r.x2 - r.x1), h: Math.abs(r.y2 - r.y1),
  };
}

/* ═══════════════ الرسم ═══════════════ */
function paintStroke(c, s) {
  c.save();
  c.globalAlpha = s.opacity;
  c.lineCap = 'round';
  c.lineJoin = 'round';

  if (s.tool === 'eraser') {
    c.globalCompositeOperation = 'destination-out';
    c.strokeStyle = 'rgba(0,0,0,1)';
  } else {
    c.strokeStyle = s.color;
    c.fillStyle = s.color;
  }
  c.lineWidth = s.size;

  if (s.tool === 'text') {
    const fam = s.font || '"Segoe UI", Tahoma, sans-serif';
    c.font = `${s.bold ? 'bold ' : ''}${Math.max(6, s.size * 2.4)}px ${fam}`;
    c.textAlign = s.align || 'center';
    c.textBaseline = 'middle';
    if (s.rotate) { c.translate(s.x, s.y); c.rotate((s.rotate * Math.PI) / 180); c.translate(-s.x, -s.y); }
    if (s.shadow) { c.shadowColor = 'rgba(0,0,0,.55)'; c.shadowBlur = s.size * 0.8; c.shadowOffsetY = s.size * 0.25; }
    if (s.outline) {
      c.save();
      c.lineWidth = Math.max(1, s.size * 0.35);
      c.strokeStyle = s.outlineColor || '#101418';
      c.strokeText(s.text, s.x, s.y);
      c.restore();
    }
    c.fillText(s.text, s.x, s.y);
    c.restore();
    return;
  }
  if (s.tool === 'rect') {
    const r = normRect(s);
    if (s.fill) c.fillRect(r.x, r.y, r.w, r.h); else c.strokeRect(r.x, r.y, r.w, r.h);
    c.restore(); return;
  }
  if (s.tool === 'ellipse') {
    const r = normRect(s);
    c.beginPath();
    c.ellipse(r.x + r.w / 2, r.y + r.h / 2, Math.max(1, r.w / 2), Math.max(1, r.h / 2), 0, 0, Math.PI * 2);
    if (s.fill) c.fill(); else c.stroke();
    c.restore(); return;
  }
  if (s.tool === 'arrow') {
    drawArrow(c, s.x1, s.y1, s.x2, s.y2, s.size);
    c.restore(); return;
  }
  if (s.tool === 'spray') {
    for (const p of s.points) {
      c.globalAlpha = s.opacity * 0.35;
      c.beginPath();
      c.arc(p[0], p[1], Math.max(0.6, s.size / 9), 0, Math.PI * 2);
      c.fill();
    }
    c.restore(); return;
  }
  // brush / pencil / line / eraser
  if (s.tool === 'pencil') { c.lineWidth = Math.max(1, s.size / 2.6); c.globalAlpha = s.opacity; }
  if (s.tool === 'line') {
    c.beginPath(); c.moveTo(s.x1, s.y1); c.lineTo(s.x2, s.y2); c.stroke();
    c.restore(); return;
  }
  if (!s.points?.length) { c.restore(); return; }
  c.beginPath();
  c.moveTo(s.points[0][0], s.points[0][1]);
  for (let i = 1; i < s.points.length; i++) {
    const [px, py] = s.points[i - 1];
    const [cx2, cy2] = s.points[i];
    c.quadraticCurveTo(px, py, (px + cx2) / 2, (py + cy2) / 2);
  }
  c.stroke();
  c.restore();
}

function drawArrow(c, x1, y1, x2, y2, size) {
  const head = Math.max(9, size * 2.6);
  const ang = Math.atan2(y2 - y1, x2 - x1);
  c.beginPath(); c.moveTo(x1, y1); c.lineTo(x2, y2); c.stroke();
  c.beginPath();
  c.moveTo(x2, y2);
  c.lineTo(x2 - head * Math.cos(ang - Math.PI / 7), y2 - head * Math.sin(ang - Math.PI / 7));
  c.lineTo(x2 - head * Math.cos(ang + Math.PI / 7), y2 - head * Math.sin(ang + Math.PI / 7));
  c.closePath();
  c.fill();
}

/** إضافة خط رسم مكتمل */
export function pushStroke(stroke) { drawStrokes.push(stroke); redrawOverlay(); }
export function popStroke() { const s = drawStrokes.pop(); redrawOverlay(); return s; }
export function clearStrokes() { drawStrokes = []; redrawOverlay(); }
/** إعادة رسم الطبقة العلوية فقط (لمعاينات الأدوات دون إعادة تحميل الصورة) */
export function refreshOverlay() { redrawOverlay(); }
export const strokeCount = () => drawStrokes.length;
export const getStrokes = () => drawStrokes;

/** رسم كل الخطوط على canvas وإرجاع data URL شفاف */
export function exportDrawLayer() {
  if (!drawStrokes.length) return null;
  const c = document.createElement('canvas');
  c.width = baseImg.width; c.height = baseImg.height;
  const cc = c.getContext('2d');
  for (const s of drawStrokes) paintStroke(cc, s);
  return c.toDataURL('image/png');
}

/* ═══════════════ الأحداث ═══════════════ */
function onWheel(e) {
  if (!e.ctrlKey && !e.metaKey) return;      // التكبير فقط مع Ctrl
  e.preventDefault();
  setZoom(state.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12));
}

function onDown(e) {
  if (!baseImg) return;
  const p = toImageCoords(e);
  els.overlay.setPointerCapture?.(e.pointerId);

  if (overlayMode === 'crop' || overlayMode === 'rect') {
    const key = overlayMode === 'crop' ? 'cropRect' : 'subjectRect';
    let r = { x1: p.x, y1: p.y, x2: p.x, y2: p.y };
    drag = { kind: overlayMode, key, start: p };
    state[key] = r;
    redrawOverlay();
    window.dispatchEvent(new CustomEvent('overlay:drag', { detail: { mode: overlayMode } }));
    return;
  }

  if (overlayMode === 'perspective') {
    // تحريك أقرب نقطة
    const pts = state.perspPoints;
    let best = -1, bd = 1e9;
    pts.forEach((q, i) => { const d = (q[0] - p.x) ** 2 + (q[1] - p.y) ** 2; if (d < bd) { bd = d; best = i; } });
    drag = { kind: 'persp', index: best };
    return;
  }

  if (overlayMode === 'draw') {
    const cfg = window.__drawConfig || {};
    const stroke = {
      tool: cfg.tool || 'brush',
      color: cfg.color || '#e63946',
      size: Math.max(1, (cfg.size || 14) / state.zoom),
      opacity: (cfg.opacity ?? 100) / 100,
      fill: !!cfg.fill,
      text: cfg.text || '',
      font: cfg.font || '', bold: !!cfg.bold, outline: !!cfg.outline,
      outlineColor: cfg.outlineColor || '#101418', shadow: !!cfg.shadow,
      rotate: parseFloat(cfg.rotate || 0), align: cfg.align || 'center',
      x: p.x, y: p.y, x1: p.x, y1: p.y, x2: p.x, y2: p.y,
      points: [[p.x, p.y]],
    };
    if (stroke.tool === 'text') {
      pushStroke(stroke);
      window.dispatchEvent(new CustomEvent('overlay:text-placed'));
      return;
    }
    if (stroke.tool === 'picker') {
      const px = ctx.getImageData(Math.max(0, Math.min(baseImg.width - 1, p.x)),
        Math.max(0, Math.min(baseImg.height - 1, p.y)), 1, 1).data;
      window.dispatchEvent(new CustomEvent('overlay:picked', {
        detail: { hex: `#${[px[0], px[1], px[2]].map((v) => v.toString(16).padStart(2, '0')).join('')}` },
      }));
      return;
    }
    drag = { kind: 'draw', stroke };
    return;
  }
}

function onMove(e) {
  if (!drag || !baseImg) return;
  const p = toImageCoords(e);

  if (drag.kind === 'draw') {
    const s = drag.stroke;
    s.x2 = p.x; s.y2 = p.y;
    if (s.tool === 'brush' || s.tool === 'pencil' || s.tool === 'eraser' || s.tool === 'spray') {
      const last = s.points[s.points.length - 1];
      if (Math.hypot(p.x - last[0], p.y - last[1]) > Math.max(0.8, s.size / 14)) s.points.push([p.x, p.y]);
    }
    redrawOverlay();
    return;
  }
  if (drag.kind === 'persp') {
    state.perspPoints[drag.index] = [p.x, p.y];
    redrawOverlay();
    return;
  }
  // crop / rect
  const r = state[drag.key];
  const aspect = drag.aspect;
  if (aspect) {
    const w = p.x - drag.start.x;
    const h = w / aspect;
    r.x2 = p.x;
    r.y2 = drag.start.y + (p.y >= drag.start.y ? Math.abs(h) : -Math.abs(h));
  } else {
    r.x2 = p.x; r.y2 = p.y;
  }
  redrawOverlay();
  window.dispatchEvent(new CustomEvent('overlay:drag', { detail: { mode: drag.kind, rect: normRect(r) } }));
}

function onUp() {
  if (!drag) return;
  if (drag.kind === 'draw') pushStroke(drag.stroke);
  else window.dispatchEvent(new CustomEvent('overlay:end', { detail: { mode: drag.kind } }));
  drag = null;
}

/** ضبط نسبة القصّ أثناء السحب */
export function setDragAspect(a) {
  if (drag && (drag.kind === 'crop' || drag.kind === 'rect')) drag.aspect = a;
  state.__nextAspect = a;
}

/** تهيئة نقاط الإمالة المنظورية */
export function initPerspective() {
  if (!baseImg) return;
  const w = baseImg.width, h = baseImg.height;
  state.perspPoints = [[0, 0], [w, 0], [w, h], [0, h]];
  setOverlayMode('perspective');
  redrawOverlay();
}
export const getPerspectivePoints = () => state.perspPoints;
export const imageSize = () => (baseImg ? { w: baseImg.width, h: baseImg.height } : { w: 0, h: 0 });

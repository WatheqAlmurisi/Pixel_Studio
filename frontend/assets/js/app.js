/**
 * استوديو بكسل — نقطة دخول الواجهة.
 * =================================
 * يربط الوحدات: الحالة، Canvas، اللوحات، الاختصارات، الفتح/التنزيل.
 */

import {
  state, onChange, setImageFromDataUrl, reset, undo, redo, canUndo, canRedo, humanSize,
} from './core/state.js';
import { api, health, toDataUrl, download, stats } from './core/api.js';
import * as canvas from './core/canvas.js';
import {
  $, $$, toast, status, withBusy, fileToDataUrl, disableNativeDnd, setDisabled, el,
} from './ui/helpers.js';
import { initConvert, initGeometry, initCrop, initDraw } from './ui/panels.js';
import { initAdjust, initFilters } from './ui/panels2.js';
import { initSegmentation, initBlend, initCreative } from './ui/panels3.js';
import { initBackgrounds, initBatch } from './ui/panels4.js';
import { initText, initSelect, initLayers } from './ui/panels6.js';
import { initRestore, initRetouch, initDocument } from './ui/panels7.js';
import { initHistory, initAnalysis } from './ui/panels5.js';
import { initTour, maybeStartTour, restartTour } from './ui/tour.js';

/* ═══════════════════ الإقلاع ═══════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  canvas.initCanvas();
  disableNativeDnd();

  initTheme();
  initMenu();
  initTour();
  initAccordion();
  initSidebars();
  initHistory();
  initAnalysis();
  initConvert();
  initGeometry();
  initCrop();
  initDraw();
  initAdjust();
  initFilters();
  initBlend();
  initCreative();
  initBackgrounds();
  initBatch();
  initText();
  initSelect();
  initLayers();
  initRestore();
  initRetouch();
  initDocument();
  await initSegmentation();

  initFileOpen();
  initDownload();
  initHelp();
  initAbout();
  initCompare();
  initShortcuts();
  initInfo();
  bindState();

  await checkHealth();
  openPanel('convert');
  status('جاهز — افتح صورة للبدء.');
  maybeStartTour();
});

// واجهة برمجية للاختبار الآلي (لا تُستخدم من الواجهة نفسها)
window.__PS = { state, canvas, api, stats, ready: true };

/* ═══════════════════ فحص الخادم ═══════════════════ */
async function checkHealth() {
  const box = $('#capabilities');
  try {
    const h = await health();
    state.online = true;
    state.capabilities = h.capabilities;
    const caps = [
      ['صيغ الإخراج', h.capabilities.formats_output?.length || 0],
      ['فلاتر', h.capabilities.filters || 0],
      ['أنماط مزج', h.capabilities.blend_modes || 0],
      ['مؤثرات', h.capabilities.creative_effects || 0],
      ['خلفيات', h.capabilities.backgrounds || 0],
      ['خطوات السلسلة', h.capabilities.pipeline_operations?.length || 0],
    ];
    box.innerHTML = '';
    for (const [label, value] of caps) {
      const d = document.createElement('div');
      d.className = 'cap';
      d.innerHTML = `<b>${value}</b><span>${label}</span>`;
      box.appendChild(d);
    }
    status(`الخادم متصل · ${h.app} v${h.version} · Pillow ${h.libraries.pillow} · OpenCV ${h.libraries.opencv}`, 'ok');
  } catch (e) {
    state.online = false;
    box.innerHTML = '<div class="cap"><b>!</b><span>الخادم غير متاح</span></div>';
    status('تعذّر الاتصال بالخادم الخلفي — شغّل `python -m uvicorn app.main:app`.', 'err');
    toast('الخادم الخلفي غير متاح. راجع ملف README لتشغيله.', 'err', 7000);
  }
}

/* ═══════════════════ اللوحات (Accordion) ═══════════════════ */
function initAccordion() {
  $$('#panels .panel-title').forEach((title) => {
    title.addEventListener('click', () => {
      const panel = title.parentElement;
      const wasOpen = panel.classList.contains('open');
      $$('#panels .panel').forEach((p) => p.classList.remove('open'));
      if (!wasOpen) panel.classList.add('open');
      // إلغاء وضع الطبقة العلوية عند إغلاق اللوحات التفاعلية
      if (wasOpen && ['crop', 'draw', 'segment', 'select'].includes(panel.dataset.panel)) {
        canvas.setOverlayMode(null);
        status('');
      }
    });
  });
}

function openPanel(name) {
  const panel = $(`#panels [data-panel="${name}"]`);
  if (!panel) return;
  $$('#panels .panel').forEach((p) => p.classList.remove('open'));
  panel.classList.add('open');
  panel.scrollIntoView({ block: 'start', behavior: 'smooth' });
}

/* ═══════════════ طي/فتح وتحجيم الأشرطة الجانبية ═══════════════ */
function initSidebars() {
  const root = document.documentElement;
  const store = {
    get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* مُعطّل */ } },
  };

  const setup = (gripId, btnId, varName, bodyClass, defVal, min, max, side) => {
    const grip = $(`#${gripId}`);
    const btn = $(`#${btnId}`);
    if (!grip || !btn) return;

    const syncBtn = () => {
      const collapsed = document.body.classList.contains(bodyClass);
      btn.textContent = side === 'start' ? (collapsed ? '❮' : '❯') : (collapsed ? '❯' : '❮');
    };

    // استعادة العرض وحالة الطي المحفوظة
    const savedW = parseInt(store.get(`ps.${varName}`, ''), 10);
    if (Number.isFinite(savedW)) {
      root.style.setProperty(varName, `${Math.min(max, Math.max(min, savedW))}px`);
    }
    if (store.get(`ps.${bodyClass}`, '') === '1') document.body.classList.add(bodyClass);
    syncBtn();

    // زر الطي/الفتح
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      document.body.classList.toggle(bodyClass);
      store.set(`ps.${bodyClass}`, document.body.classList.contains(bodyClass) ? '1' : '0');
      syncBtn();
    });

    // سحب المقبض لتغيير العرض
    grip.addEventListener('pointerdown', (e) => {
      if (e.target === btn) return;
      e.preventDefault();
      grip.classList.add('dragging');
      grip.setPointerCapture(e.pointerId);
      const move = (ev) => {
        // RTL: الشريط الأيمن عرضه = عرض النافذة − موضع المؤشر، والأيسر = موضع المؤشر
        const w = side === 'start' ? window.innerWidth - ev.clientX : ev.clientX;
        root.style.setProperty(varName, `${Math.min(max, Math.max(min, Math.round(w)))}px`);
      };
      const up = () => {
        grip.classList.remove('dragging');
        grip.removeEventListener('pointermove', move);
        grip.removeEventListener('pointerup', up);
        store.set(`ps.${varName}`, getComputedStyle(root).getPropertyValue(varName).trim());
      };
      grip.addEventListener('pointermove', move);
      grip.addEventListener('pointerup', up);
    });

    // نقرة مزدوجة: إعادة العرض الافتراضي
    grip.addEventListener('dblclick', (e) => {
      if (e.target === btn) return;
      root.style.setProperty(varName, `${defVal}px`);
      store.set(`ps.${varName}`, `${defVal}px`);
    });
  };

  setup('grip-tools', 'grip-tools-btn', '--side-r', 'no-tools', 336, 260, 560, 'start');
  setup('grip-hist', 'grip-hist-btn', '--side-l', 'no-history', 250, 200, 460, 'end');
}

/* ═══════════════════ فتح الصور ═══════════════════ */
function initFileOpen() {
  const handler = async (files) => {
    const list = Array.from(files || []).filter((f) => f.type.startsWith('image/'));
    if (!list.length) { toast('الملف المختار ليس صورة.', 'warn'); return; }
    const file = list[0];
    if (list.length > 1) {
      // أكثر من صورة ⇒ تُحوَّل تلقائياً إلى لوحة الدفعات
      toast(`${list.length} صور — أُضيفت إلى لوحة الدفعات.`, 'info');
      openPanel('batch');
    }
    await withBusy('جارٍ فتح الصورة…', async () => {
      reset();
      state.fileName = file.name;
      const data = await fileToDataUrl(file);
      await setImageFromDataUrl(data, { label: `فتح: ${file.name}`, asOriginal: true });
      canvas.fitToScreen(true);
      toast(`فُتحت ${file.name} · ${state.width}×${state.height}`, 'ok');
    });
    if (list.length > 1) feedBatch(list);
  };

  $('#file-open').addEventListener('change', (e) => handler(e.target.files));
  $('#file-open-2')?.addEventListener('change', (e) => handler(e.target.files));

  // السحب والإفلات على منطقة العمل
  const wrap = $('#canvas-wrap');
  ['dragover', 'dragenter'].forEach((ev) => wrap.addEventListener(ev, (e) => { e.preventDefault(); }));
  wrap.addEventListener('drop', (e) => {
    e.preventDefault();
    if (e.dataTransfer?.files?.length) handler(e.dataTransfer.files);
  });

  // الصور التجريبية
  const samples = [sampleProduct, sampleGradient, samplePortrait];
  let idx = 0;
  const loadSample = async () => {
    await withBusy('جارٍ توليد العيّنة…', async () => {
      reset();
      const data = samples[idx % samples.length]();
      idx++;
      state.fileName = `sample-${idx}.png`;
      await setImageFromDataUrl(data, { label: 'صورة تجريبية', asOriginal: true });
      canvas.fitToScreen(true);
      toast('تم تحميل صورة تجريبية مولّدة في المتصفح.', 'ok');
    });
  };
  $('#btn-sample').addEventListener('click', loadSample);
  $('#btn-sample-2')?.addEventListener('click', loadSample);
}

/** تغذية لوحة الدفعات بصور */
async function feedBatch(files) {
  const dz = $('#batch-drop');
  dz?.click?.();
  // نمرّر الملفات عبر حدث مخصص تلتقطه اللوحة
  window.dispatchEvent(new CustomEvent('batch:add', { detail: { files } }));
}

/* ═══════════════════ عيّنات مولّدة في المتصفح ═══════════════════ */
function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return c;
}

/** منتج على خلفية استوديو (يُظهر قوة إزالة الخلفية) */
function sampleProduct() {
  const W = 900, H = 900;
  const c = makeCanvas(W, H), g = c.getContext('2d');
  const bgGrad = g.createLinearGradient(0, 0, 0, H);
  bgGrad.addColorStop(0, '#f6f7f9');
  bgGrad.addColorStop(1, '#c9ccd3');
  g.fillStyle = bgGrad;
  g.fillRect(0, 0, W, H);

  // ظل المنتج
  g.save();
  g.translate(W / 2, H * 0.80);
  g.scale(1, 0.26);
  const sh = g.createRadialGradient(0, 0, 10, 0, 0, 240);
  sh.addColorStop(0, 'rgba(0,0,0,.42)');
  sh.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = sh;
  g.beginPath(); g.arc(0, 0, 240, 0, Math.PI * 2); g.fill();
  g.restore();

  // جسم الزجاجة
  const body = g.createLinearGradient(W * 0.34, 0, W * 0.66, 0);
  body.addColorStop(0, '#8e1b26');
  body.addColorStop(0.35, '#e0414f');
  body.addColorStop(0.62, '#b8232f');
  body.addColorStop(1, '#6d1219');
  g.fillStyle = body;
  roundRect(g, W * 0.35, H * 0.30, W * 0.30, H * 0.46, 34);
  g.fill();

  // عنق الزجاجة
  g.fillStyle = '#9c1f2a';
  roundRect(g, W * 0.445, H * 0.19, W * 0.11, H * 0.13, 12); g.fill();
  // الغطاء
  const cap = g.createLinearGradient(W * 0.43, 0, W * 0.57, 0);
  cap.addColorStop(0, '#d8b25a'); cap.addColorStop(0.5, '#f7e6ad'); cap.addColorStop(1, '#b8913c');
  g.fillStyle = cap;
  roundRect(g, W * 0.435, H * 0.13, W * 0.13, H * 0.075, 8); g.fill();

  // الملصق
  g.fillStyle = 'rgba(252,250,246,.95)';
  roundRect(g, W * 0.385, H * 0.44, W * 0.23, H * 0.19, 10); g.fill();
  g.fillStyle = '#7a1420';
  g.font = `bold ${Math.round(W * 0.042)}px Georgia, serif`;
  g.textAlign = 'center';
  g.fillText('PIXEL', W / 2, H * 0.525);
  g.font = `${Math.round(W * 0.022)}px Georgia, serif`;
  g.fillStyle = '#9a8f80';
  g.fillText('STUDIO · 2026', W / 2, H * 0.565);

  // لمعة
  g.save();
  g.globalAlpha = 0.28;
  g.fillStyle = '#fff';
  roundRect(g, W * 0.385, H * 0.33, W * 0.035, H * 0.38, 16); g.fill();
  g.restore();

  return c.toDataURL('image/png');
}

/** منظر طبيعي متدرّج (للفلاتر والمؤثرات) */
function sampleGradient() {
  const W = 1000, H = 700;
  const c = makeCanvas(W, H), g = c.getContext('2d');
  const sky = g.createLinearGradient(0, 0, 0, H * 0.72);
  sky.addColorStop(0, '#12224a');
  sky.addColorStop(0.45, '#4a5fa5');
  sky.addColorStop(0.8, '#e8a06a');
  sky.addColorStop(1, '#f7cf9a');
  g.fillStyle = sky; g.fillRect(0, 0, W, H);

  // الشمس
  const sun = g.createRadialGradient(W * 0.72, H * 0.55, 6, W * 0.72, H * 0.55, 130);
  sun.addColorStop(0, 'rgba(255,240,200,.95)');
  sun.addColorStop(1, 'rgba(255,200,120,0)');
  g.fillStyle = sun;
  g.beginPath(); g.arc(W * 0.72, H * 0.55, 130, 0, Math.PI * 2); g.fill();

  // جبال
  const layers = [
    { y: 0.62, color: '#2d3a5e', amp: 0.10 },
    { y: 0.70, color: '#202a47', amp: 0.08 },
    { y: 0.80, color: '#151d33', amp: 0.06 },
  ];
  for (const L of layers) {
    g.fillStyle = L.color;
    g.beginPath();
    g.moveTo(0, H);
    for (let x = 0; x <= W; x += 12) {
      const y = H * L.y
        + Math.sin(x / 140 + L.y * 9) * H * L.amp
        + Math.sin(x / 47 + L.y * 21) * H * L.amp * 0.4;
      g.lineTo(x, y);
    }
    g.lineTo(W, H); g.closePath(); g.fill();
  }

  // الماء
  const water = g.createLinearGradient(0, H * 0.86, 0, H);
  water.addColorStop(0, '#33406b'); water.addColorStop(1, '#0e1428');
  g.fillStyle = water; g.fillRect(0, H * 0.86, W, H * 0.14);
  g.globalAlpha = 0.35;
  for (let i = 0; i < 40; i++) {
    g.fillStyle = i % 2 ? '#f7cf9a' : '#8fa3d8';
    const y = H * 0.87 + Math.random() * H * 0.12;
    g.fillRect(Math.random() * W, y, 18 + Math.random() * 60, 1.4);
  }
  g.globalAlpha = 1;
  return c.toDataURL('image/jpeg', 0.94);
}

/** بورتريه هندسي (لتنعيم البشرة والتحديد) */
function samplePortrait() {
  const W = 800, H = 1000;
  const c = makeCanvas(W, H), g = c.getContext('2d');
  const bg = g.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, '#2b3a55'); bg.addColorStop(1, '#141d2e');
  g.fillStyle = bg; g.fillRect(0, 0, W, H);

  // هالة
  const halo = g.createRadialGradient(W / 2, H * 0.38, 20, W / 2, H * 0.38, 380);
  halo.addColorStop(0, 'rgba(120,160,255,.35)');
  halo.addColorStop(1, 'rgba(120,160,255,0)');
  g.fillStyle = halo; g.fillRect(0, 0, W, H);

  // الجسم
  g.fillStyle = '#3f5679';
  g.beginPath();
  g.moveTo(W * 0.18, H);
  g.quadraticCurveTo(W * 0.5, H * 0.62, W * 0.82, H);
  g.closePath(); g.fill();

  // الرأس
  const skin = g.createLinearGradient(W * 0.35, H * 0.12, W * 0.65, H * 0.55);
  skin.addColorStop(0, '#f0c9a8'); skin.addColorStop(1, '#c99473');
  g.fillStyle = skin;
  g.beginPath();
  g.ellipse(W / 2, H * 0.33, W * 0.155, H * 0.16, 0, 0, Math.PI * 2);
  g.fill();

  // الشعر
  g.fillStyle = '#2a2018';
  g.beginPath();
  g.ellipse(W / 2, H * 0.255, W * 0.165, H * 0.115, 0, Math.PI, Math.PI * 2);
  g.fill();

  // الملامح
  g.fillStyle = '#3a2a20';
  g.beginPath(); g.ellipse(W * 0.44, H * 0.325, 11, 7, 0, 0, Math.PI * 2); g.fill();
  g.beginPath(); g.ellipse(W * 0.56, H * 0.325, 11, 7, 0, 0, Math.PI * 2); g.fill();
  g.strokeStyle = '#8d5b41'; g.lineWidth = 5;
  g.beginPath(); g.arc(W / 2, H * 0.40, 26, 0.15 * Math.PI, 0.85 * Math.PI); g.stroke();

  // ضجيج خفيف لإظهار أثر تقليل الضوضاء
  const img = g.getImageData(0, 0, W, H);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (Math.random() - 0.5) * 22;
    img.data[i] += n; img.data[i + 1] += n; img.data[i + 2] += n;
  }
  g.putImageData(img, 0, 0);
  return c.toDataURL('image/jpeg', 0.95);
}

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

/* ═══════════════════ التنزيل ═══════════════════ */
function initDownload() {
  const modal = $('#download-modal');
  const fmt = $('#dl-format');
  const q = $('#dl-quality');
  const qv = $('#dl-q-val');
  const qrow = $('#dl-quality-row');
  const info = $('#dl-info');

  const sync = () => {
    const lossy = ['jpeg', 'webp', 'avif'].includes(fmt.value);
    qrow.style.display = lossy ? '' : 'none';
    qv.textContent = q.value;
    info.textContent = state.image
      ? `${state.width}×${state.height} · ${(state.sizeBytes / 1024).toFixed(1)} ك.بايت حاليًا`
      : '—';
  };
  fmt.addEventListener('change', sync);
  q.addEventListener('input', sync);

  $('#btn-download').addEventListener('click', () => {
    if (!state.image) { toast('لا توجد صورة للتنزيل.', 'warn'); return; }
    $('#dl-name').value = state.fileName.replace(/\.[^.]+$/, '') || 'pixel-studio';
    fmt.value = state.format === 'jpg' ? 'jpeg' : (state.format || 'png');
    sync();
    modal.hidden = false;
  });
  $('#btn-dl-close').addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });

  $('#btn-dl-go').addEventListener('click', () => {
    const name = ($('#dl-name').value || 'image').replace(/[^\w\u0600-\u06FF.-]+/g, '_');
    const ext = fmt.value === 'jpeg' ? 'jpg' : fmt.value;
    const filename = name.toLowerCase().endsWith(`.${ext}`) ? name : `${name}.${ext}`;
    withBusy('جارٍ تجهيز الملف…', async () => {
      try {
        const size = await download(state.image, filename, fmt.value, parseInt(q.value, 10));
        toast(`تم تنزيل ${filename} (${humanSize(size)})`, 'ok');
        modal.hidden = true;
      } catch (e) {
        // بديل: تنزيل مباشر من المتصفح عند تعذّر الخادم
        const a = document.createElement('a');
        a.href = state.image;
        a.download = filename;
        a.click();
        toast('نُزّلت الصورة مباشرة من المتصفح (بدون إعادة ترميز).', 'warn');
        modal.hidden = true;
      }
    });
  });
}

/* ═══════════════════ الدليل التعليمي: قراءة داخل الموقع + تحميل ═══════════════════ */
function initHelp() {
  const modal = $('#help-modal');
  const frame = $('#help-frame');

  const openHelp = () => {
    if (!frame.src || frame.src === 'about:blank') frame.src = '/help';
    modal.hidden = false;
    status('الدليل التعليمي: للقراءة داخل الموقع، وللتحميل «تحميل ملف الدليل» من القائمة.', 'ok');
  };
  $('#mi-help')?.addEventListener('click', () => { closeMenu(); openHelp(); });
  $('#mi-tour')?.addEventListener('click', () => { closeMenu(); restartTour(); });
  $('#mi-help-download')?.addEventListener('click', () => closeMenu());
  $('#btn-help-close').addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });
}

/* ═══════════════ الوضع الليلي/النهاري ═══════════════ */
function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem('ps.theme'); } catch { /* مُعطّل */ }
  const set = (light) => {
    document.body.classList.toggle('light', light);
    $('#btn-theme .ico-moon').hidden = light;
    $('#btn-theme .ico-sun').hidden = !light;
    $('#btn-theme').title = light ? 'التحويل إلى الوضع الليلي' : 'التحويل إلى الوضع النهاري';
    try { localStorage.setItem('ps.theme', light ? 'light' : 'dark'); } catch { /* مُعطّل */ }
  };
  set(saved === 'light');
  $('#btn-theme').addEventListener('click', () => {
    set(!document.body.classList.contains('light'));
  });
}

/* ═══════════════ قائمة الثلاث نقاط ═══════════════ */
function closeMenu() {
  const m = $('#app-menu');
  if (m) m.hidden = true;
  $('#btn-menu')?.setAttribute('aria-expanded', 'false');
}
function initMenu() {
  const btn = $('#btn-menu');
  const menu = $('#app-menu');
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = menu.hidden;
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
  });
  menu.addEventListener('click', (e) => e.stopPropagation());
  document.addEventListener('click', () => closeMenu());
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMenu(); });
}

/* ═══════════════════ المقارنة قبل/بعد ═══════════════════ */
function initCompare() {
  const btn = $('#btn-compare');
  const layer = $('#compare-layer');
  const img = $('#compare-img');
  const handle = $('#compare-handle');
  let active = false;

  btn.addEventListener('click', () => {
    if (!state.image) { toast('لا توجد صورة.', 'warn'); return; }
    active = !active;
    layer.hidden = !active;
    btn.classList.toggle('btn-primary', active);
    if (active) {
      img.src = state.original || state.image;
      setSplit(50);
      status('وضع المقارنة: الأصل على اليمين، النتيجة على اليسار.', 'ok');
    } else {
      status('');
    }
  });

  function setSplit(pct) {
    const p = Math.min(98, Math.max(2, pct));
    handle.style.insetInlineStart = `${p}%`;
    img.style.clipPath = `inset(0 0 0 ${p}%)`;
  }

  const move = (e) => {
    if (!active) return;
    const r = layer.getBoundingClientRect();
    // في RTL: نسبة الموضع من الحافة اليمنى
    const x = (e.clientX - r.left) / r.width * 100;
    setSplit(x);
  };
  handle.addEventListener('pointerdown', (e) => {
    handle.setPointerCapture(e.pointerId);
    const mm = (ev) => move(ev);
    const up = () => { window.removeEventListener('pointermove', mm); window.removeEventListener('pointerup', up); };
    window.addEventListener('pointermove', mm);
    window.addEventListener('pointerup', up);
  });
  layer.addEventListener('pointerdown', move);
}

/* ═══════════════════ الاختصارات ═══════════════════ */
function initShortcuts() {
  window.addEventListener('keydown', (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '');
    if (typing) return;

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
      e.preventDefault();
      if (undo()) toast('تراجع', 'info', 1200);
    } else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))) {
      e.preventDefault();
      if (redo()) toast('إعادة', 'info', 1200);
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault();
      $('#btn-download').click();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'o') {
      e.preventDefault();
      $('#file-open').click();
    } else if (e.key === '0') {
      canvas.fitToScreen(true);
    } else if (e.key === '+' || e.key === '=') {
      canvas.setZoom(state.zoom * 1.2);
    } else if (e.key === '-') {
      canvas.setZoom(state.zoom / 1.2);
    } else if (e.key === 'Escape') {
      canvas.setOverlayMode(null);
      $('#download-modal').hidden = true;
      $('#help-modal').hidden = true;
      $('#about-modal').hidden = true;
    }
  });
}

/* ═══════════════════ قسم المطوّر ═══════════════════ */
export const DEVELOPER = {
  // أسماء فريق التطوير (تُعدَّل من هنا؛ سطر التواصل اختياري)
  names: ['واثق المريسي', 'عبدالله الجحافي', 'ايمن الوهبي', 'عمر الزمر'],
  role: 'فريق تطوير استوديو بكسل',
  bio: '',
  stack: ['Python · FastAPI', 'OpenCV · NumPy · Pillow', 'HTML/CSS/JS · Canvas API'],
  contact: '',
  version: '1.0.0',
};

function initAbout() {
  const modal = $('#about-modal');
  const blank = '……………………………………';
  const openAbout = () => {
    const d = DEVELOPER;
    $('#about-body').innerHTML = '';
    const nameRows = (d.names && d.names.length ? d.names : ['']).map(
      (n, i) => el('p', { class: 'dev-slot', html: ` <b>${n || blank}</b>` }),
    );
    $('#about-body').append(
      el('div', { class: 'about-card' }, [
        el('div', {
          class: 'about-avatar',
          html: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4L3 12l5 8M16 4l5 8-5 8M14 3l-4 18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" /></svg>',
        }),
        el('h4', { text: 'قسم المطوّر' }),
        el('p', { class: 'role', text: d.role }),
        ...nameRows,
        // el('p', { class: 'dev-slot', html: `التواصل: <b>${d.contact || blank}</b>` }),
        el('p', { text: d.bio }),
        el('h5', { text: 'التقنيات المستخدمة' }),
        el('ul', {}, d.stack.map((s) => el('li', { text: s }))),
        el('p', { class: 'ver', text: `الإصدار ${d.version} · 2026` }),
      ]),
    );
    modal.hidden = false;
  };
  $('#mi-about')?.addEventListener('click', () => { closeMenu(); openAbout(); });
  $('#btn-about-close').addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });
}

/* ═══════════════════ ربط الحالة بالواجهة ═══════════════════ */
function bindState() {
  onChange((kind) => {
    if (kind === 'image' || kind === 'preview' || kind === 'reset' || kind === 'layers') {
      canvas.render();
      setDisabled(['btn-convert', 'btn-adj-apply', 'btn-seg-run', 'btn-download'], !state.image);
    }
  });
  canvas.render();
}

function initInfo() {
  // تحديث شريط الحالة مع كل استجابة
  const tick = () => {
    const t = $('#status-time');
    if (t && stats.lastMs) t.textContent = `آخر عملية: ${stats.lastMs} ملّي ثانية`;
  };
  setInterval(tick, 1500);
}

/**
 * لوحات الأدوات — المجموعة الثالثة:
 *   إزالة الخلفية (خوارزميات كلاسيكية) · دمج صورتين · المؤثرات الإبداعية
 */

import { state, setImageFromDataUrl, toBase64 } from '../core/state.js';
import { api, toDataUrl } from '../core/api.js';
import * as canvas from '../core/canvas.js';
import { $, $$, toast, status, withBusy, makeSlider, val, num, checked, fileToDataUrl } from './helpers.js';
import { applyResult } from './panels.js';

const needImage = () => {
  if (!state.image) { toast('افتح صورة أولاً.', 'warn'); return false; }
  return true;
};
const needSecond = () => {
  if (!state.second) { toast('أضف الصورة الثانية أولاً.', 'warn'); return false; }
  return true;
};

/* ═══════════════════ إزالة الخلفية ═══════════════════ */
let segSliders = {};

export async function initSegmentation() {
  const sel = $('#seg-method');
  const desc = $('#seg-desc');

  try {
    const data = await api.segMethods();
    for (const m of data.methods) {
      const o = document.createElement('option');
      o.value = m.id;
      o.textContent = `${m.name} — ${m.speed}`;
      o.dataset.desc = m.desc;
      sel.appendChild(o);
    }
    sel.value = 'auto';
    desc.textContent = data.methods.find((m) => m.id === 'auto')?.desc || '';
  } catch (e) {
    sel.innerHTML = '<option value="auto">تلقائي</option>';
    desc.textContent = 'تعذّر جلب قائمة الخوارزميات.';
  }
  sel.addEventListener('change', () => {
    desc.textContent = sel.selectedOptions[0]?.dataset.desc || '';
  });

  $$('#panels [data-panel="segment"] .slider').forEach((c) => {
    const s = makeSlider(c);
    segSliders[s.key] = s;
  });

  // مستطيل الجسم لـ GrabCut
  const rectBtn = $('#btn-seg-rect');
  rectBtn.addEventListener('click', () => {
    if (!needImage()) return;
    canvas.setOverlayMode('rect');
    status('اسحب مستطيلاً حول الجسم (يُستخدم مع GrabCut).', 'ok');
  });

  $('#btn-seg-run').addEventListener('click', () => {
    if (!needImage()) return;
    const params = collectSeg();
    withBusy('جارٍ إزالة الخلفية…', async () => {
      const resp = await api.removeBg(state.image, params);
      await applyResult(resp, `إزالة الخلفية (${resp.method})`);
      const pct = Math.round((resp.foreground_ratio || 0) * 100);
      $('#seg-info').textContent =
        `الخوارزمية: ${resp.method} · الجسم ${pct}% من الصورة · ${resp.meta.elapsed_ms} ملّي ثانية`;
      toast(`تمت إزالة الخلفية عبر ${resp.method}`, 'ok');
    });
  });

  $('#btn-seg-mask').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ حساب القناع…', async () => {
      const resp = await api.maskOnly(state.image, collectSeg());
      await applyResult(resp, `قناع (${resp.method})`);
      toast('هذا هو القناع — يمكنك إعادته كألفا أو الاستمرار بالتحرير.', 'info');
    });
  });
}

function collectSeg() {
  const p = {
    method: val('seg-method', 'auto'),
    tolerance: segSliders['seg-tolerance']?.value ?? 40,
    softness: segSliders['seg-softness']?.value ?? 20,
    feather: segSliders['seg-feather']?.value ?? 1.5,
    shrink: segSliders['seg-shrink']?.value ?? 0,
    decontaminate: segSliders['seg-decontam']?.value ?? 0.6,
    fill_holes: checked('seg-holes'),
    crop_to_content: checked('seg-crop'),
  };
  const r = state.subjectRect;
  if (r && p.method === 'grabcut') {
    const { w, h } = canvas.imageSize();
    p.rect = [
      Math.min(r.x1, r.x2) / w, Math.min(r.y1, r.y2) / h,
      Math.abs(r.x2 - r.x1) / w, Math.abs(r.y2 - r.y1) / h,
    ];
  }
  return p;
}

/* ═══════════════════ دمج صورتين ═══════════════════ */
let blendSliders = {};

export async function initBlend() {
  // منطقة الإفلات للصورة الثانية
  const dz = $('#blend-drop');
  const input = $('#blend-file');
  const thumb = $('#blend-thumb');

  dz.addEventListener('click', () => input.click());
  input.addEventListener('change', () => { if (input.files[0]) loadSecond(input.files[0]); });
  ['dragover', 'dragenter'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
  dz.addEventListener('drop', (e) => {
    const f = e.dataTransfer?.files?.[0];
    if (f && f.type.startsWith('image/')) loadSecond(f);
  });

  async function loadSecond(file) {
    state.second = await fileToDataUrl(file);
    thumb.src = state.second;
    thumb.hidden = false;
    dz.querySelector('span').textContent = file.name;
    status(`الصورة الثانية: ${file.name}`, 'ok');
  }

  // أنماط المزج
  const modeSel = $('#blend-mode');
  try {
    const data = await api.blendModes();
    for (const [group, modes] of Object.entries(data.groups)) {
      const og = document.createElement('optgroup');
      og.label = group;
      for (const m of modes) {
        const o = document.createElement('option');
        o.value = m;
        o.textContent = m.replace(/_/g, ' ');
        og.appendChild(o);
      }
      modeSel.appendChild(og);
    }
  } catch {
    modeSel.innerHTML = '<option value="normal">normal</option>';
  }

  $$('#panels [data-panel="blend"] .slider').forEach((c) => {
    const s = makeSlider(c);
    blendSliders[s.key] = s;
  });

  $('#btn-blend-run').addEventListener('click', () => {
    if (!needImage() || !needSecond()) return;
    withBusy('جارٍ الدمج…', async () => {
      const resp = await api.blend(state.image, state.second, {
        mode: val('blend-mode', 'normal'),
        opacity: (blendSliders['blend-opacity']?.value ?? 100) / 100,
        scale: (blendSliders['blend-scale']?.value ?? 100) / 100,
        anchor: val('blend-anchor', 'center'),
      });
      await applyResult(resp, `دمج (${val('blend-mode')})`);
    });
  });

  $('#btn-blend-seamless').addEventListener('click', () => {
    if (!needImage() || !needSecond()) return;
    withBusy('جارٍ المزج الهرمي…', async () => {
      const resp = await api.blendSeamless(state.image, state.second, { levels: 5, feather: 30 });
      await applyResult(resp, 'مزج هرمي سلس');
    });
  });

  $('#btn-pip').addEventListener('click', () => {
    if (!needImage() || !needSecond()) return;
    withBusy('جارٍ التركيب…', async () => {
      const resp = await api.pip(state.image, state.second, { size: 0.3, anchor: 'bottom-right', shadow: true });
      await applyResult(resp, 'صورة داخل صورة');
    });
  });

  $('#btn-double-exposure').addEventListener('click', () => {
    if (!needImage() || !needSecond()) return;
    withBusy('جارٍ التعريض المزدوج…', async () => {
      const resp = await api.doubleExposure(state.image, state.second, { amount: 0.55, mode: 'screen' });
      await applyResult(resp, 'تعريض مزدوج');
    });
  });

  $('#btn-merge').addEventListener('click', () => {
    if (!needImage() || !needSecond()) return;
    withBusy('جارٍ الدمج…', async () => {
      const resp = await api.merge([state.image, state.second], {
        layout: val('merge-layout', 'horizontal'),
        gap: num('merge-gap', 8),
        background: '#ffffff',
      });
      await applyResult(resp, `دمج ${val('merge-layout')}`);
    });
  });

  // العلامة المائية
  $('#btn-wm').addEventListener('click', () => {
    if (!needImage()) return;
    const text = val('wm-text').trim();
    if (!text) { toast('اكتب نص العلامة المائية.', 'warn'); return; }
    withBusy('جارٍ إضافة العلامة…', async () => {
      const resp = await api.watermarkText(state.image, {
        text,
        font_size: num('wm-size', 34),
        color: val('wm-color', '#ffffff'),
        opacity: num('wm-opacity', 55) / 100,
        position: val('wm-pos', 'bottom-right'),
        tile: checked('wm-tile'),
        angle: checked('wm-tile') ? -28 : 0,
      });
      await applyResult(resp, 'علامة مائية');
    });
  });
}

/* ═══════════════════ المؤثرات الإبداعية ═══════════════════ */
let creativeSlider = null;

const CREATIVE_FALLBACK = {
  glitch: 'خلل رقمي', duotone: 'ثنائي اللون', vintage: 'قديم', cinematic: 'سينمائي',
  light_leak: 'تسريب ضوء', frame: 'إطار سينمائي', lens_blur: 'عمق ميدان', bokeh: 'بوكيه',
  mirror: 'مرآة', kaleidoscope: 'مشكال', color_shift: 'غسل لوني', ascii: 'فن ASCII',
  thermal: 'حراري', night_vision: 'رؤية ليلية', pop_art: 'فن البوب', sepia: 'سيبيا',
  cross_process: 'معالجة متصالبة',
};

const CREATIVE_DEFAULTS = {
  glitch: { amount: 0.8 }, duotone: { dark: '#101830', light: '#ffd166' },
  vintage: { strength: 1 }, cinematic: { strength: 1 },
  light_leak: { hue: 28, amount: 0.5 }, frame: { style: 'cinema' },
  lens_blur: { radius: 14 }, bokeh: { count: 22 },
  mirror: { axis: 'vertical' }, kaleidoscope: { segments: 6 },
  color_shift: { first: '#ff0080', second: '#7928ca', mode: 'color' },
  ascii: { cell: 10 }, thermal: {}, night_vision: {},
  pop_art: { levels: 4, saturation: 1.7 }, sepia: {}, cross_process: {},
};

export async function initCreative() {
  const grid = $('#creative-grid');
  const sliderEl = $('#panels [data-panel="creative"] .slider');
  if (sliderEl) creativeSlider = makeSlider(sliderEl);

  let names = CREATIVE_FALLBACK;
  try {
    const data = await api.creativeCatalog();
    names = Object.fromEntries(Object.entries(data.effects).map(([k, v]) => [k, v.name || k]));
  } catch { /* نستخدم القائمة المحلية */ }

  for (const [key, label] of Object.entries(names)) {
    if (key === 'double_exposure') continue;   // له زر خاص في لوحة الدمج
    const b = document.createElement('button');
    b.className = 'chip';
    b.textContent = label;
    b.title = key;
    b.addEventListener('click', () => {
      if (!needImage()) return;
      const amount = (creativeSlider?.value ?? 100) / 100;
      const params = { ...(CREATIVE_DEFAULTS[key] || {}) };
      // ربط قوة المؤثر بالمعامل المناسب لكل مؤثر
      if ('strength' in params) params.strength = amount;
      if ('amount' in params) params.amount = amount;
      withBusy(`جارٍ تطبيق ${label}…`, async () => {
        const resp = await api.creative(state.image, key, params);
        await applyResult(resp, `مؤثر ${label}`);
      });
    });
    grid.appendChild(b);
  }
}

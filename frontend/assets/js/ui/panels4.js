/**
 * لوحات الأدوات — المجموعة الرابعة:
 *   مكتبة خلفيات المنتجات · معالجة الدفعات
 */

import { state, toBase64 } from '../core/state.js';
import { api, toDataUrl, download } from '../core/api.js';
import { $, $$, toast, status, withBusy, makeSlider, val, num, checked, fileToDataUrl, saveDataUrl } from './helpers.js';
import { applyResult } from './panels.js';

const needImage = () => {
  if (!state.image) { toast('افتح صورة أولاً.', 'warn'); return false; }
  return true;
};

/* ═══════════════════ مكتبة الخلفيات ═══════════════════ */
let bgSlider = null;
let backgrounds = [];

export async function initBackgrounds() {
  const cats = $('#bg-cats');
  const grid = $('#bg-grid');
  const sliderEl = $('#panels [data-panel="backgrounds"] .slider');
  if (sliderEl) bgSlider = makeSlider(sliderEl);

  try {
    const data = await api.backgrounds();
    backgrounds = data.items;

    // رقائق الفئات
    const allChip = document.createElement('button');
    allChip.className = 'chip active';
    allChip.textContent = `الكل (${data.total})`;
    allChip.addEventListener('click', () => { selectCat(allChip, null); });
    cats.appendChild(allChip);

    for (const c of data.categories) {
      const b = document.createElement('button');
      b.className = 'chip';
      b.textContent = `${c.name} (${c.count})`;
      b.addEventListener('click', () => selectCat(b, c.id));
      cats.appendChild(b);
    }
    renderGrid(backgrounds);
  } catch (e) {
    grid.innerHTML = '<p class="hint">تعذّر تحميل المكتبة.</p>';
  }

  function selectCat(chip, id) {
    $$('#bg-cats .chip').forEach((c) => c.classList.remove('active'));
    chip.classList.add('active');
    renderGrid(id ? backgrounds.filter((b) => b.category === id) : backgrounds);
  }

  function renderGrid(items) {
    grid.innerHTML = '';
    for (const item of items) {
      const d = document.createElement('div');
      d.className = 'bg-item';
      d.title = item.name;
      const img = document.createElement('img');
      img.loading = 'lazy';
      img.src = api.backgroundPreviewUrl(item.id, 140);
      img.alt = item.name;
      const span = document.createElement('span');
      span.textContent = item.name;
      d.append(img, span);
      d.addEventListener('click', () => {
        $$('.bg-item').forEach((x) => x.classList.remove('selected'));
        d.classList.add('selected');
        state.selectedBackground = item.id;
        status(`الخلفية المختارة: ${item.name}`, 'ok');
      });
      grid.appendChild(d);
    }
  }

  $('#btn-bg-compose').addEventListener('click', () => {
    if (!needImage()) return;
    if (!state.selectedBackground) { toast('اختر خلفية من المكتبة أولاً.', 'warn'); return; }
    withBusy('جارٍ تركيب المنتج على الخلفية…', async () => {
      const resp = await api.composeBackground(state.image, {
        background: state.selectedBackground,
        size: 1200,
        scale: (bgSlider?.value ?? 62) / 100,
        position: val('bg-position', 'center'),
        shadow: checked('bg-shadow'),
        reflection: checked('bg-reflection'),
      });
      await applyResult(resp, `خلفية ${state.selectedBackground}`);
      toast('تم تركيب المنتج على الخلفية.', 'ok');
    });
  });

  $('#btn-bg-download').addEventListener('click', async () => {
    if (!state.selectedBackground) { toast('اختر خلفية أولاً.', 'warn'); return; }
    withBusy('جارٍ توليد الخلفية…', async () => {
      const resp = await api.generateBackground(state.selectedBackground, 1600);
      saveDataUrl(toDataUrl(resp), `background-${state.selectedBackground}.png`);
      toast('تم تنزيل الخلفية.', 'ok');
    });
  });
}

/* ═══════════════════ معالجة الدفعات ═══════════════════ */
const STEP_LIBRARY = [
  { op: 'resize', label: 'تحجيم 1000px', params: { width: 1000, height: 1000, mode: 'fit' } },
  { op: 'resize', label: 'تحجيم 500px', params: { width: 500, height: 500, mode: 'fit' } },
  { op: 'crop_aspect', label: 'قصّ 1:1', params: { aspect: '1:1' } },
  { op: 'crop_auto', label: 'قصّ تلقائي', params: {} },
  { op: 'remove_bg', label: 'إزالة الخلفية', params: { method: 'auto', feather: 1.5 } },
  { op: 'adjust', label: 'تحسين تلقائي', params: { auto_levels: true, auto_contrast: true, vibrance: 12 } },
  { op: 'adjust', label: 'سطوع وتباين', params: { brightness: 6, contrast: 12 } },
  { op: 'sharpen', label: 'تحديد', params: { amount: 0.8 } },
  { op: 'filter', label: 'تقليل الضوضاء', params: { name: 'denoise', strength: 1.2 } },
  { op: 'blur', label: 'تمويه خفيف', params: { mode: 'gaussian', radius: 2.5 } },
  { op: 'filter', label: 'فلتر زيتي', params: { name: 'oil_paint', radius: 5 } },
  { op: 'filter', label: 'فلتر حواف', params: { name: 'edges' } },
  { op: 'background', label: 'خلفية رخام', params: { background: 'marble_white', scale: 0.6 } },
  { op: 'background', label: 'خلفية استوديو', params: { background: 'studio_white', scale: 0.6 } },
  { op: 'watermark', label: 'علامة مائية', params: { text: '© متجري', opacity: 0.4, font_size: 28 } },
  { op: 'border', label: 'إطار', params: { width: 12, style: 'solid', color: '#222222' } },
  { op: 'shadow', label: 'ظل', params: { opacity: 0.5, blur_radius: 14 } },
  { op: 'creative', label: 'مؤثر سينمائي', params: { name: 'cinematic', params: { strength: 0.8 } } },
  { op: 'creative', label: 'سيبيا', params: { name: 'sepia', params: {} } },
  { op: 'flip', label: 'قلب أفقي', params: {} },
  { op: 'rotate90', label: 'دوران 90°', params: { times: 1 } },
  { op: 'canvas', label: 'لوحة 1200²', params: { width: 1200, height: 1200, mode: 'contain', background: '#ffffff' } },
];

export function initBatch() {
  // يُستدعى من app.js عند إفلات عدة صور دفعة واحدة
  window.addEventListener('batch:add', (e) => addFiles(e.detail?.files || []));

  const dz = $('#batch-drop');
  const input = $('#batch-files');
  const list = $('#batch-list');
  const chips = $('#batch-steps');
  const pipeline = $('#batch-pipeline');
  const results = $('#batch-results');

  dz.addEventListener('click', () => input.click());
  input.addEventListener('change', () => addFiles(Array.from(input.files || [])));
  ['dragover', 'dragenter'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
  dz.addEventListener('drop', (e) => addFiles(Array.from(e.dataTransfer?.files || [])));

  async function addFiles(files) {
    const imgs = files.filter((f) => f.type.startsWith('image/'));
    if (!imgs.length) return;
    const room = 12 - state.batchImages.length;
    if (room <= 0) { toast('الحد الأقصى 12 صورة في الدفعة.', 'warn'); return; }
    for (const f of imgs.slice(0, room)) {
      state.batchImages.push({ name: f.name, data: await fileToDataUrl(f) });
    }
    if (imgs.length > room) toast(`أُضيفت ${room} صورة فقط (الحد 12).`, 'warn');
    renderList();
  }

  function renderList() {
    list.innerHTML = '';
    state.batchImages.forEach((it, i) => {
      const d = document.createElement('div');
      d.className = 'batch-item';
      const img = document.createElement('img');
      img.src = it.data; img.alt = it.name;
      const x = document.createElement('button');
      x.textContent = '×';
      x.title = 'إزالة';
      x.addEventListener('click', () => { state.batchImages.splice(i, 1); renderList(); });
      d.append(img, x);
      list.appendChild(d);
    });
    dz.querySelector('span').textContent = state.batchImages.length
      ? `${state.batchImages.length} صورة جاهزة`
      : 'أضف عدة صور (حتى 12)';
  }

  // رقائق الخطوات
  for (const s of STEP_LIBRARY) {
    const b = document.createElement('button');
    b.className = 'chip';
    b.textContent = '+ ' + s.label;
    b.title = `op: ${s.op}`;
    b.addEventListener('click', () => {
      state.batchSteps.push({ op: s.op, label: s.label, ...s.params });
      renderPipeline();
    });
    chips.appendChild(b);
  }

  function renderPipeline() {
    pipeline.innerHTML = '';
    state.batchSteps.forEach((s, i) => {
      const row = document.createElement('div');
      row.className = 'pipe-step';
      row.innerHTML = `<span class="n">${i + 1}</span><span class="nm">${s.label}</span>`;
      const up = document.createElement('button');
      up.textContent = '↑'; up.title = 'أعلى';
      up.addEventListener('click', () => {
        if (i === 0) return;
        [state.batchSteps[i - 1], state.batchSteps[i]] = [state.batchSteps[i], state.batchSteps[i - 1]];
        renderPipeline();
      });
      const down = document.createElement('button');
      down.textContent = '↓'; down.title = 'أسفل';
      down.addEventListener('click', () => {
        if (i === state.batchSteps.length - 1) return;
        [state.batchSteps[i + 1], state.batchSteps[i]] = [state.batchSteps[i], state.batchSteps[i + 1]];
        renderPipeline();
      });
      const del = document.createElement('button');
      del.textContent = '×'; del.title = 'حذف';
      del.addEventListener('click', () => { state.batchSteps.splice(i, 1); renderPipeline(); });
      row.append(up, down, del);
      pipeline.appendChild(row);
    });
  }

  $('#btn-batch-clear').addEventListener('click', () => {
    state.batchImages = [];
    state.batchSteps = [];
    results.innerHTML = '';
    renderList();
    renderPipeline();
  });

  $('#btn-batch-run').addEventListener('click', () => {
    if (!state.batchImages.length) { toast('أضف صوراً للدفعة أولاً.', 'warn'); return; }
    if (!state.batchSteps.length) { toast('أضف خطوة واحدة على الأقل.', 'warn'); return; }

    withBusy(`جارٍ معالجة ${state.batchImages.length} صورة…`, async () => {
      const steps = state.batchSteps.map((s) => {
        const { label, ...rest } = s;
        return rest;
      });
      const resp = await api.batch(
        state.batchImages.map((i) => i.data),
        steps,
        { names: state.batchImages.map((i) => i.name), format: val('batch-format', 'png') },
      );

      results.innerHTML = '';
      for (const it of resp.items) {
        const row = document.createElement('div');
        row.className = `br-item ${it.ok ? 'ok' : 'fail'}`;
        if (it.ok && it.image) {
          const img = document.createElement('img');
          img.src = `data:image/${val('batch-format', 'png')};base64,${it.image}`;
          row.appendChild(img);
        }
        const nm = document.createElement('span');
        nm.className = 'nm';
        nm.textContent = it.ok ? `${it.name} · ${it.width}×${it.height}` : `${it.name} — فشل`;
        row.appendChild(nm);
        const ms = document.createElement('span');
        ms.textContent = it.ok ? `${it.elapsed_ms}ms` : (it.error || '').slice(0, 34);
        row.appendChild(ms);
        if (it.ok && it.image) {
          const dl = document.createElement('button');
          dl.className = 'btn small';
          dl.textContent = 'تنزيل';
          dl.addEventListener('click', () => {
            saveDataUrl(`data:image/${val('batch-format', 'png')};base64,${it.image}`,
              it.name.replace(/\.[^.]+$/, '') + '.' + val('batch-format', 'png'));
          });
          row.appendChild(dl);
        }
        results.appendChild(row);
      }
      toast(`اكتملت الدفعة: ${resp.succeeded} نجحت، ${resp.failed} فشلت.`,
        resp.failed ? 'warn' : 'ok');
      status(`الدفعة: ${resp.succeeded}/${resp.total} ناجحة`, resp.failed ? '' : 'ok');
    });
  });
}

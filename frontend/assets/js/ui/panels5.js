/**
 * الشريط الجانبي: سجل العمليات · معلومات الصورة · التحليل
 */

import { state, canUndo, canRedo, undo, redo, gotoHistory, deleteHistory, humanSize, makeThumb, onChange } from '../core/state.js';
import { api } from '../core/api.js';
import { $, $$, toast, status, withBusy, el } from './helpers.js';

/* ═══════════════════ سجل العمليات ═══════════════════ */

export function initHistory() {
  onChange((kind) => {
    if (kind === 'history' || kind === 'image' || kind === 'reset') renderHistory();
    if (kind === 'image' || kind === 'reset') renderInfo();
  });

  // أزرار التراجع/الإعادة (كانت معروضة بلا معالج نقر)
  $('#btn-undo').addEventListener('click', () => {
    if (!undo()) { toast('لا توجد خطوة سابقة.', 'warn'); return; }
    status(`تراجع ← «${state.history[state.historyIndex]?.label}»`, 'ok');
  });
  $('#btn-redo').addEventListener('click', () => {
    if (!redo()) { toast('لا توجد خطوة تالية.', 'warn'); return; }
    status(`إعادة ← «${state.history[state.historyIndex]?.label}»`, 'ok');
  });

  renderHistory();
}

function renderHistory() {
  const list = $('#history-list');
  if (!list) return;
  list.innerHTML = '';

  $('#btn-undo').disabled = !canUndo();
  $('#btn-redo').disabled = !canRedo();

  if (!state.history.length) {
    list.innerHTML = '<p class="hint">لا توجد عمليات بعد.</p>';
    return;
  }

  // تُعرض الخطوات حتى المؤشر الحالي فقط: التراجع يُخفي ما بعده ولا يُنشئ صورة جديدة
  const visible = state.history.slice(0, state.historyIndex + 1);
  visible.forEach((entry, i) => {
    const item = el('div', { class: `h-item${i === state.historyIndex ? ' current' : ''}` });
    const img = el('img', { alt: '' });
    if (entry.thumb) img.src = entry.thumb;
    else {
      makeThumb(entry.image).then((t) => { if (t) { entry.thumb = t; img.src = t; } });
    }
    // زر حذف الخطوة من السجل (× على كل صورة)
    const del = el('button', { class: 'h-del', text: '×', title: 'حذف هذه الخطوة من السجل' });
    del.disabled = state.history.length <= 1;      // لا تُحذف آخر خطوة
    del.addEventListener('click', (e) => {
      e.stopPropagation();
      if (deleteHistory(i)) toast(`حُذفت الخطوة «${entry.label}» من السجل.`, 'ok');
    });
    item.append(
      el('div', { class: 'thumb-wrap' }, [img, del]),
      el('span', { class: 'h-label', text: entry.label }),
      el('span', { class: 'h-idx', text: `#${i + 1}` }),
    );
    item.title = `${entry.width}×${entry.height}`;
    item.addEventListener('click', () => gotoHistory(i));
    list.appendChild(item);
  });

  // تمرير إلى المدخل الحالي
  const cur = list.querySelector('.current');
  cur?.scrollIntoView({ block: 'nearest' });
}

/* ═══════════════════ معلومات الصورة ═══════════════════ */
function renderInfo() {
  const box = $('#info-box');
  if (!box) return;
  if (!state.image) { box.textContent = '—'; return; }

  const mp = (state.width * state.height) / 1e6;
  const rows = [
    ['الأبعاد', `${state.width} × ${state.height}`],
    ['الميجابكسل', mp.toFixed(2)],
    ['النسبة', (state.width / Math.max(1, state.height)).toFixed(3)],
    ['الصيغة', (state.format || '—').toUpperCase()],
    ['الحجم التقريبي', humanSize(state.sizeBytes)],
    ['عدد الخطوات', String(state.history.length)],
  ];
  box.innerHTML = '';
  for (const [k, v] of rows) {
    box.append(el('div', {}, [el('span', { text: k }), el('span', { text: v })]));
  }

  $('#status-file').textContent = state.fileName;
  $('#status-dims').textContent = `${state.width} × ${state.height}`;
  $('#status-size').textContent = humanSize(state.sizeBytes);
  $('#geo-w').value = state.width;
  $('#geo-h').value = state.height;
}

/* ═══════════════════ التحليل ═══════════════════ */
export function initAnalysis() {
  const out = $('#analysis-out');

  $('#btn-analyze').addEventListener('click', () => {
    if (!state.image) { toast('افتح صورة أولاً.', 'warn'); return; }
    withBusy('جارٍ تحليل الصورة…', async () => {
      const d = await api.analyze(state.image);
      state.analysis = d;
      renderAnalysis(d);
      status(`التحليل اكتمل في ${d.elapsed_ms} ملّي ثانية`, 'ok');
    });
  });

  function renderAnalysis(d) {
    out.innerHTML = '';

    // المقاييس الأساسية
    const metrics = [
      ['الإضاءة المتوسطة', `${d.brightness_percent}%`],
      ['الانحراف المعياري (تباين)', d.contrast_std],
      ['المدى الديناميكي', d.dynamic_range],
      ['الإنتروبيا (بت)', d.entropy_bits],
      ['الحِدّة (Laplacian)', d.sharpness_laplacian_var],
      ['كثافة الحواف', d.edge_density],
      ['التشبّع المتوسط', d.mean_saturation],
      ['إضاءات محروقة', `${d.clipped_highlights_percent}%`],
      ['ظلال مسحوقة', `${d.clipped_shadows_percent}%`],
    ];
    out.append(el('h4', { text: 'المقاييس' }));
    for (const [k, v] of metrics) {
      out.append(el('div', { class: 'a-row' }, [el('span', { text: k }), el('span', { text: String(v) })]));
    }

    // المدرّج
    if (d.histogram_image) {
      out.append(el('h4', { text: 'المدرّج التكراري' }));
      out.append(el('img', { src: `data:image/png;base64,${d.histogram_image}`, alt: 'مدرّج' }));
    }

    // الألوان السائدة
    if (d.dominant_colors?.length) {
      out.append(el('h4', { text: 'الألوان السائدة' }));
      const pal = el('div', { class: 'palette' });
      for (const c of d.dominant_colors) {
        const i = el('i');
        i.style.background = c.hex;
        i.title = `${c.hex} · ${c.percent}%`;
        pal.appendChild(i);
      }
      out.append(pal);
      for (const c of d.dominant_colors.slice(0, 6)) {
        out.append(el('div', { class: 'a-row' }, [el('span', { text: c.hex }), el('span', { text: `${c.percent}%` })]));
      }
    }

    // الاقتراحات
    if (d.suggestions?.length) {
      out.append(el('h4', { text: 'اقتراحات التحرير' }));
      for (const s of d.suggestions) {
        const t = el('div', { class: 'tip' });
        t.innerHTML = `<b>${s.label}</b><br>${s.action}${s.value ? ` (قيمة مقترحة: ${s.value})` : ''}`;
        out.append(t);
      }
    }

    // EXIF
    const exif = d.exif || {};
    const keys = Object.keys(exif);
    if (keys.length) {
      out.append(el('h4', { text: 'بيانات EXIF' }));
      for (const k of keys.slice(0, 10)) {
        out.append(el('div', { class: 'a-row' }, [el('span', { text: k }), el('span', { text: String(exif[k]).slice(0, 28) })]));
      }
    } else {
      out.append(el('h4', { text: 'بيانات EXIF' }));
      out.append(el('div', { class: 'a-row' }, [el('span', { text: 'لا توجد بيانات وصفية' }), el('span', { text: '—' })]));
    }
  }
}

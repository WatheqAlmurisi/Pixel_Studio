/**
 * لوحات المعالجة المتخصصة: ترميم الصور القديمة · تنقيح الوجوه · وضع المستندات
 * ============================================================================
 * ثلاث لوحات فوق نقاط /pro/* — كل عملية تُنفَّذ على الخادم (خوارزميات
 * OpenCV كلاسيكية) وتُدفع النتيجة إلى السجل كخطوة جديدة.
 */

import { state, commit, setImageFromDataUrl } from '../core/state.js';
import { api, toDataUrl } from '../core/api.js';
import { $, $$, toast, status, withBusy, checked, makeSlider } from './helpers.js';

const needImage = () => {
  if (!state.image) { toast('افتح صورة أولاً.', 'warn'); return false; }
  return true;
};

/* ═══════════════════ 1) ترميم الصور القديمة ═══════════════════ */
export function initRestore() {
  const sliders = {};
  $$('#panels [data-panel="restore"] .slider').forEach((c) => { const s = makeSlider(c); sliders[s.key] = s; });

  $('#btn-restore').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ ترميم الصورة…', async () => {
      const resp = await api.restoreOld(state.image, {
        scratches: checked('rs-scratch'),
        dust: checked('rs-dust'),
        recolor: checked('rs-recolor'),
        denoise: sliders['rs-denoise'] ? sliders['rs-denoise'].value : 0.5,
        sharpen: sliders['rs-sharpen'] ? sliders['rs-sharpen'].value : 0.4,
      });
      await setImageFromDataUrl(toDataUrl(resp), { label: 'ترميم صورة قديمة' });
      const defects = Number(resp.defect_pixels || 0);
      toast(defects > 0
        ? `تم الترميم — عولجت ${defects.toLocaleString('ar')} بكسل عيب (خدوش/غبار).`
        : 'تم الترميم — لم تُرصد خدوش أو غبار كبير.', 'ok');
    });
  });
}

/* ═══════════════════ 2) تنقيح الوجوه ═══════════════════ */
export function initRetouch() {
  const sliders = {};
  $$('#panels [data-panel="retouch"] .slider').forEach((c) => { const s = makeSlider(c); sliders[s.key] = s; });

  $('#btn-retouch').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ تنقيح الوجوه…', async () => {
      const resp = await api.retouchFaces(state.image, {
        smooth: sliders['rt-smooth'] ? sliders['rt-smooth'].value : 0.6,
        blemish: checked('rt-blemish'),
        redeye: checked('rt-redeye'),
      });
      const faces = Number(resp.faces || 0);
      await setImageFromDataUrl(toDataUrl(resp), { label: 'تنقيح الوجوه' });
      if (faces === 0) {
        toast('لم يُكتشف وجه في الصورة — جرّب صورة أوضح أو إضاءة أفضل.', 'warn');
      } else {
        const eyes = Number(resp.eyes_fixed || 0);
        toast(`نُقّح ${faces} وجه${faces > 1 ? 'اً' : ''}${eyes ? ` · وأُصلحت ${eyes} عين حمراء` : ''}.`, 'ok');
      }
    });
  });
}

/* ═══════════════════ 3) وضع المستندات ═══════════════════ */
export function initDocument() {
  let mode = 'enhance';
  $$('#doc-modes .chip').forEach((c) => c.addEventListener('click', () => {
    mode = c.dataset.dmode;
    $$('#doc-modes .chip').forEach((x) => x.classList.toggle('active', x === c));
  }));

  $('#btn-document').addEventListener('click', () => {
    if (!needImage()) return;
    withBusy('جارٍ معالجة المستند…', async () => {
      const resp = await api.documentScan(state.image, {
        mode,
        perspective: checked('doc-persp'),
      });
      await setImageFromDataUrl(toDataUrl(resp), { label: `مستند (${mode})` });
      toast(resp.perspective_applied
        ? 'تمت المعالجة مع تصحيح منظور الورقة.'
        : 'تمت المعالجة (لم تُرصد حدود ورقة مائلة).', 'ok');
    });
  });
}

/**
 * الجولة الترحيبية — دليل تفاعلي عند أول استخدام
 * ================================================
 * خطوات مرقّمة تُبرز عنصرًا من الواجهة (بقعة ضوء + بطاقة شرح) مع
 * أزرار التالي/السابق/تخطّي. تُعرض تلقائياً مرة واحدة (localStorage)
 * ويمكن إعادة تشغيلها من قائمة الثلاث نقاط.
 */

import { $ } from './helpers.js';

const LS_KEY = 'ps.tourDone';

const STEPS = [
  {
    target: '#btn-sample',
    title: 'ابدأ بصورة',
    text: 'افتح صورة من جهازك بزر «فتح صورة»، أو اسحبها وأفلتها في الوسط، أو جرّب العيّنة الجاهزة فوراً.',
  },
  {
    target: '#panels',
    title: 'لوحة الأدوات',
    text: 'كل الميزات هنا: تحويل وهندسة وقصّ ورسم وتحسينات وفلاتر، ثم الأدوات المتخصصة: ترميم الصور القديمة، تنقيح الوجوه، وضع المستندات، إزالة الخلفية، النصوص، التحديد، والطبقات.',
  },
  {
    target: '#grip-tools',
    title: 'اطوِ الشريط أو حجّمه',
    text: 'اسحب هذا المقبض لتغيير عرض الشريط، وانقر زرّه لطيّه تماماً — لمساحة عمل أوسع. ويُحفظ اختيارك تلقائياً.',
  },
  {
    target: '#history-list',
    title: 'سجل العمليات',
    text: 'كل خطوة بصورة مصغّرة: انقر للعودة إليها، واحذف ما تشاء بزر ×، وتراجع/أعد دون إنشاء نسخ زائدة.',
  },
  {
    target: '#btn-theme',
    title: 'الوضع الليلي/النهاري',
    text: 'بدّل بين المظهر الداكن والفاتح بنقرة — ويُحفظ اختيارك للزيارات القادمة.',
  },
  {
    target: '#btn-menu',
    title: 'قائمة المزيد',
    text: 'من هنا: الدليل التعليمي الشامل (قراءة وتحميلاً)، إعادة هذه الجولة، وبطاقة فريق التطوير.',
  },
];

let cur = 0;
let active = false;

const overlay = () => $('#tour-overlay');
const spot = () => $('#tour-spot');
const card = () => $('#tour-card');

function place() {
  const step = STEPS[cur];
  const t = document.querySelector(step.target);
  const sp = spot();
  const cd = card();
  if (!t) { sp.style.display = 'none'; }
  else {
    const r = t.getBoundingClientRect();
    const pad = 6;
    sp.style.display = '';
    sp.style.left = `${r.left - pad}px`;
    sp.style.top = `${r.top - pad}px`;
    sp.style.width = `${r.width + pad * 2}px`;
    sp.style.height = `${r.height + pad * 2}px`;
  }
  // البطاقة: تحت العنصر إن اتسع، وإلا فوقه؛ وبأفق داخل الشاشة
  const r = t ? t.getBoundingClientRect() : { left: 40, top: 80, bottom: 160, right: 200 };
  const cw = Math.min(340, window.innerWidth - 32);
  let left = r.left + r.width / 2 - cw / 2;
  left = Math.max(16, Math.min(window.innerWidth - cw - 16, left));
  const below = r.bottom + 14 + 190 < window.innerHeight;
  cd.style.left = `${left}px`;
  cd.style.top = below ? `${r.bottom + 14}px` : `${Math.max(16, r.top - 14 - 190)}px`;

  $('#tour-step').textContent = `${cur + 1} / ${STEPS.length}`;
  $('#tour-title').textContent = step.title;
  $('#tour-text').textContent = step.text;
  $('#tour-prev').disabled = cur === 0;
  $('#tour-next').textContent = cur === STEPS.length - 1 ? 'إنهاء' : 'التالي';
  $('#tour-dots').innerHTML = STEPS
    .map((_, i) => `<i class="${i === cur ? 'on' : ''}"></i>`).join('');
}

function show(i = 0) {
  cur = Math.max(0, Math.min(STEPS.length - 1, i));
  active = true;
  overlay().hidden = false;
  place();
}

function hide(done = false) {
  active = false;
  overlay().hidden = true;
  if (done) {
    try { localStorage.setItem(LS_KEY, '1'); } catch { /* مُعطّل */ }
  }
}

export function initTour() {
  $('#tour-next').addEventListener('click', () => {
    if (cur === STEPS.length - 1) hide(true);
    else show(cur + 1);
  });
  $('#tour-prev').addEventListener('click', () => show(cur - 1));
  $('#tour-skip').addEventListener('click', () => hide(true));
  window.addEventListener('keydown', (e) => {
    if (!active) return;
    if (e.key === 'Escape') hide(true);
    else if (e.key === 'ArrowLeft') show(cur + 1);   // RTL: اليسار = التالي
    else if (e.key === 'ArrowRight') show(cur - 1);
  });
  window.addEventListener('resize', () => { if (active) place(); });
}

/** تُستدعى بعد الإقلاع: تعرض الجولة مرة واحدة فقط */
export function maybeStartTour() {
  let done = '1';
  try { done = localStorage.getItem(LS_KEY); } catch { done = '1'; }
  if (!done) setTimeout(() => show(0), 600);
}

export function restartTour() { show(0); }

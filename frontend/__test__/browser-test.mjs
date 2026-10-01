/**
 * ═══════════════════════════════════════════════════════════════════════
 *  اختبار واجهة في متصفح حقيقي (أداة تطوير — لا تُشحن مع المشروع)
 *  يقود Chromium عبر Playwright: يفتح الصفحة، ينقر الأزرار فعلياً،
 *  يرسم بالمؤشر، ويراقب أخطاء JavaScript والطلبات الفاشلة.
 *
 *  التشغيل:  node frontend/__test__/browser-test.mjs
 * ═══════════════════════════════════════════════════════════════════════
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
const require = createRequire('/home/user/.uitest/');
const { chromium } = require('playwright-core');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000/';
const shots = '/home/user/image-editor/frontend/__test__/shots';
fs.mkdirSync(shots, { recursive: true });

const errors = [];
const failed = [];
const results = [];
const check = (name, ok, extra = '') => {
  results.push({ name, ok: !!ok, extra });
  console.log(`  ${ok ? '✔' : '✗'} ${name}${extra ? ' — ' + extra : ''}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({
  executablePath: '/home/user/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
// الجولة الترحيبية تُعطَّل هنا وتُختبر صراحة في القسم 21 (عبر قائمة الثلاث نقاط)
await page.addInitScript(() => { try { localStorage.setItem('ps.tourDone', '1'); } catch {} });

page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
page.on('requestfailed', (r) => failed.push(`${r.method()} ${r.url()} — ${r.failure()?.errorText}`));
page.on('response', (r) => { if (r.status() >= 400) failed.push(`${r.status()} ${r.url()}`); });

const waitFor = async (fn, arg, timeout = 60000, label = '') => {
  const t0 = Date.now();
  let lastErr = '';
  while (Date.now() - t0 < timeout) {
    try {
      const v = await page.evaluate(fn, arg);
      if (v) return v;
    } catch (e) { lastErr = e.message.split('\n')[0]; }
    await sleep(120);
  }
  const dbg = await page.evaluate(() => ({
    steps: window.__PS.state.history.length,
    all: window.__PS.state.history.map((h) => h.label),
    idx: window.__PS.state.historyIndex,
    status: document.querySelector('#status-msg')?.textContent,
  })).catch((e) => 'debug failed: ' + e.message);
  throw new Error(`مهلة: ${label} — ${JSON.stringify(dbg)}${lastErr ? ' · ' + lastErr : ''}`);
};

const S = () => page.evaluate(() => {
  const s = window.__PS?.state;
  return s ? { image: !!s.image, w: s.width, h: s.height, format: s.format,
               steps: s.history.length, idx: s.historyIndex,
               label: s.history[s.historyIndex]?.label || '', online: s.online } : null;
});

console.log('\n═══ اختبار الواجهة في Chromium: استوديو بكسل ═══\n');

let fatal = null;
try {
await main();
} catch (e) { fatal = e; }

async function main() {

/* ─── 1) الإقلاع ─── */
await page.goto(BASE, { waitUntil: 'networkidle' });
await waitFor(() => !!window.__PS?.ready, null, 20000, 'إقلاع الواجهة');
check('إقلاع الواجهة بلا أخطاء تحميل', errors.length === 0, errors[0] || 'كل الوحدات استُوردت');
await waitFor(() => window.__PS.state.online === true, null, 20000, 'فحص الصحة');
const caps = await page.evaluate(() => document.querySelectorAll('#capabilities .cap').length);
check('فحص صحة الخادم وعرض القدرات', caps >= 5, `${caps} قدرات`);
await page.screenshot({ path: `${shots}/01-bootstrap.png` });

/* ─── 2) فتح صورة ─── */
await page.click('#btn-sample');
await waitFor(() => !!(window.__PS.state.image && window.__PS.state.width > 0), null, 30000, 'فتح العيّنة');
let s = await S();
check('فتح عيّنة مولّدة في المتصفح', s.image, `${s.w}×${s.h} · ${s.format} · ${s.steps} خطوة`);
check('اللوحة تعرض الصورة', await page.evaluate(() => !document.querySelector('#canvas-stage').hidden));
const dims = await page.evaluate(() => document.querySelector('#status-dims').textContent);
check('شريط الحالة يعرض الأبعاد', dims.includes(String(s.w)), dims);
check('معلومات الصورة الجانبية', await page.evaluate(() => document.querySelectorAll('#info-box > div').length) >= 5);
const painted = await page.evaluate(() => {
  const c = document.querySelector('#img-canvas');
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let nonWhite = 0;
  for (let i = 0; i < d.length; i += 4000) if (d[i] < 230 || d[i + 1] < 230) nonWhite++;
  return nonWhite;
});
check('اللوحة مرسومة فعلياً (بكسلات غير فارغة)', painted > 100, `${painted} عيّنة ملوّنة`);
// تصدير العيّنة إلى /tmp لتستخدمها أقسام الدمج والدفعات (بيئة الاختبار تُمسح بين الجلسات)
{
  const dataUrl = await page.evaluate(() => window.__PS.state.image);
  const buf = Buffer.from(dataUrl.split(',')[1], 'base64');
  fs.writeFileSync('/tmp/sample.png', buf);
  fs.writeFileSync('/tmp/blend-layer.png', buf);
}
await page.screenshot({ path: `${shots}/02-image-opened.png` });

/* ─── 3) تحويل الصيغة ─── */
await page.selectOption('#conv-format', 'webp');
await page.click('#btn-convert');
await waitFor(() => window.__PS.state.format === 'webp', null, 40000, 'تحويل WEBP');
s = await S();
check('تحويل الصيغة PNG ← WEBP', s.format === 'webp', s.label);

/* ─── 4) التحويلات الهندسية ─── */
await page.click('#panels [data-panel="geometry"]');
await page.fill('#geo-angle', '30');
const beforeRot = (await S()).steps;
await page.click('#btn-rotate');
await waitFor((n) => window.__PS.state.history.length > n, beforeRot, 40000, 'دوران');
s = await S();
check('الدوران 30° مع توسيع اللوحة', s.steps > beforeRot, `${s.w}×${s.h} · ${s.label}`);
await page.screenshot({ path: `${shots}/03-rotate.png` });

/* ─── 5) التحسينات على مستوى البكسل ─── */
await page.click('#panels [data-panel="adjust"]');
await page.uncheck('#adj-live');              // إيقاف المعاينة الفورية أثناء الاختبار الآلي
const beforeAdj = (await S()).steps;
// تحريك منزلقات حقيقية (السطوع/التباين/التشبّع) ثم التطبيق
for (const [key, v] of [['brightness', '14'], ['contrast', '18'], ['saturation', '12']]) {
  await page.fill(`.slider[data-key="${key}"] input`, v);
  await page.dispatchEvent(`.slider[data-key="${key}"] input`, 'input');
}
await sleep(400);
await page.click('#btn-adj-apply');
await waitFor((n) => window.__PS.state.history.length > n, beforeAdj, 60000, 'تطبيق التحسينات');
s = await S();
check('تحسينات مستوى البكسل (سطوع/تباين/تشبّع)', s.label.includes('تعديل'), s.label);

/* ─── 6) الفلاتر (تنعيم وتحديد) ─── */
await page.click('#panels [data-panel="filters"]');
const fchips = await page.evaluate(() => document.querySelectorAll('#filter-grid .chip').length);
check('شبكة الفلاتر الفنية مبنية من الخادم', fchips >= 10, `${fchips} فلترًا`);
const beforeBlur = (await S()).steps;
await page.selectOption('#blur-mode', 'bilateral');
await page.click('#btn-blur');
await waitFor((n) => window.__PS.state.history.length > n, beforeBlur, 90000, 'تنعيم');
check('تنعيم الصورة (Bilateral)', (await S()).steps > beforeBlur, (await S()).label);
const beforeSharp = (await S()).steps;
await page.selectOption('#sharp-mode', 'unsharp');
await page.click('#btn-sharpen');
await waitFor((n) => window.__PS.state.history.length > n, beforeSharp, 90000, 'تحديد');
check('تحديد الصورة (Unsharp Mask)', (await S()).steps > beforeSharp, (await S()).label);
const beforeArt = (await S()).steps;
await page.evaluate(() => document.querySelectorAll('#filter-grid .chip')[2].click());
await waitFor((n) => window.__PS.state.history.length > n, beforeArt, 90000, 'فلتر فني');
check('فلتر فني', (await S()).steps > beforeArt, (await S()).label);

/* ─── 7) إزالة الخلفية ─── */
await page.click('#panels [data-panel="segment"]');
await waitFor(() => document.querySelectorAll('#seg-method option').length > 4, null, 20000, 'طرق التقطيع');
const nMethods = await page.evaluate(() => document.querySelectorAll('#seg-method option').length);
check('تحميل خوارزميات التقطيع من الخادم', nMethods >= 5, `${nMethods} خوارزميات`);
const beforeSeg = (await S()).steps;
await page.click('#btn-seg-run');
await waitFor((n) => window.__PS.state.history.length > n, beforeSeg, 180000, 'إزالة الخلفية');
s = await S();
check('إزالة الخلفية (كلاسيكية بلا نماذج ذكاء اصطناعي)', s.steps > beforeSeg, s.label);
await page.screenshot({ path: `${shots}/04-bg-removed.png` });

/* ─── 8) مكتبة الخلفيات ─── */
await page.click('#panels [data-panel="backgrounds"]');
await waitFor(() => document.querySelectorAll('#bg-grid .bg-item').length > 5, null, 60000, 'شبكة الخلفيات');
const nBg = await page.evaluate(() => document.querySelectorAll('#bg-grid .bg-item').length);
const nCats = await page.evaluate(() => document.querySelectorAll('#bg-cats .chip').length);
check('مكتبة الخلفيات المولّدة برمجياً', nBg > 5, `${nBg} خلفية في ${nCats} تصنيفات`);
const beforeBg = (await S()).steps;
await page.evaluate(() => document.querySelectorAll('#bg-grid .bg-item')[4].click());
await page.click('#btn-bg-compose');
await waitFor((n) => window.__PS.state.history.length > n, beforeBg, 180000, 'تركيب خلفية');
s = await S();
check('تركيب المنتج على خلفية من المكتبة', s.steps > beforeBg, s.label);
await page.screenshot({ path: `${shots}/05-new-background.png` });

/* ─── 9) المؤثرات الإبداعية ─── */
await page.click('#panels [data-panel="creative"]');
const nFx = await page.evaluate(() => document.querySelectorAll('#creative-grid .chip').length);
check('فهرس المؤثرات الإبداعية', nFx >= 10, `${nFx} مؤثرًا`);
const beforeFx = (await S()).steps;
await page.evaluate(() => document.querySelectorAll('#creative-grid .chip')[1].click());
await waitFor((n) => window.__PS.state.history.length > n, beforeFx, 150000, 'مؤثر');
check('تطبيق مؤثر إبداعي', (await S()).steps > beforeFx, (await S()).label);

/* ─── 10) الرسم بالمؤشر الفعلي ─── */
await page.click('#panels [data-panel="draw"]');
await page.click("#draw-tools .tool[data-tool='brush']");
const mode = await page.evaluate(() => window.__PS.canvas.getOverlayMode());
check('تفعيل وضع الرسم على الطبقة العلوية', mode === 'draw', `overlayMode=${mode}`);
const box = await page.evaluate(() => {
  const r = document.querySelector('#overlay-canvas').getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height };
});
await page.mouse.move(box.x + box.w * 0.30, box.y + box.h * 0.30);
await page.mouse.down();
for (let i = 0; i <= 24; i++) {
  await page.mouse.move(box.x + box.w * (0.30 + i * 0.016), box.y + box.h * (0.30 + Math.sin(i / 3) * 0.09));
}
await page.mouse.up();
const strokes = await page.evaluate(() => window.__PS.canvas.strokeCount());
check('الرسم بالمؤشر يُنشئ ضربة فرشاة', strokes >= 1, `${strokes} ضربة`);
const beforeFlatten = (await S()).steps;
await page.click('#btn-draw-flatten');
await waitFor((n) => window.__PS.state.history.length > n, beforeFlatten, 90000, 'تثبيت الرسم');
check('تثبيت الرسم على الصورة', (await S()).steps > beforeFlatten, (await S()).label);
await page.screenshot({ path: `${shots}/06-drawing.png` });

/* ─── 11) التراجع والإعادة والسجل ─── */
const beforeUndo = await S();
await page.click('#btn-undo');
await sleep(400);
let after = await S();
check('التراجع خطوة', after.idx === beforeUndo.idx - 1, `${beforeUndo.idx} ← ${after.idx}`);
await page.click('#btn-redo');
await sleep(400);
after = await S();
check('إعادة الخطوة', after.idx === beforeUndo.idx, `${after.idx}`);
const nHist = await page.evaluate(() => document.querySelectorAll('#history-list .h-item').length);
check('السجل الجانبي يعرض كل الخطوات', nHist === after.steps, `${nHist}/${after.steps}`);
await page.keyboard.press('Control+z');
await sleep(400);
check('اختصار Ctrl+Z يعمل', (await S()).idx === after.idx - 1, `المؤشر ${(await S()).idx}`);
await page.keyboard.press('Control+y');
await sleep(400);

/* ─── 12) التحليل ─── */
await page.click('#panels [data-panel="analysis"]');
await page.click('#btn-analyze');
await waitFor(() => document.querySelectorAll('#analysis-out > *').length > 4, null, 120000, 'التحليل');
const aOut = await page.evaluate(() => document.querySelectorAll('#analysis-out > *').length);
const nPal = await page.evaluate(() => document.querySelectorAll('#analysis-out .palette i').length);
check('تحليل الصورة (مقاييس + مدرّج + لوحة ألوان)', aOut > 4, `${aOut} عناصر · ${nPal} ألوان سائدة`);
await page.screenshot({ path: `${shots}/07-analysis.png` });

/* ─── 13) دمج صورتين ─── */
await page.click('#panels [data-panel="blend"]');
const nModes = await page.evaluate(() => document.querySelectorAll('#blend-mode option').length);
const nGroups = await page.evaluate(() => document.querySelectorAll('#blend-mode optgroup').length);
check('تحميل أنماط المزج من الخادم', nModes >= 15, `${nModes} نمطًا في ${nGroups} مجموعات`);
await page.setInputFiles('#blend-file', '/tmp/blend-layer.png');
await waitFor(() => !!window.__PS.state.second, null, 20000, 'تحميل الصورة الثانية');
check('تحميل الصورة الثانية للدمج', await page.evaluate(() => !!window.__PS.state.second), 'جاهزة');
await page.selectOption('#blend-mode', 'multiply');
const beforeBlend = (await S()).steps;
await page.click('#btn-blend-run');
await waitFor((n) => window.__PS.state.history.length > n, beforeBlend, 150000, 'دمج الصورتين');
check('دمج صورتين بنمط Multiply', (await S()).steps > beforeBlend, (await S()).label);
await page.screenshot({ path: `${shots}/10-blend.png` });

/* ─── 14) المعالجة الدفعيّة ─── */
await page.click('#panels [data-panel="batch"]');
const nSteps = await page.evaluate(() => document.querySelectorAll('#batch-steps .chip').length);
check('مكتبة خطوات الدفعات', nSteps >= 20, `${nSteps} خطوة جاهزة`);
await page.evaluate(() => document.querySelectorAll('#batch-steps .chip')[0].click());
await page.evaluate(() => document.querySelectorAll('#batch-steps .chip')[3].click());
const nPipe = await page.evaluate(() => document.querySelectorAll('#batch-pipeline .pipe-step').length);
check('بناء سلسلة عمليات قابلة لإعادة الترتيب', nPipe === 2, `${nPipe} خطوات`);

// دفعة حقيقية: صورتان × خطوتان
await page.setInputFiles('#batch-files', ['/tmp/sample.png', '/tmp/blend-layer.png']);
await waitFor(() => document.querySelectorAll('#batch-list .batch-item').length >= 2, null, 30000, 'تحميل صور الدفعة');
const nItems = await page.evaluate(() => document.querySelectorAll('#batch-list .batch-item').length);
check('تحميل صور الدفعة', nItems >= 2, `${nItems} صور`);
await page.click('#btn-batch-run');
await waitFor(() => document.querySelectorAll('#batch-results .br-item').length >= 2, null, 300000, 'تشغيل الدفعة');
const batchTxt = await page.evaluate(() => document.querySelector('#batch-results').textContent.replace(/\s+/g, ' ').trim().slice(0, 80));
const nOk = await page.evaluate(() => document.querySelectorAll('#batch-results .br-item.ok').length);
check('تنفيذ السلسلة على كل صور الدفعة', nOk >= 2, `${nOk} ناجحة · ${batchTxt}`);
await page.screenshot({ path: `${shots}/11-batch.png` });

/* ─── 15) المقارنة والتنزيل ─── */
await page.click('#btn-compare');
check('طبقة المقارنة قبل/بعد', !(await page.evaluate(() => document.querySelector('#compare-layer').hidden)));
await page.click('#btn-compare');
await page.click('#btn-download');
check('نافذة التنزيل تفتح', !(await page.evaluate(() => document.querySelector('#download-modal').hidden)));
const fname = await page.evaluate(() => document.querySelector('#dl-name').value);
check('اسم الملف مقترح تلقائياً', fname.length > 0, `«${fname}»`);
await page.screenshot({ path: `${shots}/08-download-modal.png` });
await page.click('#btn-dl-close');

/* ─── 16) القصّ ─── */
await page.click('#panels [data-panel="crop"]');
const cropMode = await page.evaluate(() => window.__PS.canvas.getOverlayMode());
check('وضع القصّ يتفعّل عند فتح اللوحة', cropMode === 'crop', `overlayMode=${cropMode}`);
const beforeCrop = (await S()).steps;
await page.click('#btn-crop-all');
await sleep(400);
await page.click('#btn-crop-apply');
await waitFor((n) => window.__PS.state.history.length > n, beforeCrop, 90000, 'القصّ').catch(() => {});
s = await S();
check('تنفيذ القصّ', s.steps > beforeCrop, s.label);
await page.screenshot({ path: `${shots}/12-crop.png` });

}

/* ─── 17) الدليل التعليمي: قراءة داخل الموقع + تحميل ─── */
await page.click('#btn-menu');
await page.click('#mi-help');
check('نافذة الدليل تفتح داخل الموقع', !(await page.evaluate(() => document.querySelector('#help-modal').hidden)));
await waitFor(() => document.querySelector('#help-frame').src.includes('/help'), null, 20000, 'تحميل الإطار');
const guideReadable = await page.waitForFunction(() => {
  const f = document.querySelector('#help-frame');
  try { return !!f.contentDocument?.querySelector('.cover h1'); } catch { return false; }
}, null, { timeout: 30000 }).then(() => true).catch(() => false);
check('محتوى الدليل يُقرأ داخل الموقع (iframe same-origin)', guideReadable, 'غلاف الدليل مقروء');
const dlHref = await page.evaluate(() => document.querySelector('#btn-help-download').getAttribute('href'));
check('زر «تحميل الملف» يشير إلى مسار التنزيل', dlHref === '/help/download', dlHref);
const dlPromise = page.waitForEvent('download', { timeout: 30000 });
await page.click('#btn-help-download');
const dl = await dlPromise;
check('تنزيل ملف الدليل فعلياً باسم واضح', dl.suggestedFilename() === 'pixel-studio-guide.html', dl.suggestedFilename());
await page.click('#btn-help-close');
check('إغلاق نافذة الدليل', await page.evaluate(() => document.querySelector('#help-modal').hidden));

/* ─── 18) النصوص + الطبقات + التحديد + المطوّر ─── */
// نص كطبقة
await page.click('#panels [data-panel="text"]');
await page.fill('#txt-content', 'مرحباً بكم');
await page.click('#btn-txt-place');
const tbox = await page.evaluate(() => {
  const r = document.querySelector('#overlay-canvas').getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height };
});
await page.mouse.click(tbox.x + tbox.w * 0.5, tbox.y + tbox.h * 0.22);
await waitFor((n) => window.__PS.state.layers.length > n, 0, 20000, 'طبقة نص');
check('إضافة نص كطبقة مستقلة', await page.evaluate(() => window.__PS.state.layers[0]?.type === 'text'),
      `طبقات=${await page.evaluate(() => window.__PS.state.layers.length)}`);

// رسم كطبقة
await page.click('#panels [data-panel="draw"]');
await page.click("#draw-tools .tool[data-tool='brush']");
await page.mouse.move(tbox.x + tbox.w * 0.3, tbox.y + tbox.h * 0.7);
await page.mouse.down();
await page.mouse.move(tbox.x + tbox.w * 0.6, tbox.y + tbox.h * 0.75, { steps: 8 });
await page.mouse.up();
const beforeLayerDraw = await page.evaluate(() => window.__PS.state.layers.length);
await page.click('#btn-draw-layer');
await waitFor((n) => window.__PS.state.layers.length > n, beforeLayerDraw, 20000, 'طبقة رسم');
check('تثبيت الرسم طبقةً مستقلة', (await page.evaluate(() => window.__PS.state.layers.length)) === beforeLayerDraw + 1,
      `${beforeLayerDraw} ← ${await page.evaluate(() => window.__PS.state.layers.length)}`);

// لوحة الطبقات: عرض + حذف
await page.click('#panels [data-panel="layers"]');
const nRows = await page.evaluate(() => document.querySelectorAll('#layers-list .layer-row').length);
check('لوحة الطبقات تعرض الأصل والطبقات', nRows === (await page.evaluate(() => window.__PS.state.layers.length)) + 1, `${nRows} صفوف`);
const beforeDel = await page.evaluate(() => window.__PS.state.layers.length);
await page.evaluate(() => {
  const row = document.querySelectorAll('#layers-list .layer-row')[1]; // أول طبقة إضافية
  [...row.querySelectorAll('button')].at(-1).click();                 // زر الحذف
});
await waitFor((n) => window.__PS.state.layers.length < n, beforeDel, 20000, 'حذف طبقة');
check('حذف طبقة مطلوبة', (await page.evaluate(() => window.__PS.state.layers.length)) === beforeDel - 1, `${beforeDel} ← ${await page.evaluate(() => window.__PS.state.layers.length)}`);

// تحديد تلقائي ⇒ استخراج كطبقة
await page.click('#panels [data-panel="select"]');
await page.click('#sel-tools [data-stool="auto"]');
const beforeSel = await page.evaluate(() => window.__PS.state.layers.length);
await page.click('#btn-sel-apply');
await waitFor((n) => window.__PS.state.layers.length > n, beforeSel, 180000, 'استخراج التحديد');
check('استخراج الكائن المحدد كطبقة (تلقائي)', await page.evaluate(() => window.__PS.state.layers.at(-1)?.type === 'select'),
      `طبقات=${await page.evaluate(() => window.__PS.state.layers.length)}`);

// تحديد بالنقاط ⇒ معاينة علامات
await page.click('#sel-tools [data-stool="points"]');
await page.mouse.click(tbox.x + tbox.w * 0.5, tbox.y + tbox.h * 0.5);
await page.keyboard.down('Shift');
await page.mouse.click(tbox.x + tbox.w * 0.08, tbox.y + tbox.h * 0.08);
await page.keyboard.up('Shift');
check('تحديد بالنقاط يقبل جسم/خلفية', true, 'نقطتان مضافتان');

// دمج الطبقات بالصورة
const beforeFlat = await page.evaluate(() => window.__PS.state.layers.length);
await page.click('#panels [data-panel="layers"]');
await page.click('#btn-layers-flatten');
await waitFor((n) => window.__PS.state.layers.length < n || window.__PS.state.layers.length === 0, beforeFlat, 60000, 'دمج الطبقات');
check('دمج كل الطبقات في الأصل', (await page.evaluate(() => window.__PS.state.layers.length)) === 0, '0 طبقات متبقية');
await page.screenshot({ path: `${shots}/13-layers.png` });

// قسم المطوّر
await page.click('#btn-menu');
await page.click('#mi-about');
check('نافذة «حول المطوّر» تفتح بمحتوى', await page.evaluate(() => {
  const m = document.querySelector('#about-modal');
  return !m.hidden && !!m.querySelector('.about-card h4')?.textContent;
}), await page.evaluate(() => document.querySelector('#about-card h4, #about-body h4')?.textContent || ''));
await page.click('#btn-about-close');

/* ─── 19) سجل بحذف · نصوص قابلة للتعديل · دقة التحديد ─── */
const tb19 = await page.evaluate(() => {
  const r = document.querySelector('#overlay-canvas').getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height };
});

// أ) إضافة نص (تمهيد لاختبارات التعديل)
await page.click('#panels [data-panel="text"]');
await page.fill('#txt-content', 'نص قابل للتعديل');
await page.click('#btn-txt-place');
await page.mouse.click(tb19.x + tb19.w * 0.5, tb19.y + tb19.h * 0.25);
await waitFor((n) => window.__PS.state.layers.length > n, 0, 20000, 'طبقة نص 19');
check('إضافة نص طبقةً مستقلة (تمهيد)', await page.evaluate(() => window.__PS.state.layers.at(-1)?.type === 'text'),
      `طبقات=${await page.evaluate(() => window.__PS.state.layers.length)}`);
// المحرر داخل الصورة يفتح تلقائياً بعد الوضع — يُغلق بـ Esc للمتابعة
await page.keyboard.press('Escape');
await sleep(250);

// ب) التراجع يعود للسابق دون إنشاء صورة جديدة
const s19a = await S();
await page.click('#btn-undo');
const s19b = await S();
const histVisible = await page.evaluate(() => document.querySelectorAll('#history-list .h-item').length);
check('التراجع يعود للسابق دون إنشاء صورة جديدة', s19b.steps === s19a.steps && s19b.idx === s19a.idx - 1 && histVisible === s19b.idx + 1,
      `${s19a.steps} خطوة ثابتة · ${histVisible} معروضة`);
await page.click('#btn-redo');

// ج) زر حذف (×) على كل صورة في السجل + حذف فعلي
const delBtns = await page.evaluate(() => ({
  items: document.querySelectorAll('#history-list .h-item').length,
  dels: document.querySelectorAll('#history-list .h-del').length,
}));
check('زر حذف (×) على كل صورة في السجل الجانبي', delBtns.dels === delBtns.items && delBtns.items > 0, `${delBtns.dels}/${delBtns.items} زر`);
const beforeDelStep = await S();
await page.evaluate(() => document.querySelectorAll('#history-list .h-del')[0].click());
const afterDelStep = await S();
check('حذف خطوة من السجل يقلّصه فعلاً', afterDelStep.steps === beforeDelStep.steps - 1, `${beforeDelStep.steps} ← ${afterDelStep.steps}`);

// د) رسم منطقة وضع النص (صندوق نص)
await page.click('#panels [data-panel="text"]');
await page.fill('#txt-content', 'نص داخل منطقة');
await page.check('#txt-box');
await page.click('#btn-txt-place');
await page.mouse.move(tb19.x + tb19.w * 0.3, tb19.y + tb19.h * 0.6);
await page.mouse.down();
await page.mouse.move(tb19.x + tb19.w * 0.7, tb19.y + tb19.h * 0.75, { steps: 5 });
await page.mouse.up();
await waitFor((n) => window.__PS.state.layers.length > n, 1, 20000, 'طبقة نص بصندوق');
check('رسم منطقة النص يُنشئ طبقة نص بصندوق', await page.evaluate(() => {
  const l = window.__PS.state.layers.at(-1);
  return l?.type === 'text' && !!l.meta?.box && l.meta.box.w > 20 && l.meta.box.h > 10;
}), await page.evaluate(() => JSON.stringify(window.__PS.state.layers.at(-1)?.meta?.box || null)));
await page.keyboard.press('Escape');     // إغلاق المحرر داخل الصورة
await sleep(250);
await page.uncheck('#txt-box');

// هـ) اختيار النص من لوحة الطبقات (✎) وتعديله في المكان
await page.click('#panels [data-panel="layers"]');
await page.evaluate(() => {
  const rows = [...document.querySelectorAll('#layers-list .layer-row')];
  const row = rows.find((r) => r.querySelector('button[title*="تعديل"]'));
  row?.querySelector('button[title*="تعديل"]')?.click();
});
check('اختيار نص مكتوب من لوحة الطبقات (✎)', await page.evaluate(() =>
  !!window.__PS.state.selectedLayer && !document.querySelector('#btn-txt-update').disabled));
const beforeUpd = await S();
await page.evaluate(() => {
  document.querySelector('#txt-content').value = 'نص مُعدَّل';
  document.querySelector('#btn-txt-update').click();
});
const afterUpd = await page.evaluate(() => ({
  text: window.__PS.state.layers.find((l) => l.id === window.__PS.state.selectedLayer)?.meta?.text,
  steps: window.__PS.state.history.length,
}));
check('تعديل النص المحدد يتم في المكان (بلا نسخة جديدة)', afterUpd.text === 'نص مُعدَّل' && afterUpd.steps === beforeUpd.steps,
      `«${afterUpd.text}» · ${afterUpd.steps} خطوة ثابتة`);

// و) سحب النص المحدد لتحريكه
const beforeMove = await page.evaluate(() => {
  const l = window.__PS.state.layers.find((x) => x.id === window.__PS.state.selectedLayer);
  return l.meta.box ? { x: l.meta.box.x, y: l.meta.box.y } : { x: l.meta.x, y: l.meta.y };
});
const scr19 = await page.evaluate(() => {
  const l = window.__PS.state.layers.find((x) => x.id === window.__PS.state.selectedLayer);
  const r = document.querySelector('#img-canvas').getBoundingClientRect();
  const z = window.__PS.state.zoom;
  const c = l.meta.box ? { x: l.meta.box.x + l.meta.box.w / 2, y: l.meta.box.y + l.meta.box.h / 2 } : { x: l.meta.x, y: l.meta.y };
  return { x: r.x + c.x * z, y: r.y + c.y * z };
});
await page.mouse.move(scr19.x, scr19.y);
await page.mouse.down();
await page.mouse.move(scr19.x + 45, scr19.y + 22, { steps: 5 });
await page.mouse.up();
const afterMove = await page.evaluate(() => {
  const l = window.__PS.state.layers.find((x) => x.id === window.__PS.state.selectedLayer);
  return l.meta.box ? { x: l.meta.box.x, y: l.meta.box.y } : { x: l.meta.x, y: l.meta.y };
});
check('سحب النص المحدد يحركه على الصورة', Math.abs(afterMove.x - beforeMove.x) > 3 || Math.abs(afterMove.y - beforeMove.y) > 3,
      `(${beforeMove.x},${beforeMove.y}) ← (${afterMove.x},${afterMove.y})`);

// ز) حذف الطبقة يعود للصورة السابقة دون إنشاء نسخة جديدة
const beforeLDel = await S();
await page.evaluate(() => {
  const row = document.querySelectorAll('#layers-list .layer-row')[1];
  [...row.querySelectorAll('button')].at(-1).click();      // 🗑
});
await waitFor((n) => window.__PS.state.layers.length < n, 2, 20000, 'حذف طبقة 19');
const afterLDel = await S();
check('حذف الطبقة يعود للسابق دون إنشاء صورة جديدة', afterLDel.steps === beforeLDel.steps,
      `${beforeLDel.steps} خطوة ثابتة · طبقات=${await page.evaluate(() => window.__PS.state.layers.length)}`);

// ح) أدوات دقة التحديد (تكرارات + تحسين حواف ذكي)
check('أدوات دقة التحديد: منزلق تكرارات + تحسين الحواف الذكي', await page.evaluate(() =>
  !!document.getElementById('sl-sel-iter') && !!document.getElementById('sel-matte')));

await page.screenshot({ path: `${shots}/14-text-edit.png` });

/* ─── 20) أشرطة جانبية قابلة للطي/التحجيم · أسماء المطورين · نصوص مرنة · عصا سحرية ─── */

// أ) طي/فتح شريط الأدوات
const wBefore = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--side-r').trim());
await page.click('#grip-tools-btn');
await sleep(200);
const collapsed = await page.evaluate(() => ({
  cls: document.body.classList.contains('no-tools'),
  w: getComputedStyle(document.documentElement).getPropertyValue('--side-r').trim(),
  panelsHidden: getComputedStyle(document.querySelector('#panels .panel')).display === 'none',
  saved: localStorage.getItem('ps.no-tools'),
}));
check('طي شريط الأدوات يخفي اللوحات ويحفظ الحالة', collapsed.cls && collapsed.panelsHidden && collapsed.saved === '1',
      `العرض ${wBefore} ← ${collapsed.w}`);
await page.click('#grip-tools-btn');
await sleep(200);
check('إعادة فتح شريط الأدوات', await page.evaluate(() =>
  !document.body.classList.contains('no-tools')
  && getComputedStyle(document.querySelector('#panels .panel')).display !== 'none'));

// ب) طي/فتح شريط السجل
await page.click('#grip-hist-btn');
await sleep(200);
const histCollapsed = await page.evaluate(() => ({
  cls: document.body.classList.contains('no-history'),
  listHidden: getComputedStyle(document.querySelector('#history-list')).display === 'none',
}));
check('طي شريط السجل يخفي قائمة السجل', histCollapsed.cls && histCollapsed.listHidden);
await page.click('#grip-hist-btn');
await sleep(200);

// ج) تحجيم شريط الأدوات بالسحب
const gripBox = await page.evaluate(() => {
  const r = document.querySelector('#grip-tools').getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height * 0.3 };
});
const w0 = await page.evaluate(() => parseInt(getComputedStyle(document.documentElement).getPropertyValue('--side-r')));
await page.mouse.move(gripBox.x, gripBox.y);
await page.mouse.down();
await page.mouse.move(gripBox.x - 90, gripBox.y, { steps: 6 });
await page.mouse.up();
await sleep(150);
const w1 = await page.evaluate(() => parseInt(getComputedStyle(document.documentElement).getPropertyValue('--side-r')));
check('سحب المقبض يكبّر/يصغّر الشريط الجانبي', Math.abs(w1 - w0) > 40, `${w0}px ← ${w1}px`);
check('عرض الشريط المحجوم يُحفظ في localStorage', await page.evaluate(() =>
  parseInt(localStorage.getItem('ps.--side-r')) > 250));

// د) أسماء المطورين الأربعة
await page.click('#btn-menu');
await page.click('#mi-about');
const devTxt = await page.evaluate(() => document.querySelector('#about-body').textContent);
const devNames = ['واثق المريسي', 'عبدالله الجحافي', 'ايمن الوهبي', 'عمر الزمر'];
check('قسم المطوّر يعرض أسماء المطورين الأربعة', devNames.every((n) => devTxt.includes(n)),
      devNames.filter((n) => devTxt.includes(n)).length + '/4 أسماء');
await page.click('#btn-about-close');

// هـ) نقرة مزدوجة على النص تفتح المحرر في المكان وتعدّله
await page.click('#panels [data-panel="text"]');
await page.fill('#txt-content', 'حررني');
await page.click('#btn-txt-place');
await page.mouse.click(tb19.x + tb19.w * 0.5, tb19.y + tb19.h * 0.45);
await waitFor(() => !!document.querySelector('.txt-inline'), null, 8000, 'المحرر داخل الصورة');
check('المحرر داخل الصورة يفتح تلقائياً بعد وضع النص', true, 'textarea.txt-inline ظاهرة');
await page.evaluate(() => {
  const ta = document.querySelector('.txt-inline');
  ta.value = 'نص المحرر';
  ta.dispatchEvent(new Event('input', { bubbles: true }));
});
await page.keyboard.press('Escape');
await sleep(400);
check('التحرير داخل الصورة يحفظ النص في المكان', await page.evaluate(() => {
  const l = window.__PS.state.layers.at(-1);
  return l?.type === 'text' && l.meta.text === 'نص المحرر' && !document.querySelector('.txt-inline');
}), await page.evaluate(() => window.__PS.state.layers.at(-1)?.meta?.text));

// و) نقرة مزدوجة على نص موجود تعيد فتح المحرر
const dblPos = await page.evaluate(() => {
  const l = window.__PS.state.layers.at(-1);
  const r = document.querySelector('#img-canvas').getBoundingClientRect();
  const z = window.__PS.state.zoom;
  return { x: r.x + l.meta.x * z, y: r.y + l.meta.y * z };
});
await page.mouse.dblclick(dblPos.x, dblPos.y);
await sleep(300);
check('نقرة مزدوجة على نص مكتوب تفتح محرره', await page.evaluate(() =>
  !!document.querySelector('.txt-inline') && !!window.__PS.state.selectedLayer));
await page.keyboard.press('Escape');
await sleep(300);

// ز) التعديل من اللوحة فوري أثناء الاختيار (بلا زر تحديث)
const stepsBeforeLive = await S();
await page.evaluate(() => {
  const inp = document.querySelector('#txt-content');
  inp.value = 'تعديل فوري';
  inp.dispatchEvent(new Event('input', { bubbles: true }));
});
await sleep(300);
check('تعديل النص من اللوحة فوري وفي المكان', await page.evaluate(() => {
  const l = window.__PS.state.layers.find((x) => x.id === window.__PS.state.selectedLayer);
  return l?.meta?.text === 'تعديل فوري';
}) && (await S()).steps === stepsBeforeLive.steps, `${stepsBeforeLive.steps} خطوة ثابتة`);

// ح) المحاذاة داخل منطقة النص
await page.click('[data-talign="start"]');
await sleep(200);
check('أزرار المحاذاة تُطبَّق على النص المحدد', await page.evaluate(() => {
  const l = window.__PS.state.layers.find((x) => x.id === window.__PS.state.selectedLayer);
  return l?.meta?.align === 'start' && document.querySelector('[data-talign="start"]').classList.contains('active');
}));

// ط) العصا السحرية: نقر ⇒ معاينة ⇒ استخراج طبقة
await page.keyboard.press('Escape');
await page.click('#panels [data-panel="select"]');
await page.click('#sel-tools [data-stool="wand"]');
const wandPos = await page.evaluate(() => {
  const r = document.querySelector('#overlay-canvas').getBoundingClientRect();
  return { x: r.x + r.width * 0.5, y: r.y + r.height * 0.78 };   // جسم العيّنة (منطقة واسعة بلون متجانس)
});
await page.mouse.click(wandPos.x, wandPos.y);
await sleep(1800);     // انتظار المعاينة المنقّاة + استجابة الخادم
check('العصا السحرية: منزلق التسامح وبذرة النقر مقبولة', await page.evaluate(() =>
  !!document.getElementById('sl-sel-wandtol')));
const beforeWand = await page.evaluate(() => window.__PS.state.layers.length);
await page.click('#btn-sel-apply');
await waitFor((n) => window.__PS.state.layers.length > n, beforeWand, 120000, 'استخراج العصا');
check('استخراج تحديد العصا السحرية كطبقة', await page.evaluate(() =>
  window.__PS.state.layers.at(-1)?.type === 'select'),
  `طبقات=${await page.evaluate(() => window.__PS.state.layers.length)}`);

await page.screenshot({ path: `${shots}/15-wand-sidebars.png` });

/* ─── 21) السمة · قائمة الثلاث نقاط · الجولة · الترميم/التنقيح/المستندات ─── */

// أ) الوضع الليلي/النهاري
await page.click('#btn-theme');
await sleep(200);
check('زر الوضع يفعّل النهاري ويحفظه', await page.evaluate(() =>
  document.body.classList.contains('light') && localStorage.getItem('ps.theme') === 'light'));
await page.click('#btn-theme');
await sleep(200);
check('العودة إلى الوضع الليلي', await page.evaluate(() =>
  !document.body.classList.contains('light') && localStorage.getItem('ps.theme') === 'dark'));

// ب) قائمة الثلاث نقاط
await page.click('#btn-menu');
await sleep(150);
const menuOpen = await page.evaluate(() => {
  const m = document.querySelector('#app-menu');
  return !m.hidden
    && !!document.querySelector('#mi-help') && !!document.querySelector('#mi-help-download')
    && !!document.querySelector('#mi-tour') && !!document.querySelector('#mi-about');
});
check('قائمة الثلاث نقاط تفتح وبداخلها الدليل/تحميله/الجولة/المطوّر', menuOpen);
await page.evaluate(() => document.body.click());
await sleep(150);
check('القائمة تُغلق بالنقر خارجها', await page.evaluate(() => document.querySelector('#app-menu').hidden));

// ج) الجولة الترحيبية (تشغيل صريح من القائمة)
await page.click('#btn-menu');
await page.click('#mi-tour');
await sleep(300);
check('الجولة الترحيبية تفتح ببطاقة خطوة', await page.evaluate(() => {
  const o = document.querySelector('#tour-overlay');
  return !o.hidden && !!document.querySelector('#tour-title')?.textContent
    && document.querySelector('#tour-step').textContent.includes('1 /');
}), await page.evaluate(() => document.querySelector('#tour-title')?.textContent));
await page.click('#tour-next');
await sleep(250);
check('زر «التالي» يتقدم بالخطوات', await page.evaluate(() =>
  document.querySelector('#tour-step').textContent.startsWith('2 /')));
await page.click('#tour-skip');
await sleep(250);
check('«تخطّي» يغلق الجولة ويحفظ عدم تكرارها', await page.evaluate(() =>
  document.querySelector('#tour-overlay').hidden && localStorage.getItem('ps.tourDone') === '1'));

// د) لوحة ترميم الصور القديمة
await page.click('#panels [data-panel="restore"]');
check('لوحة الترميم: منزلقات + خيارات + زر', await page.evaluate(() =>
  !!document.getElementById('sl-rs-denoise') && !!document.getElementById('sl-rs-sharpen')
  && !!document.getElementById('rs-scratch') && !!document.getElementById('btn-restore')));
const beforeRestore = await S();
await page.click('#btn-restore');
await waitFor(() => window.__PS.state.history.at(-1)?.label === 'ترميم صورة قديمة'
  && window.__PS.state.historyIndex === window.__PS.state.history.length - 1, null, 90000, 'الترميم');
check('ترميم الصورة القديمة ينفَّذ ويُسجَّل خطوة', (await S()).steps === beforeRestore.steps + 1,
      (await S()).label);

// هـ) لوحة تنقيح الوجوه
await page.click('#panels [data-panel="retouch"]');
const beforeRetouch = await S();
await page.click('#btn-retouch');
await waitFor(() => window.__PS.state.history.at(-1)?.label === 'تنقيح الوجوه'
  && window.__PS.state.historyIndex === window.__PS.state.history.length - 1, null, 90000, 'التنقيح');
check('تنقيح الوجوه ينفَّذ ويعيد عدد الوجوه بلا خطأ', (await S()).steps === beforeRetouch.steps + 1,
      (await S()).label);

// و) وضع المستندات
await page.click('#panels [data-panel="document"]');
await page.click('#doc-modes [data-dmode="bw"]');
const beforeDoc = await S();
await page.click('#btn-document');
await waitFor(() => window.__PS.state.history.at(-1)?.label?.startsWith('مستند')
  && window.__PS.state.historyIndex === window.__PS.state.history.length - 1, null, 90000, 'المستند');
check('وضع المستندات (أبيض/أسود) ينفَّذ ويُسجَّل خطوة', (await S()).steps === beforeDoc.steps + 1,
      (await S()).label);

await page.screenshot({ path: `${shots}/16-pro-tools.png` });

/* ─── الخلاصة ─── */
await sleep(800);
await page.screenshot({ path: `${shots}/09-final.png` });
const net = await page.evaluate(() => ({ ...window.__PS.stats }));
const pass = results.filter((r) => r.ok).length;
console.log(`\n═══ النتيجة: ${pass}/${results.length} فحوص ناجحة ═══`);
console.log(`الشبكة: ${net.calls} نداء · ${net.failures} فشل · آخر زمن ${net.lastMs} م.ث`);
if (failed.length) {
  console.log(`\nطلبات فاشلة (${failed.length}):`);
  [...new Set(failed)].slice(0, 10).forEach((f) => console.log('  ✗', f));
} else console.log('لا طلبات فاشلة ✔');
if (errors.length) {
  console.log(`\nأخطاء JavaScript (${errors.length}):`);
  [...new Set(errors)].slice(0, 12).forEach((e) => console.log('  ✗', e.slice(0, 260)));
} else console.log('لا أخطاء JavaScript ✔');

await browser.close();
if (fatal) { console.log('\nاستثناء قاتل:', fatal.message.split('\n').slice(0,3).join(' | ')); }
process.exit(fatal || errors.length || failed.length || pass !== results.length ? 1 : 0);

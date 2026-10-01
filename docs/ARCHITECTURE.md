# المعمارية — استوديو بكسل

## طبقات النظام

```
المتصفح (HTML/CSS/JS + Canvas)
        │  JSON ‏(base64 image + params)
        ▼
FastAPI ‏/api/v1  ←  schemas (Pydantic)  ←  _common.prepare/respond
        │
        ▼
services (منطق خالص: PIL in / PIL out — ومنها restore.py للترميم/التنقيح/المستندات)
        │
        ▼
core (image_io · helpers · fonts · settings · exceptions)
```

## عقود التصميم (ملزمة)

1. **Stateless**: لا ملفات مؤقتة ولا جلسات؛ كل طلب يحمل صورته ويعيد الناتج.
2. **غلاف موحّد**: استجابة `{"image": base64, "meta": {format,mime,width,height,size_bytes,size_kb,elapsed_ms,operations}}`.
3. **دقة عددية**: حساب float32 ثم اقتطاع واحد في الترميز.
4. **بلا AI**: إزالة الخلفية = GrabCut / عصا سحرية (نمو لوني في LAB) / عصا ذكية / K‑Means / Flood‑Fill / Edge‑Cut / Color‑Key + مُقيّم أقنعة للاختيار الآلي + صقل حدودي شريطي.
5. **OpenAPI مرجع الحقيقة**: الفهرس وأعداد النقاط تُقرأ من `app.openapi()["paths"]`.

## تدفق طلب نموذجي (إزالة خلفية)

1. `POST /api/v1/segmentation/remove-background` بجسم `{"image","method","feather",…}`.
2. `prepare()` يفكّ Base64 ويتحقق (حجم/صيغة) ← PIL Image.
3. `segmentation.remove_background()` ينفّذ الطريقة، وينقّي القناع (despeckle/fill/feather)،
   ويعيد RGBA + درجات تقييم.
4. `respond()` يرمّز PNG ويضيف meta وزمن التنفيذ.

## الواجهة

- `core/state.js`: صورة/أصل/معاينة/سجل 30 خطوة/تكبير؛ أحداث `onChange`.
- `core/canvas.js`: طبقة صورة + طبقة تفاعل (crop/rect/draw/perspective)؛ أدوات رسم 10.
- `core/api.js`: غلاف fetch لكل النقاط + إحصاءات زمن/فشل.
- `ui/panels*.js`: 18 لوحة؛ كل لوحة تستدعي api وتسلّم النتيجة لـ`applyResult`.
- `ui/panels6.js`: النصوص كطبقات · تحديد الكائنات (تلقائي/مستطيل/نقاط/يدوي عبر hint_mask) · لوحة الطبقات (حذف/إخفاء/ترتيب/دمج).
- `ui/panels7.js`: ترميم الصور القديمة · تنقيح الوجوه · وضع المستندات (نقاط `/pro/*`).
- `ui/tour.js`: جولة ترحيبية تفاعلية (6 خطوات، بقعة ضوء + بطاقة) تُعرض مرة واحدة وتُعاد من القائمة.
- `app.js`: إقلاع، فتح/سحب/إفلات، تنزيل، مقارنة، اختصارات، سمة ليلي/نهاري، قائمة ثلاث نقاط؛ يعرّض `window.__PS` لأدوات الاختبار.
- `help.html`: الدليل التعليمي (قسم المساعدة) — ملف واحد مكتفٍ ذاتياً (CSS داخلي، RTL، UTF-8،
  طباعة A4 بأرقام صفحات). يُقرأ داخل الموقع عبر `/help` (iframe في نافذة عارض)،
  ويُنزَّل مرفقاً باسم `pixel-studio-guide.html` عبر `/help/download`،
  وكلا المسارين خارج OpenAPI (`include_in_schema=False`) فلا يغيّران سطح الـAPI.

## الاختبار

| الطبقة | الأداة | الحصيلة |
|--------|--------|---------|
| الخدمات/النقاط | `backend/tests/test_api_endpoints.py` (TestClient) | 252/252 |
| الواجهة كاملة | `frontend/__test__/browser-test.mjs` (Chromium حقيقي) | 87/87 |
| الخادم الحي | curl/httpx ضد uvicorn فعلي | مسارات ثابتة + مسارات عمل |

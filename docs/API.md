# مرجع واجهة البرمجة

يوفر استوديو بكسل واجهة REST لمعالجة الصور عبر FastAPI. المرجع الكامل القابل للتجربة يولّده التطبيق تلقائياً:

- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`
- OpenAPI JSON: `http://localhost:8000/api/openapi.json`
- فهرس المجموعات: `http://localhost:8000/api/v1`

## مبادئ عامة

- المسار الأساسي لجميع عمليات API هو `/api/v1`.
- جميع العمليات التي تعدّل صورة تستخدم `POST` وتستقبل JSON.
- حقل الصورة هو `image`، ويقبل Base64 خاماً أو Data URL مثل `data:image/png;base64,...`.
- الاستجابة المعتادة هي صورة Base64 داخل `image` مع معلوماتها داخل `meta`.
- الخادم عديم الحالة: لا تُحفظ الصور أو الجلسات على القرص أثناء الطلب.
- الحد الأقصى الافتراضي للصورة هو 30 MB تقريباً، مع حدود إضافية للبكسلات وأبعاد الناتج.

## شكل الاستجابة

```json
{
  "image": "iVBORw0KGgoAAA...",
  "meta": {
    "format": "PNG",
    "mime": "image/png",
    "width": 800,
    "height": 600,
    "size_bytes": 24531,
    "size_kb": 23.96,
    "elapsed_ms": 18.4,
    "operations": ["resize:fit"]
  }
}
```

بعض المسارات المعلوماتية، مثل `/formats` و`/health`، تعيد JSON خاصاً بها ولا تحتوي على `image`.

## المجموعات الرئيسية

| المجموعة           | المسار          | الاستخدام                                                     |
| ------------------ | --------------- | ------------------------------------------------------------- |
| تحويل الصيغ        | `/convert`      | تحويل PNG وJPEG وWEBP وAVIF وTIFF وBMP وGIF وICO وغيرها       |
| العمليات الهندسية  | `/geometry`     | القص، التحجيم، الدوران، القلب، المنظور، الإطارات والظلال      |
| تحسينات البكسل     | `/pixel`        | السطوع، التباين، التشبع، المستويات، المنحنيات والتدرج الرمادي |
| الفلاتر            | `/filters`      | التنعيم، التحديد، إزالة الضوضاء، الحواف والمؤثرات الفنية      |
| إزالة الخلفية      | `/segmentation` | GrabCut وColor Key وFlood Fill وK-Means وطرق كلاسيكية أخرى    |
| الدمج والعلامات    | `/composite`    | المزج، الدمج، PiP، التعريض المزدوج والعلامات المائية          |
| المؤثرات الإبداعية | `/creative`     | مؤثرات سينمائية وفنية قابلة للتطبيق بالاسم                    |
| خلفيات المنتجات    | `/backgrounds`  | توليد الخلفيات وتركيب المنتج عليها                            |
| التحليل            | `/analysis`     | المدرج، الألوان السائدة، EXIF، المقاييس والاقتراحات           |
| السلاسل والدفعات   | `/pipeline`     | تشغيل عدة عمليات ومعالجة حتى 12 صورة                          |
| الترميم            | `/restore`      | ترميم الصور القديمة، تنقيح الوجوه ومسح المستندات              |
| النظام             | `/system`       | تنزيل الصورة وفحص صحة الخادم                                  |

تظل وثيقة OpenAPI هي المرجع النهائي لأسماء الحقول وأنواعها والقيم المسموح بها، لأن المخططات تُقرأ مباشرة من نماذج Pydantic في `backend/app/schemas/operations.py`.

## أمثلة

### تحويل صورة

```bash
curl -X POST http://localhost:8000/api/v1/convert \
  -H "Content-Type: application/json" \
  -d '{"image":"data:image/png;base64,<BASE64_DATA>","format":"webp","quality":90}'
```

### تغيير الحجم

```bash
curl -X POST http://localhost:8000/api/v1/geometry/resize \
  -H "Content-Type: application/json" \
  -d '{"image":"data:image/png;base64,<BASE64_DATA>","width":1200,"height":800,"mode":"fit"}'
```

### فحص الخادم

```bash
curl http://localhost:8000/api/v1/health
```

### استخدام JavaScript

```js
const response = await fetch("/api/v1/geometry/rotate90", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ image: dataUrl, times: 1 }),
});

const result = await response.json();
const outputDataUrl = `data:${result.meta.mime};base64,${result.image}`;
```

## الأخطاء

الأخطاء المتوقعة تستخدم الشكل التالي:

```json
{
  "error": {
    "code": "validation_error",
    "message": "معاملات الطلب غير صالحة.",
    "detail": []
  }
}
```

أكواد HTTP الشائعة هي `400` للمعاملات غير المقبولة، `404` للمسار غير الموجود، `413` للحجم الزائد، `415` للصيغة غير المدعومة، `422` لفشل التحقق، و`500` للأخطاء غير المتوقعة.

## إضافة عملية جديدة

1. أضف نموذج الطلب والاستجابة في `backend/app/schemas/operations.py`.
2. ضع منطق معالجة الصورة في الخدمة المناسبة داخل `backend/app/services/`.
3. أضف المسار إلى `backend/app/api/v1/routes.py` باستخدام `prepare()` و`respond()` حيث ينطبق ذلك.
4. حدّث اختبار نقاط النهاية ثم شغّل الاختبارات قبل فتح Pull Request.

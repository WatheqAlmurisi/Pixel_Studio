# المساهمة في استوديو بكسل

شكرًا لاهتمامك بالمساهمة. المشروع مقسوم إلى واجهة HTML/CSS/JavaScript وخادم Python/FastAPI، لذلك يُفضّل إبقاء كل تغيير داخل الطبقة التي تملكه.

## إعداد بيئة التطوير

```powershell
cd backend
py -3 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

يمكن تشغيل الخادم من جذر المشروع عبر:

```powershell
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

أو عبر `bash scripts/run.sh` من Git Bash أو بيئة Linux/macOS.

## قبل رفع التغيير

شغّل اختبار API:

```powershell
python backend/tests/test_api_endpoints.py
```

ولفحص الواجهة، شغّل الخادم أولاً ثم نفّذ:

```powershell
node frontend/__test__/browser-test.mjs
```

إذا لم تكن بيئة Chromium الخاصة باختبار المتصفح متاحة، يكفي توثيق ذلك في وصف Pull Request وتشغيل اختبار API على الأقل.

## قواعد التغيير

- لا تضف نماذج ذكاء اصطناعي أو ملفات أوزان؛ إزالة الخلفية في هذا المشروع خوارزمية كلاسيكية.
- ضع منطق الصور في `backend/app/services/` ولا تضعه داخل مسارات API.
- حافظ على عقد Base64 الموحد وشكل `meta` في استجابات الصور.
- أضف أو حدّث اختبارًا عند تغيير سلوك API.
- حدّث `README.md` أو `docs/API.md` إذا تغيرت طريقة التشغيل أو المسارات أو حدود الاستخدام.
- لا ترفع `.venv` أو المخابئ أو ملفات الصور الناتجة إلى المستودع.

## Pull Request

اكتب وصفًا مختصرًا يوضح:

- المشكلة أو الحاجة التي يعالجها التغيير.
- الملفات أو الطبقة المتأثرة.
- أوامر الاختبار التي شغّلتها ونتيجتها.
- أي حدود معروفة أو تغييرات متوافقة للخلف.

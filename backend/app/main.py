"""
نقطة الدخول لتطبيق FastAPI.
===========================
المسؤوليات:
  1) إنشاء التطبيق وتوثيقه (Swagger UI بالعربية).
  2) تهيئة CORS والوسائط (Middleware) والقياس الزمني.
  3) تحويل كل استثناءات التطبيق إلى استجابة JSON موحّدة.
  4) جبل الواجهة الأمامية الثابتة وتقديمها على المسار الجذر.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.v1.routes import ROUTERS
from .core.exceptions import AppError
from .core.settings import FRONTEND_DIR, settings

# -----------------------------------------------------------------------------
#  الإعداد الأولي
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pixel-studio")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "## استوديو بكسل — محرر صور احترافي\n\n"
        "واجهة برمجة REST لمعالجة الصور: تحويل الصيغ، إزالة الخلفية (خوارزميات "
        "كلاسيكية بلا ذكاء اصطناعي)، الرسم، العمليات الهندسية، تحسينات البكسل، "
        "الفلاتر، الدمج والمزج، مكتبة خلفيات المنتجات المولّدة برمجياً، والمعالجة بالدفعات.\n\n"
        "**نمط الطلب الموحّد:** `{\"image\": \"<base64 أو data URL>\", ...}`  \n"
        "**نمط الاستجابة الموحّد:** `{\"image\": \"<base64>\", \"meta\": {...}}`\n\n"
        "> لا تُخزَّن أي صورة على الخادم — المعالجة بلا حالة (Stateless)."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True},
)

# -----------------------------------------------------------------------------
#  CORS
# -----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


# -----------------------------------------------------------------------------
#  وسيط القياس الزمني
# -----------------------------------------------------------------------------
@app.middleware("http")
async def timing_middleware(request: Request, call_next: Callable) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.1f}"
    if request.url.path.startswith(settings.API_PREFIX):
        logger.info("%s %s → %s (%.0f ms)", request.method, request.url.path,
                    response.status_code, elapsed)
    return response


# -----------------------------------------------------------------------------
#  معالجات الأخطاء الموحّدة
# -----------------------------------------------------------------------------
@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    """كل أخطاء التطبيق المتوقعة ⇒ JSON بنفس الشكل."""
    logger.warning("AppError[%s]: %s", exc.code, exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """أخطاء التحقق من المخططات ⇒ رسالة عربية واضحة مع تفاصيل الحقول."""
    details = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
        details.append({"field": loc or "body", "message": err.get("msg", ""),
                        "input": str(err.get("input"))[:80]})
    return JSONResponse(
        status_code=422,
        content={"error": {
            "code": "validation_error",
            "message": "معاملات الطلب غير صالحة.",
            "detail": details,
        }},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    """404 للمسارات غير المعروفة داخل API ⇒ JSON، أما غيرها فيعود للواجهة (SPA)."""
    if exc.status_code == 404 and not request.url.path.startswith(settings.API_PREFIX):
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    """أي خطأ غير متوقع ⇒ 500 مع رسالة عامة (والتفاصيل في السجل فقط)."""
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error",
                           "message": "حدث خطأ داخلي في الخادم أثناء المعالجة."}},
    )


# -----------------------------------------------------------------------------
#  تسجيل مسارات API
# -----------------------------------------------------------------------------
for router in ROUTERS:
    app.include_router(router, prefix=settings.API_PREFIX)


# -----------------------------------------------------------------------------
#  الجذر والواجهة الأمامية
# -----------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """تقديم الواجهة الرئيسية."""
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(status_code=503, content={
            "error": {"code": "frontend_missing",
                      "message": "لم يُعثر على ملفات الواجهة في مجلد frontend/."}})
    return FileResponse(index_file)


@app.get("/help", include_in_schema=False)
async def help_guide() -> FileResponse:
    """تقديم الدليل التعليمي (قسم المساعدة) — ملف HTML واحد للطباعة/PDF."""
    guide = FRONTEND_DIR / "help.html"
    if guide.exists():
        return FileResponse(guide)
    return JSONResponse(status_code=404, content={
        "error": {"code": "not_found", "message": "ملف الدليل غير موجود."}})


@app.get("/help/download", include_in_schema=False)
async def help_guide_download() -> FileResponse:
    """تنزيل ملف الدليل التعليمي (مرفقاً باسم واضح)."""
    guide = FRONTEND_DIR / "help.html"
    if guide.exists():
        return FileResponse(guide, filename="pixel-studio-guide.html")
    return JSONResponse(status_code=404, content={
        "error": {"code": "not_found", "message": "ملف الدليل غير موجود."}})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    icon = FRONTEND_DIR / "assets" / "icons" / "favicon.svg"
    if icon.exists():
        return FileResponse(icon, media_type="image/svg+xml")
    return Response(status_code=204)


# الأصول الثابتة (CSS/JS/Aيقونات)
_assets = FRONTEND_DIR / "assets"
if _assets.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")


def collect_endpoints() -> dict:
    """
    حصر نقاط النهاية الفعلية من مخطط OpenAPI المولَّد (المصدر الرسمي)،
    لأن FastAPI الحديث يغلّف مجموعات المسارات بكائنات بلا خاصية path.
    """
    groups: dict = {}
    try:
        paths = app.openapi().get("paths", {})
    except Exception:
        paths = {}
    for path in paths:
        if not path.startswith(settings.API_PREFIX) or path == settings.API_PREFIX:
            continue
        parts = path[len(settings.API_PREFIX):].strip("/").split("/")
        group = parts[0] if parts and parts[0] else "system"
        groups[group] = groups.get(group, 0) + len(paths[path])
    return dict(sorted(groups.items()))


@app.get("/api/v1", include_in_schema=True, tags=["النظام"], summary="فهرس نقاط النهاية")
async def api_index() -> dict:
    """قائمة مجموعات المسارات وعدد عملياتها (توثيق سريع)."""
    groups = collect_endpoints()
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
        "groups": groups,
        "total_endpoints": sum(groups.values()),
    }


# -----------------------------------------------------------------------------
#  حدث البدء
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup() -> None:
    logger.info("تشغيل %s الإصدار %s", settings.APP_NAME, settings.APP_VERSION)
    logger.info("مجلد الواجهة: %s", FRONTEND_DIR)
    # تسخين مسبق لمكتبات المعالجة لتقليل زمن أول طلب
    try:
        import cv2
        import numpy as np

        cv2.setNumThreads(max(1, (cv2.getNumberOfCPUs() or 2)))
        _ = np.zeros((8, 8, 3), np.uint8)
        logger.info("OpenCV %s — الخيوط: %s", cv2.__version__, cv2.getNumThreads())
    except Exception as exc:  # pragma: no cover
        logger.warning("تعذّر تسخين OpenCV: %s", exc)


__all__ = ["app"]

"""
الإعدادات المركزية للتطبيق.
==========================
كل القيم القابلة للضبط في مكان واحد، ويمكن تجاوزها بمتغيرات البيئة.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

# ---------------------------------------------------------------- مسارات أساسية
BACKEND_DIR: Path = Path(__file__).resolve().parents[2]
PROJECT_ROOT: Path = BACKEND_DIR.parent
FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"

# تحديد عدد خيوط OpenCV/OpenMP لتفادي استنزاف الذاكرة على الخوادم الصغيرة
os.environ.setdefault("OMP_NUM_THREADS", os.environ.get("OMP_NUM_THREADS", "2"))


class Settings:
    """كائن الإعدادات (نمط Singleton عبر lru_cache)."""

    # --- الهوية ---
    APP_NAME: str = "استوديو بكسل | Pixel Studio"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"

    # --- حدود الحماية (DoS / استهلاك الذاكرة) ---
    MAX_UPLOAD_BYTES: int = 30 * 1024 * 1024          # 30 ميجابايت للملف الواحد
    MAX_BASE64_CHARS: int = 64 * 1024 * 1024          # ~48 ميجابايت صورة فعلية
    MAX_PIXELS: int = 40_000_000                      # 40 ميجابكسل
    MAX_OUTPUT_SIDE: int = 12_000                     # أقصى بُعد للمخرجات
    MAX_BATCH_IMAGES: int = 12                        # أقصى عدد صور في الدفعة

    # --- الصيغ المدعومة ---
    SUPPORTED_INPUT: List[str] = [
        "png", "jpeg", "jpg", "webp", "avif", "bmp", "tiff", "tif", "gif",
        "ppm", "pgm", "pbm",
    ]
    SUPPORTED_OUTPUT: List[str] = ["png", "jpeg", "webp", "bmp", "tiff", "gif", "ico", "avif"]

    # ملاحظة تصميمية: إزالة الخلفية كلاسيكية بالكامل (GrabCut/K-Means/Flood-Fill/Edge-Cut)
    # ولا يعتمد المشروع على أي نموذج ذكاء اصطناعي أو ملف أوزان.

    # --- الجودة الافتراضية ---
    DEFAULT_QUALITY: int = 92

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["*"]

    # --- مكتبة الخلفيات ---
    BG_SIZE: int = 1200                 # مقاس الخلفيات المولّدة
    BG_CACHE_DIR: Path = PROJECT_ROOT / ".cache" / "backgrounds"

    @property
    def cache_enabled(self) -> bool:
        return os.environ.get("PS_BG_CACHE", "1") == "1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """إرجاع نسخة وحيدة من الإعدادات."""
    return Settings()


settings = get_settings()

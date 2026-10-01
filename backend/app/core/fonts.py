"""
إدارة الخطوط وتشكيل النص العربي.
=================================
Pillow لا يُشكّل الحروف العربية تلقائياً (وصل/اتجاه) إلا عند توفّر libraqm،
لذلك نُشكّل النص يدوياً عبر arabic-reshaper + python-bidi لضمان صحة العرض.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from PIL import ImageFont

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

# الأولوية: خط يدعم العربية واللاتينية معاً، ثم خطوط النظام
FONT_CANDIDATES: List[str] = [
    str(FONTS_DIR / "IBMPlexSansArabic-Bold.ttf"),
    str(FONTS_DIR / "IBMPlexSansArabic-Regular.ttf"),
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
]

MONO_CANDIDATES: List[str] = ["DejaVuSansMono.ttf", "DejaVuSans.ttf"]

_HAS_ARABIC = None


def has_arabic(text: str) -> bool:
    """هل يحتوي النص على حروف عربية؟"""
    return any("\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F" or "\uFB50" <= ch <= "\uFDFF"
               for ch in text)


def shape_text(text: str) -> str:
    """
    تشكيل النص العربي: وصل الحروف ثم إعادة الترتيب الثنائي الاتجاه (Bidi).
    يعود النص كما هو إن لم يحتوِ عربية أو لم تتوفر المكتبتان.
    """
    if not text or not has_arabic(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


@lru_cache(maxsize=64)
def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """إرجاع أول خط متاح بالحجم المطلوب (مع تخزين مؤقت)."""
    candidates = FONT_CANDIDATES if bold else FONT_CANDIDATES[::-1]
    for name in candidates:
        try:
            return ImageFont.truetype(name, int(size))
        except Exception:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=32)
def get_mono_font(size: int) -> ImageFont.FreeTypeFont:
    """خط أحادي العرض (يُستخدم في فن ASCII)."""
    for name in MONO_CANDIDATES:
        try:
            return ImageFont.truetype(name, int(size))
        except Exception:
            continue
    return ImageFont.load_default()


def measure(draw, text: str, font) -> tuple:
    """قياس أبعاد النص بعد التشكيل."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]


__all__ = ["FONT_CANDIDATES", "FONTS_DIR", "get_font", "get_mono_font", "has_arabic",
           "measure", "shape_text"]

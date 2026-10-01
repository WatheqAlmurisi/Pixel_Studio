"""
أدوات مشتركة لمسارات API.
========================
تفصل المنطق المتكرر (فك الصورة ← المعالجة ← الترميز ← القياس) عن المسارات
فيبقى كل مسار سطراً أو سطرين فقط.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from PIL import Image

from ...core.image_io import EncodedImage, load_image, encode_image
from ...schemas.operations import ImageMeta, ImageResponse


def prepare(payload: str, keep_exif: bool = False) -> Image.Image:
    """فك صورة الطلب إلى كائن PIL."""
    return load_image(payload, keep_exif=keep_exif).image


def respond(
    img: Image.Image,
    started: float,
    fmt: str = "png",
    *,
    quality: Optional[int] = None,
    keep_alpha: bool = True,
    keep_exif: bool = False,
    exif: Optional[Dict[str, Any]] = None,
    background: str = "#ffffff",
    operations: Optional[Iterable[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> ImageResponse:
    """ترميز النتيجة وبناء الاستجابة الموحّدة مع زمن المعالجة."""
    from ...core.helpers import parse_color

    enc: EncodedImage = encode_image(
        img, fmt,
        quality=quality,
        keep_alpha=keep_alpha,
        keep_exif=keep_exif,
        exif=exif,
        background=parse_color(background),
    )
    meta = ImageMeta(
        format=enc.format,
        mime=enc.mime,
        width=enc.width,
        height=enc.height,
        size_bytes=enc.size_bytes,
        size_kb=enc.size_kb if hasattr(enc, "size_kb") else round(enc.size_bytes / 1024, 2),
        elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        operations=list(operations or []),
    )
    payload: Dict[str, Any] = {"image": enc.data, "meta": meta.model_dump()}
    if extra:
        payload.update(extra)
    # FastAPI يقوم بالتسلسل؛ نكتفي بإرجاع dict مطابق لمخطط ImageResponse
    return payload  # type: ignore[return-value]


def respond_dict(
    img: Image.Image,
    started: float,
    fmt: str = "png",
    *,
    quality: Optional[int] = None,
    keep_alpha: bool = True,
    background: str = "#ffffff",
    operations: Optional[Iterable[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """نسخة تُرجع dict (عندما نحتاج حقولاً إضافية مثل القناع أو الدرجات)."""
    from ...core.helpers import parse_color

    enc = encode_image(
        img, fmt, quality=quality, keep_alpha=keep_alpha, background=parse_color(background)
    )
    out: Dict[str, Any] = {
        "image": enc.data,
        "meta": {
            "format": enc.format,
            "mime": enc.mime,
            "width": enc.width,
            "height": enc.height,
            "size_bytes": enc.size_bytes,
            "size_kb": round(enc.size_bytes / 1024, 2),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "operations": list(operations or []),
        },
    }
    if extra:
        out.update(extra)
    return out


__all__ = ["prepare", "respond", "respond_dict"]

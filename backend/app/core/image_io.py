"""
طبقة الإدخال/الإخراج للصور (Image I/O).
======================================
المسؤولية الوحيدة لهذا الملف: تحويل (Base64 / bytes / UploadFile) ⇄ كائن PIL.Image،
مع ضبط الصيغ والشفافية والبيانات الوصفية والحدود الأمنية. لا يحتوي أي منطق معالجة.
"""
from __future__ import annotations

import base64
import binascii
import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

from .exceptions import (
    ImageDecodeError,
    ImageTooLargeError,
    InvalidParameterError,
    UnsupportedFormatError,
)
from .settings import settings

# ------------------------------------------------------------------------------
# جدول الصيغ: اسم Pillow ⇄ الامتداد ⇄ نوع MIME ⇄ هل تدعم قناة شفافية
# ------------------------------------------------------------------------------
ALPHA_FORMATS = {"PNG", "WEBP", "TIFF", "ICO", "AVIF"}

FORMATS: Dict[str, Dict[str, Any]] = {
    "png":  {"pil": "PNG",  "ext": "png",  "mime": "image/png",              "alpha": True},
    "jpeg": {"pil": "JPEG", "ext": "jpg",  "mime": "image/jpeg",             "alpha": False},
    "jpg":  {"pil": "JPEG", "ext": "jpg",  "mime": "image/jpeg",             "alpha": False},
    "webp": {"pil": "WEBP", "ext": "webp", "mime": "image/webp",             "alpha": True},
    "bmp":  {"pil": "BMP",  "ext": "bmp",  "mime": "image/bmp",              "alpha": False},
    "tiff": {"pil": "TIFF", "ext": "tiff", "mime": "image/tiff",             "alpha": True},
    "tif":  {"pil": "TIFF", "ext": "tiff", "mime": "image/tiff",             "alpha": True},
    "gif":  {"pil": "GIF",  "ext": "gif",  "mime": "image/gif",              "alpha": False},
    "ico":  {"pil": "ICO",  "ext": "ico",  "mime": "image/x-icon",           "alpha": True},
    "avif": {"pil": "AVIF", "ext": "avif", "mime": "image/avif",             "alpha": True},
    "ppm":  {"pil": "PPM",  "ext": "ppm",  "mime": "image/x-portable-pixmap","alpha": False},
}

_DATA_URL_RE = re.compile(r"^data:image/([a-zA-Z0-9.+-]+);base64,(.*)$", re.DOTALL)


# ==============================================================================
#  هياكل البيانات
# ==============================================================================
@dataclass
class LoadedImage:
    """نتيجة فك صورة: الكائن + بياناته الوصفية الأصلية."""

    image: Image.Image
    source_format: str = "unknown"
    original_size: Optional[int] = None
    has_alpha: bool = False
    exif: Dict[str, Any] = field(default_factory=dict)
    info: Dict[str, Any] = field(default_factory=dict)

    @property
    def width(self) -> int:
        return self.image.width

    @property
    def height(self) -> int:
        return self.image.height


@dataclass
class EncodedImage:
    """نتيجة ترميز صورة: Base64 + بيانات وصفية."""

    data: str                 # base64 خام بدون بادئة data:
    data_url: str             # data:image/...;base64,...
    mime: str
    format: str
    width: int
    height: int
    size_bytes: int

    def meta(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "mime": self.mime,
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
            "size_kb": round(self.size_bytes / 1024, 2),
        }


# ==============================================================================
#  الفك (Decode)
# ==============================================================================
def strip_data_url(value: str) -> Tuple[str, Optional[str]]:
    """فصل بادئة data URL إن وُجدت. يُرجع (base64, نوع معلن)."""
    value = value.strip()
    match = _DATA_URL_RE.match(value)
    if match:
        return match.group(2), match.group(1).lower()
    return value, None


def decode_base64(value: str) -> bytes:
    """فك ترميز Base64 مع تحقق من الحجم ومن سلامة الترميز."""
    if not value:
        raise InvalidParameterError("حقل الصورة فارغ.")
    if len(value) > settings.MAX_BASE64_CHARS:
        raise ImageTooLargeError(
            f"حجم الصورة المرسلة يتجاوز الحد المسموح ({settings.MAX_BASE64_CHARS // (1024*1024)} م.حرف)."
        )
    raw, _ = strip_data_url(value)
    # إصلاح الحشو الناقص الشائع عند النسخ من المتصفح
    padding = (-len(raw)) % 4
    if padding:
        raw += "=" * padding
    try:
        return base64.b64decode(raw, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ImageDecodeError("تعذّر فك ترميز Base64: البيانات ليست صورة مُرمّزة بشكل صحيح.") from exc


def open_image_bytes(data: bytes, *, name: str = "") -> Image.Image:
    """فتح صورة من بايتات مع تطبيق اتجاه EXIF والتحقق من الحدود."""
    if not data:
        raise ImageDecodeError("لا توجد بيانات للصورة.")
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise ImageTooLargeError(
            f"حجم الملف ({len(data) // 1024} ك.بايت) يتجاوز الحد المسموح "
            f"({settings.MAX_UPLOAD_BYTES // (1024*1024)} م.بايت)."
        )
    try:
        img = Image.open(io.BytesIO(data))
        img.load()  # إجبار القراءة الآن لاكتشاف الملفات التالفة مبكراً
    except Exception as exc:
        raise ImageDecodeError(detail=str(exc)) from exc

    # تدوير الصورة حسب علامة الاتجاه في EXIF (هواتف المحمول)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    _check_pixels(img)
    return img


def _check_pixels(img: Image.Image) -> None:
    pixels = img.width * img.height
    if pixels > settings.MAX_PIXELS:
        raise ImageTooLargeError(
            f"أبعاد الصورة {img.width}×{img.height} = {pixels:,} بكسل، "
            f"والحد المسموح {settings.MAX_PIXELS:,} بكسل."
        )


def load_image(payload: str | bytes, *, keep_exif: bool = False) -> LoadedImage:
    """
    نقطة الدخول الموحّدة لفك الصور.
    يقبل: Base64 خام، data URL، أو بايتات.
    """
    if isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
        declared = None
    else:
        if not isinstance(payload, str):
            raise InvalidParameterError("حقل الصورة يجب أن يكون نص Base64 أو بايتات.")
        data = decode_base64(payload)
        _, declared = strip_data_url(payload)

    img = open_image_bytes(data)

    # ترتيب تحديد الصيغة: توقيع البايتات (الأدق) ← علامة Pillow ← النوع المعلن
    source_format = (
        guess_format_from_bytes(data) if data else "unknown"
    )
    if source_format == "unknown":
        source_format = (img.format or declared or "unknown").lower()
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )

    exif: Dict[str, Any] = {}
    if keep_exif:
        try:
            raw_exif = img.getexif()
            exif = {str(k): _safe(v) for k, v in raw_exif.items()}
        except Exception:
            exif = {}

    return LoadedImage(
        image=img,
        source_format=source_format,
        original_size=len(data),
        has_alpha=has_alpha,
        exif=exif,
        info={k: _safe(v) for k, v in img.info.items() if k in ("dpi", "comment", "duration")},
    )


def _safe(value: Any) -> Any:
    """تحويل قيم EXIF إلى أنواع قابلة للتسلسل JSON."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "replace")
        except Exception:
            return repr(value)
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return str(value)


# ==============================================================================
#  الترميز (Encode)
# ==============================================================================
def normalize_format(fmt: Optional[str]) -> str:
    """توحيد اسم الصيغة إلى مفتاح جدول FORMATS."""
    if not fmt:
        return "png"
    key = fmt.lower().strip().lstrip(".")
    if key == "jpe":
        key = "jpeg"
    if key not in FORMATS:
        raise UnsupportedFormatError(
            f"الصيغة «{fmt}» غير مدعومة.",
            detail={"supported": sorted(settings.SUPPORTED_OUTPUT)},
        )
    return key


def prepare_for_format(
    img: Image.Image,
    fmt_key: str,
    *,
    background: Tuple[int, int, int] = (255, 255, 255),
    keep_alpha: bool = True,
) -> Image.Image:
    """
    تجهيز الصورة للصيغة الهدف:
      • الصيغ غير الداعمة للشفافية ⇒ دمج الشفافية على لون خلفية.
      • الصيغ الداعمة ⇒ ضمان RGBA.
    """
    spec = FORMATS[fmt_key]
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)

    if not keep_alpha or not spec["alpha"]:
        if has_alpha:
            base = Image.new("RGB", img.size, background)
            rgba = img.convert("RGBA")
            base.paste(rgba, mask=rgba.split()[-1])
            return base
        return img.convert("RGB")

    # صيغة تدعم الشفافية
    if img.mode == "P":
        return img.convert("RGBA")
    if img.mode in ("RGB", "L"):
        return img.convert("RGBA")
    if img.mode == "LA":
        return img.convert("RGBA")
    if img.mode in ("RGBA", "RGBX"):
        return img
    if img.mode.startswith("I") or img.mode.startswith("F"):
        return img.convert("RGBA")
    if img.mode == "CMYK":
        return img.convert("RGBA")
    return img.convert("RGBA")


def encode_image(
    img: Image.Image,
    fmt: str = "png",
    *,
    quality: Optional[int] = None,
    optimize: bool = True,
    background: Tuple[int, int, int] = (255, 255, 255),
    keep_alpha: bool = True,
    keep_exif: bool = False,
    exif: Optional[Dict[str, Any]] = None,
    png_compression: int = 6,
) -> EncodedImage:
    """ترميز الصورة إلى الصيغة المطلوبة وإرجاع Base64 + بيانات وصفية."""
    fmt_key = normalize_format(fmt)
    spec = FORMATS[fmt_key]
    pil_format = spec["pil"]

    prepared = prepare_for_format(img, fmt_key, background=background, keep_alpha=keep_alpha)

    # ICO لا يقبل أبعاداً اعتباطية ⇒ تصغير إلى أقرب مقاس مسموح.
    # ملاحظة: مُرمِّز ICO في Pillow يكتب عدة مقاسات داخل الملف الواحد،
    # وإعادة الترميز تُنقّص المقاس تدريجياً؛ لذلك نعتمد لاحقاً المقاس الفعلي
    # للبايتات الناتجة (بعد فكّها) كمصدر وحيد للحقيقة.
    if pil_format == "ICO":
        prepared = _fit_for_ico(prepared)

    q = settings.DEFAULT_QUALITY if quality is None else max(1, min(100, int(quality)))

    save_kwargs: Dict[str, Any] = {}
    if pil_format in ("JPEG", "WEBP", "AVIF"):
        save_kwargs["quality"] = q
    if pil_format == "WEBP":
        save_kwargs["method"] = 4
    if pil_format == "AVIF":
        save_kwargs["speed"] = 6
    if pil_format == "PNG":
        save_kwargs["optimize"] = optimize
        save_kwargs["compress_level"] = max(0, min(9, png_compression))
    if pil_format == "GIF":
        save_kwargs["optimize"] = optimize
    if pil_format in ("TIFF",):
        save_kwargs["compression"] = "tiff_lzw"

    if keep_exif and pil_format in ("JPEG", "WEBP", "PNG", "TIFF", "AVIF"):
        try:
            if exif:
                from PIL import Image as _I

                exif_obj = _I.Exif()
                for k, v in exif.items():
                    try:
                        exif_obj[int(k)] = v
                    except Exception:
                        continue
                if exif_obj:
                    save_kwargs["exif"] = exif_obj.tobytes()
            elif getattr(img, "info", {}).get("exif"):
                save_kwargs["exif"] = img.info["exif"]
        except Exception:
            pass

    buffer = io.BytesIO()
    try:
        prepared.save(buffer, format=pil_format, **save_kwargs)
    except Exception as exc:
        from .exceptions import ProcessingError

        raise ProcessingError(f"فشل ترميز الصورة إلى {pil_format}.", detail=str(exc)) from exc

    raw = buffer.getvalue()

    # التحقق النهائي: نفكّ البايتات التي كتبناها فعلاً ونعتمد أبعادها الحقيقية،
    # حتى لا نبلّغ مقاساً يختلف عمّا يراه أي قارئ (مهم في ICO/GIF متعدد الإطارات).
    out_w, out_h = prepared.width, prepared.height
    try:
        with Image.open(io.BytesIO(raw)) as check:
            check.load()
            out_w, out_h = check.width, check.height
    except Exception:
        pass

    b64 = base64.b64encode(raw).decode("ascii")
    mime = spec["mime"]
    return EncodedImage(
        data=b64,
        data_url=f"data:{mime};base64,{b64}",
        mime=mime,
        format=fmt_key,
        width=out_w,
        height=out_h,
        size_bytes=len(raw),
    )


def _fit_for_ico(img: Image.Image) -> Image.Image:
    """تصغير الصورة إلى أكبر مقاس ICO مسموح (≤256) مع الحفاظ على النسبة."""
    allowed = [16, 24, 32, 48, 64, 128, 256]
    longest = max(img.width, img.height)
    target = max(a for a in allowed if a <= max(16, min(256, longest)))
    ratio = target / longest
    new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
    return img.resize(new_size, Image.LANCZOS)


def guess_format_from_bytes(data: bytes) -> str:
    """تخمين الصيغة من توقيع البايتات (Magic Bytes) — أدق من الامتداد."""
    signatures: List[Tuple[bytes, str]] = [
        (b"\x89PNG\r\n\x1a\n", "png"),
        (b"\xff\xd8\xff", "jpeg"),
        (b"RIFF", "webp"),          # + WEBP عند الإزاحة 8
        (b"GIF8", "gif"),
        (b"BM", "bmp"),
        (b"II*\x00", "tiff"),
        (b"MM\x00*", "tiff"),
        (b"\x00\x00\x01\x00", "ico"),
        (b"P6", "ppm"),
        (b"P5", "ppm"),
    ]
    for sig, fmt in signatures:
        if data.startswith(sig):
            if fmt == "webp" and data[8:12] != b"WEBP":
                continue
            return fmt
    if data[4:12] == b"ftypavif" or data[4:12] == b"ftypmif1":
        return "avif"
    return "unknown"


def human_size(num_bytes: int) -> str:
    """تنسيق حجم الملف بصورة مقروءة."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


__all__ = [
    "ALPHA_FORMATS",
    "FORMATS",
    "EncodedImage",
    "LoadedImage",
    "decode_base64",
    "encode_image",
    "guess_format_from_bytes",
    "human_size",
    "load_image",
    "normalize_format",
    "prepare_for_format",
    "strip_data_url",
]

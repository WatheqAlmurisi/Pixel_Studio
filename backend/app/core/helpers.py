"""
دوال مساعدة مشتركة بين وحدات المعالجة.
=====================================
تحويل PIL ⇄ NumPy، ضبط المجالات الرقمية، ألوان، ومقاييس هندسية.
القاعدة الحاكمة: **كل الحسابات في float32 بمجال [0,1] أو [0,255]، والتحويل إلى
uint8 يحدث في الخطوة الأخيرة فقط** لتفادي تراكم أخطاء التقريب.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

# ------------------------------------------------------------------------------
#  التحويل بين PIL و NumPy / OpenCV
# ------------------------------------------------------------------------------


def to_rgb_array(img: Image.Image) -> np.ndarray:
    """PIL → مصفوفة RGB بمجال [0,255] ونوع float32."""
    if img.mode != "RGB":
        img = img.convert("RGB")
    return np.asarray(img, dtype=np.float32)


def to_rgba_array(img: Image.Image) -> np.ndarray:
    """PIL → مصفوفة RGBA بمجال [0,255] ونوع float32."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return np.asarray(img, dtype=np.float32)


def from_rgb_array(arr: np.ndarray) -> Image.Image:
    """مصفوفة RGB → PIL (مع قصّ آمن للمجال)."""
    arr = np.clip(np.asarray(arr, dtype=np.float32), 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def from_rgba_array(arr: np.ndarray) -> Image.Image:
    """مصفوفة RGBA → PIL (مع قصّ آمن للمجال)."""
    arr = np.clip(np.asarray(arr, dtype=np.float32), 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def from_gray_array(arr: np.ndarray) -> Image.Image:
    """مصفوفة أحادية القناة → PIL (وضع L)."""
    arr = np.clip(np.asarray(arr, dtype=np.float32), 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "L")


def bgr(arr: np.ndarray) -> np.ndarray:
    """RGB ⇄ BGR (OpenCV يستخدم BGR)."""
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def rgb(arr: np.ndarray) -> np.ndarray:
    """BGR ⇄ RGB."""
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def unit(arr: np.ndarray) -> np.ndarray:
    """تحويل إلى المجال [0,1]."""
    return np.asarray(arr, dtype=np.float32) / 255.0


def byte(arr: np.ndarray) -> np.ndarray:
    """تحويل من المجال [0,1] إلى [0,255]."""
    return np.clip(np.asarray(arr, dtype=np.float32) * 255.0, 0, 255)


# ------------------------------------------------------------------------------
#  الألوان
# ------------------------------------------------------------------------------
def parse_color(value: str | Sequence[int] | None, default: Tuple[int, int, int] = (255, 255, 255)) -> Tuple[int, int, int]:
    """
    تحليل لون من صيغ متعددة:
      "#rrggbb" | "rgb(r,g,b)" | (r,g,b) | اسم لون بسيط
    """
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        vals = tuple(int(max(0, min(255, v))) for v in value[:3])
        while len(vals) < 3:
            vals = vals + (0,)
        return vals  # type: ignore[return-value]

    text = str(value).strip().lower()
    named = {
        "white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0),
        "green": (0, 128, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
        "transparent": (0, 0, 0),
    }
    if text in named:
        return named[text]

    if text.startswith("#"):
        hexv = text[1:]
        if len(hexv) == 3:
            hexv = "".join(c * 2 for c in hexv)
        if len(hexv) >= 6:
            try:
                return (int(hexv[0:2], 16), int(hexv[2:4], 16), int(hexv[4:6], 16))
            except ValueError:
                return default

    if text.startswith("rgb"):
        digits = "".join(ch if (ch.isdigit() or ch == ",") else "" for ch in text)
        parts = [p for p in digits.split(",") if p != ""]
        if len(parts) >= 3:
            return tuple(int(max(0, min(255, float(p)))) for p in parts[:3])  # type: ignore[return-value]

    return default


def luminance(arr: np.ndarray) -> np.ndarray:
    """حساب الإضاءة وفق معاملات Rec.709 من مصفوفة RGB [0,255]."""
    a = np.asarray(arr, dtype=np.float32)
    if a.ndim == 2:
        return a
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


# ------------------------------------------------------------------------------
#  المنحنيات والاستيفاء
# ------------------------------------------------------------------------------
def build_lut(points: Sequence[Tuple[float, float]], size: int = 256) -> np.ndarray:
    """
    بناء جدول بحث (LUT) من نقاط تحكم (مدخل/مخرج بمجال [0,1])
    باستخدام استيفاء تكعيبي رتيب (PCHIP) يحافظ على عدم انقلاب التدرّج.
    """
    pts = sorted({(float(max(0.0, min(1.0, x))), float(max(0.0, min(1.0, y)))) for x, y in points})
    if len(pts) < 2:
        pts = [(0.0, 0.0), (1.0, 1.0)]
    if pts[0][0] > 0.0:
        pts.insert(0, (0.0, pts[0][1]))
    if pts[-1][0] < 1.0:
        pts.append((1.0, pts[-1][1]))

    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)

    # إزالة التكرار في الإحداثي السيني (يمنع قسمة على صفر)
    keep = np.concatenate(([True], np.diff(xs) > 1e-9))
    xs, ys = xs[keep], ys[keep]
    if len(xs) < 2:
        xs, ys = np.array([0.0, 1.0]), np.array([0.0, 1.0])

    grid = np.linspace(0.0, 1.0, size)
    try:
        from scipy.interpolate import PchipInterpolator  # type: ignore

        ys_interp = PchipInterpolator(xs, ys)(grid)
    except Exception:
        # بديل بلا scipy: استيفاء خطي
        ys_interp = np.interp(grid, xs, ys)

    return (np.clip(ys_interp, 0.0, 1.0) * (size - 1)).astype(np.float32)


def apply_lut(arr: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """تطبيق LUT أحادي على كل قنوات الصورة (مجال [0,255])."""
    idx = np.clip(np.asarray(arr, dtype=np.float32), 0, 255)
    lo = np.floor(idx).astype(np.int32)
    hi = np.minimum(lo + 1, len(lut) - 1)
    frac = idx - lo
    return lut[lo] * (1 - frac) + lut[hi] * frac


# ------------------------------------------------------------------------------
#  مقاييس وهندسة
# ------------------------------------------------------------------------------
def clamp_size(width: int, height: int, max_side: int) -> Tuple[int, int]:
    """قصّ الأبعاد عند الحد الأقصى مع الحفاظ على النسبة."""
    longest = max(width, height)
    if longest <= max_side:
        return max(1, int(width)), max(1, int(height))
    ratio = max_side / longest
    return max(1, int(round(width * ratio))), max(1, int(round(height * ratio)))


def fit_size(width: int, height: int, max_w: Optional[int], max_h: Optional[int]) -> Tuple[int, int]:
    """حساب مقاس يناسب صندوقاً معطى مع الحفاظ على النسبة."""
    scale = 1.0
    if max_w:
        scale = min(scale, max_w / width)
    if max_h:
        scale = min(scale, max_h / height)
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def odd(value: int) -> int:
    """تقريب إلى أقرب عدد فردي (مطلوب في بعض نوى OpenCV)."""
    value = max(1, int(value))
    return value if value % 2 == 1 else value + 1


def validate_range(name: str, value: float, low: float, high: float) -> float:
    """التحقق من وقوع قيمة ضمن مجال، مع اسم واضح للخطأ."""
    from .exceptions import InvalidParameterError

    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(f"المعامل «{name}» يجب أن يكون رقماً.") from exc
    if value < low or value > high:
        raise InvalidParameterError(f"المعامل «{name}» يجب أن يكون بين {low} و {high} (القيمة: {value}).")
    return value


def validate_choice(name: str, value: str, choices: Iterable[str]) -> str:
    """التحقق من أن القيمة ضمن قائمة خيارات."""
    from .exceptions import InvalidParameterError

    allowed = list(choices)
    if value not in allowed:
        raise InvalidParameterError(
            f"المعامل «{name}» يجب أن يكون أحد: {', '.join(allowed)}", detail={"value": value}
        )
    return value


def downscale_for_speed(img: Image.Image, max_side: int = 1600) -> Tuple[Image.Image, float]:
    """
    تصغير مؤقت لتسريع العمليات الثقيلة (مثل GrabCut)، ويُرجع معامل التصغير
    كي تُعاد النتيجة إلى المقاس الأصلي.
    """
    longest = max(img.width, img.height)
    if longest <= max_side:
        return img, 1.0
    ratio = max_side / longest
    return img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), Image.BILINEAR), ratio


__all__ = [
    "apply_lut", "bgr", "build_lut", "byte", "clamp_size", "downscale_for_speed",
    "fit_size", "from_gray_array", "from_rgb_array", "from_rgba_array", "luminance",
    "odd", "parse_color", "rgb", "to_rgb_array", "to_rgba_array", "unit",
    "validate_choice", "validate_range",
]

"""
تحسينات الصورة على مستوى البكسل.
================================
كل دالة تأخذ PIL.Image وتُرجع PIL.Image، وتعمل داخلياً بمجال float32 [0,255].
لا يحدث أي تحويل إلى uint8 إلا في نهاية كل عملية مستقلة، ما يقلّل فقد الدقة.

ترتيب التطبيق المعتمد (من الأصح بصرياً):
  التعرّض ← توازن الأبيض ← الحرارة ← السطوع ← التباين ← المستويات ← جاما ←
  المنحنيات ← التشبّع/Vibrance ← درجة اللون ← توازن الألوان ← ماتريكس القنوات ←
  البوسترة/العتبة ← العكس
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

from ..core.helpers import (
    apply_lut,
    build_lut,
    luminance,
    to_rgb_array,
    from_rgb_array,
    unit,
    byte,
    validate_range,
)


# ==============================================================================
#  ضبط القيم
# ==============================================================================
def adjust_brightness(img: Image.Image, value: float) -> Image.Image:
    """السطوع: إزاحة خطية [-100..100] ⇒ [-255..255]/2."""
    if value == 0:
        return img
    arr = to_rgb_array(img) + float(value) * 2.55
    return from_rgb_array(arr)


def adjust_contrast(img: Image.Image, value: float) -> Image.Image:
    """التباين حول نقطة المنتصف (128): [-100..100] ⇒ معامل [0..2]."""
    if value == 0:
        return img
    factor = (100.0 + float(value)) / 100.0
    arr = (to_rgb_array(img) - 128.0) * factor + 128.0
    return from_rgb_array(arr)


def adjust_saturation(img: Image.Image, value: float) -> Image.Image:
    """التشبّع: مزج بين الصورة الرمادية والأصلية في فضاء HSL."""
    if value == 0:
        return img
    arr = to_rgb_array(img).astype(np.uint8)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * ((100.0 + float(value)) / 100.0), 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    return from_rgb_array(out)


def adjust_vibrance(img: Image.Image, value: float) -> Image.Image:
    """
    التشبّع الذكي (Vibrance): يعزّز الألوان الباهتة فقط ويحمي الألوان المشبعة
    مسبقاً وملفات البشرة، على عكس التشبّع الخطي.
    """
    if value == 0:
        return img
    arr = to_rgb_array(img).astype(np.uint8)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
    s = hsv[..., 1] / 255.0
    # وزن inversely proportional للتشبّع الحالي
    amount = float(value) / 100.0
    weight = (1.0 - s) ** 2
    hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + amount * weight * 2.0), 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    return from_rgb_array(out)


def adjust_exposure(img: Image.Image, value: float) -> Image.Image:
    """التعرّض: ضرب أُسّي بمحور الإضاءة (EV) — [-3..3] stop."""
    if value == 0:
        return img
    factor = 2.0 ** (float(value) / 1.0)
    arr = to_rgb_array(img) * factor
    return from_rgb_array(arr)


def adjust_gamma(img: Image.Image, value: float) -> Image.Image:
    """تصحيح جاما: out = 255·(in/255)^(1/γ)."""
    if abs(value - 1.0) < 1e-3:
        return img
    lut = build_lut([(0.0, 0.0), (1.0, 1.0)])  # placeholder لاستيراد ثابت
    x = np.linspace(0, 1, 256, dtype=np.float32)
    lut = np.clip(x ** (1.0 / max(0.05, float(value))), 0, 1) * 255.0
    arr = to_rgb_array(img)
    idx = np.clip(arr, 0, 255).astype(np.int32)
    return from_rgb_array(lut[idx])


def adjust_temperature(img: Image.Image, value: float) -> Image.Image:
    """
    حرارة اللون: قيمة سالبة ⇒ أزرق (بارد)، موجبة ⇒ برتقالي (دافئ).
    تُطبَّق كإزاحة متعاكسة على قناتَي R و B مع تصحيح طفيف للأخضر.
    """
    if value == 0:
        return img
    arr = to_rgb_array(img)
    shift = float(value) * 1.2
    arr[..., 0] += shift          # R
    arr[..., 2] -= shift          # B
    arr[..., 1] += shift * 0.15   # G
    return from_rgb_array(arr)


def adjust_tint(img: Image.Image, value: float) -> Image.Image:
    """صبغة اللون: سالبة ⇒ أخضر، موجبة ⇒ أرجواني."""
    if value == 0:
        return img
    arr = to_rgb_array(img)
    shift = float(value) * 1.0
    arr[..., 1] += shift
    arr[..., 0] -= shift * 0.4
    arr[..., 2] -= shift * 0.4
    return from_rgb_array(arr)


def adjust_hue(img: Image.Image, value: float) -> Image.Image:
    """إزاحة درجة اللون [-180..180] درجة على عجلة الألوان."""
    if value == 0:
        return img
    arr = to_rgb_array(img).astype(np.uint8)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[..., 0] = (hsv[..., 0] + float(value) * (180.0 / 180.0)) % 180.0
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    return from_rgb_array(out)


def adjust_levels(
    img: Image.Image,
    in_black: float = 0.0,
    in_white: float = 1.0,
    mid_gamma: float = 1.0,
    out_black: float = 0.0,
    out_white: float = 1.0,
) -> Image.Image:
    """
    مستويات (Levels) كتلك الموجودة في Photoshop:
      out = out_black + (out_white-out_black) · ((in-in_black)/(in_white-in_black))^(1/γ)
    """
    in_black = min(max(float(in_black), 0.0), 0.99)
    in_white = max(min(float(in_white), 1.0), in_black + 0.01)
    mid_gamma = min(max(float(mid_gamma), 0.1), 10.0)

    def f(x: np.ndarray) -> np.ndarray:
        v = (x - in_black) / (in_white - in_black)
        v = np.clip(v, 0, 1) ** (1.0 / mid_gamma)
        return out_black + (out_white - out_black) * v

    lut = (f(np.linspace(0, 1, 256, dtype=np.float32)) * 255.0).astype(np.float32)
    arr = to_rgb_array(img)
    idx = np.clip(arr, 0, 255).astype(np.int32)
    return from_rgb_array(lut[idx])


def adjust_curves(img: Image.Image, points: Sequence[Tuple[float, float]], channel: str = "rgb") -> Image.Image:
    """
    منحنيات (Curves): نقاط تحكم (مدخل، مخرج) بمجال [0..1] مع استيفاء تكعيبي رتيب.
    channel: rgb | r | g | b
    """
    lut = build_lut(points)
    arr = to_rgb_array(img)
    if channel in ("r", "g", "b"):
        idx = {"r": 0, "g": 1, "b": 2}[channel]
        out = arr.copy()
        out[..., idx] = apply_lut(arr[..., idx], lut)
        return from_rgb_array(out)
    out = apply_lut(arr, lut)
    return from_rgb_array(out)


def adjust_color_balance(
    img: Image.Image,
    shadows: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    midtones: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    highlights: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Image.Image:
    """
    توازن الألوان حسب نطاق الإضاءة: كل تعديل يُوزَّن بمنحنى جرسي حول نطاقه،
    تماماً كما في أدوات التصحيح اللوني الاحترافية.
    """
    arr = to_rgb_array(img)
    lum = luminance(arr) / 255.0

    def gauss(center: float, width: float) -> np.ndarray:
        return np.exp(-((lum - center) ** 2) / (2 * width ** 2))

    w_sh = gauss(0.15, 0.25)[..., None]
    w_mid = gauss(0.5, 0.30)[..., None]
    w_hi = gauss(0.85, 0.25)[..., None]

    delta = (
        np.array(shadows, dtype=np.float32).reshape(1, 1, 3) * w_sh
        + np.array(midtones, dtype=np.float32).reshape(1, 1, 3) * w_mid
        + np.array(highlights, dtype=np.float32).reshape(1, 1, 3) * w_hi
    )
    return from_rgb_array(arr + delta * 2.55)


def apply_channel_mixer(img: Image.Image, matrix: Sequence[Sequence[float]]) -> Image.Image:
    """ماتريكس القنوات 3×3: كل خرج = مزيج خطي من R,G,B."""
    m = np.array(matrix, dtype=np.float32)
    if m.shape != (3, 3):
        from ..core.exceptions import InvalidParameterError

        raise InvalidParameterError("مصفوفة خلط القنوات يجب أن تكون 3×3.")
    arr = to_rgb_array(img)
    out = arr.reshape(-1, 3) @ m.T
    return from_rgb_array(out.reshape(arr.shape))


def white_balance(img: Image.Image, method: str = "grayworld", strength: float = 1.0) -> Image.Image:
    """
    توازن أبيض تلقائي:
      • grayworld : ضبط متوسطات القنوات على قيمة رمادية واحدة.
      • whitepatch: اعتماد ألمع بكسل كمرجع أبيض.
    """
    arr = to_rgb_array(img)
    strength = min(max(float(strength), 0.0), 1.0)

    if method == "whitepatch":
        #Percentile 99.5 لكل قناة كمرجع للأبيض
        ref = np.percentile(arr.reshape(-1, 3), 99.5, axis=0)
    else:
        ref = arr.reshape(-1, 3).mean(axis=0)

    target = float(ref.mean())
    gains = np.where(ref > 1e-3, target / np.maximum(ref, 1e-3), 1.0).astype(np.float32)
    gains = 1.0 + (gains - 1.0) * strength
    return from_rgb_array(arr * gains.reshape(1, 1, 3))


def auto_levels(img: Image.Image, clip: float = 0.5) -> Image.Image:
    """تمديد تلقائي للمستويات: يقصّ نسبة `clip`% من الطرفين ثم يمدّ المجال."""
    arr = to_rgb_array(img)
    flat = arr.reshape(-1, 3)
    lo = np.percentile(flat, clip, axis=0)
    hi = np.percentile(flat, 100 - clip, axis=0)
    span = np.maximum(hi - lo, 1.0)
    out = (arr - lo) / span * 255.0
    return from_rgb_array(out)


def auto_contrast(img: Image.Image, clip: float = 1.0) -> Image.Image:
    """تباين تلقائي على قناة الإضاءة مع الحفاظ على الألوان."""
    arr = to_rgb_array(img)
    lum = luminance(arr)
    lo, hi = np.percentile(lum, clip), np.percentile(lum, 100 - clip)
    if hi - lo < 1.0:
        return img
    factor = 255.0 / (hi - lo)
    out = (arr - lo) * factor
    return from_rgb_array(out)


def posterize(img: Image.Image, levels: int = 4) -> Image.Image:
    """تقليل عدد مستويات كل قناة (تأثير ملصق)."""
    levels = int(np.clip(levels, 2, 32))
    step = 255.0 / (levels - 1)
    arr = to_rgb_array(img)
    out = np.round(arr / step) * step
    return from_rgb_array(out)


def threshold(
    img: Image.Image, value: float = 128.0, mode: str = "binary", color: bool = False
) -> Image.Image:
    """
    عتبة (Threshold): binary | binary_inv | otsu | adaptive | tozero | trunc.
    عند color=True تُطبَّق العتبة على الإضاءة مع الحفاظ على ألوان البكسلات.
    """
    arr = to_rgb_array(img)
    gray = luminance(arr).astype(np.uint8)

    flags = {
        "binary": cv2.THRESH_BINARY,
        "binary_inv": cv2.THRESH_BINARY_INV,
        "otsu": cv2.THRESH_BINARY | cv2.THRESH_OTSU,
        "tozero": cv2.THRESH_TOZERO,
        "trunc": cv2.THRESH_TRUNC,
    }
    if mode == "adaptive":
        mask = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5
        )
    elif mode == "otsu":
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    else:
        flag = flags.get(mode, cv2.THRESH_BINARY)
        _, mask = cv2.threshold(gray, float(np.clip(value, 0, 255)), 255, flag)

    if color:
        keep = (mask > 0).astype(np.float32)[..., None]
        return from_rgb_array(arr * keep)
    return from_rgb_array(np.dstack([mask, mask, mask]))


def invert(img: Image.Image) -> Image.Image:
    """عكس الألوان (Negative)."""
    return from_rgb_array(255.0 - to_rgb_array(img))


def black_and_white(img: Image.Image, mix: Tuple[float, float, float] = (0.299, 0.587, 0.114)) -> Image.Image:
    """أبيض وأسود بخلط قنوات قابل للضبط (مثل Channel Mixer في Lightroom)."""
    arr = to_rgb_array(img)
    m = np.array(mix, dtype=np.float32)
    gray = (arr.reshape(-1, 3) @ m).reshape(arr.shape[:2])
    gray = np.clip(gray, 0, 255)
    return from_rgb_array(np.dstack([gray, gray, gray]))


def split_toning(img: Image.Image, shadow_hue: float, highlight_hue: float, balance: float = 0.0) -> Image.Image:
    """تلوين منفصل: لون للظلال وآخر للإضاءات مع توازن بينهما."""
    arr = unit(to_rgb_array(img))
    lum = luminance(arr * 255.0) / 255.0

    def tint(hue: float) -> np.ndarray:
        h = (float(hue) % 360.0) / 360.0
        import colorsys

        r, g, b = colorsys.hsv_to_rgb(h, 0.55, 1.0)
        return np.array([r, g, b], dtype=np.float32).reshape(1, 1, 3)

    sh, hi = tint(shadow_hue), tint(highlight_hue)
    w_hi = np.clip(lum + float(balance) * 0.25, 0, 1)[..., None]
    w_sh = 1.0 - w_hi
    tinted = arr * (sh * w_sh + hi * w_hi) * 1.25 + arr * 0.35
    return from_rgb_array(byte(tinted))


def selective_color(img: Image.Image, hue_center: float, hue_width: float, scale: float) -> Image.Image:
    """تعديل انتقائي: تكبير/تصغير تشبّع نطاق لوني محدد فقط."""
    arr = to_rgb_array(img).astype(np.uint8)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
    h = hsv[..., 0] * 2.0  # تحويل إلى درجات [0..360]
    center = float(hue_center) % 360.0
    diff = np.abs((h - center + 180.0) % 360.0 - 180.0)
    weight = np.clip(1.0 - diff / max(1.0, float(hue_width)), 0, 1)
    hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + float(scale) * weight), 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    return from_rgb_array(out)


# ==============================================================================
#  التطبيق الموحّد
# ==============================================================================
@dataclass
class PixelAdjustments:
    """كل معاملات ضبط البكسل بقيمها المحايدة (لا تأثير)."""

    exposure: float = 0.0
    white_balance: Optional[str] = None       # None | grayworld | whitepatch
    wb_strength: float = 1.0
    temperature: float = 0.0
    tint: float = 0.0
    brightness: float = 0.0
    contrast: float = 0.0
    levels: Optional[Dict[str, float]] = None
    gamma: float = 1.0
    curves: Optional[List[Tuple[float, float]]] = None
    curves_channel: str = "rgb"
    saturation: float = 0.0
    vibrance: float = 0.0
    hue: float = 0.0
    color_balance: Optional[Dict[str, Sequence[float]]] = None
    channel_mixer: Optional[List[List[float]]] = None
    posterize_levels: Optional[int] = None
    threshold_value: Optional[float] = None
    threshold_mode: str = "binary"
    invert: bool = False
    grayscale: bool = False
    auto_levels: bool = False
    auto_contrast: bool = False

    def is_identity(self) -> bool:
        """هل كل القيم محايدة؟ (لتخطّي المعالجة غير الضرورية)."""
        trivial = (
            self.exposure == 0 and self.temperature == 0 and self.tint == 0
            and self.brightness == 0 and self.contrast == 0 and self.levels is None
            and abs(self.gamma - 1.0) < 1e-3 and self.curves is None
            and self.saturation == 0 and self.vibrance == 0 and self.hue == 0
            and self.color_balance is None and self.channel_mixer is None
            and self.posterize_levels is None and self.threshold_value is None
            and not self.invert and not self.grayscale and not self.auto_levels
            and not self.auto_contrast and self.white_balance is None
        )
        return trivial


def apply_pixel_adjustments(img: Image.Image, adj: PixelAdjustments) -> Image.Image:
    """تطبيق سلسلة الضبوطات بالترتيب البصري الصحيح."""
    if adj.is_identity():
        return img

    out = img
    if adj.auto_levels:
        out = auto_levels(out)
    if adj.auto_contrast:
        out = auto_contrast(out)
    if adj.exposure:
        out = adjust_exposure(out, adj.exposure)
    if adj.white_balance:
        out = white_balance(out, adj.white_balance, adj.wb_strength)
    if adj.temperature:
        out = adjust_temperature(out, adj.temperature)
    if adj.tint:
        out = adjust_tint(out, adj.tint)
    if adj.brightness:
        out = adjust_brightness(out, adj.brightness)
    if adj.contrast:
        out = adjust_contrast(out, adj.contrast)
    if adj.levels:
        out = adjust_levels(
            out,
            adj.levels.get("in_black", 0.0),
            adj.levels.get("in_white", 1.0),
            adj.levels.get("gamma", 1.0),
            adj.levels.get("out_black", 0.0),
            adj.levels.get("out_white", 1.0),
        )
    if abs(adj.gamma - 1.0) > 1e-3:
        out = adjust_gamma(out, adj.gamma)
    if adj.curves:
        out = adjust_curves(out, adj.curves, adj.curves_channel)
    if adj.saturation:
        out = adjust_saturation(out, adj.saturation)
    if adj.vibrance:
        out = adjust_vibrance(out, adj.vibrance)
    if adj.hue:
        out = adjust_hue(out, adj.hue)
    if adj.color_balance:
        out = adjust_color_balance(
            out,
            tuple(adj.color_balance.get("shadows", (0, 0, 0))),
            tuple(adj.color_balance.get("midtones", (0, 0, 0))),
            tuple(adj.color_balance.get("highlights", (0, 0, 0))),
        )
    if adj.channel_mixer:
        out = apply_channel_mixer(out, adj.channel_mixer)
    if adj.grayscale:
        out = black_and_white(out)
    if adj.posterize_levels:
        out = posterize(out, adj.posterize_levels)
    if adj.threshold_value is not None:
        out = threshold(out, adj.threshold_value, adj.threshold_mode)
    if adj.invert:
        out = invert(out)
    return out


__all__ = [
    "PixelAdjustments", "adjust_brightness", "adjust_color_balance", "adjust_contrast",
    "adjust_curves", "adjust_exposure", "adjust_gamma", "adjust_hue", "adjust_levels",
    "adjust_saturation", "adjust_temperature", "adjust_tint", "adjust_vibrance",
    "apply_channel_mixer", "apply_pixel_adjustments", "auto_contrast", "auto_levels",
    "black_and_white", "invert", "posterize", "selective_color", "split_toning",
    "threshold", "white_balance",
]

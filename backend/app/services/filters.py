"""
الفلاتر: التنعيم، التحديد، تقليل الضوضاء، والفلاتر الفنية.
==========================================================
التنعيم (Blur)   : gaussian | box | motion | radial_zoom | radial_spin | surface | bilateral | nlmeans
التحديد (Sharpen): unsharp | highpass | laplacian | detail
الضوضاء          : denoise (NL-Means) | median | bilateral
الحواف/النحت     : edges (Canny) | sobel | emboss
فنية             : oil_paint | sketch | pencil_color | halftone | pixelate | mosaic
"""
from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from ..core.exceptions import InvalidParameterError
from ..core.helpers import bgr, from_rgb_array, odd, rgb, to_rgb_array, unit, byte

BLUR_MODES = (
    "gaussian", "box", "motion", "radial_zoom", "radial_spin",
    "surface", "bilateral", "nlmeans",
)
SHARPEN_MODES = ("unsharp", "highpass", "laplacian", "detail")


# ==============================================================================
#  التنعيم
# ==============================================================================
def _motion_kernel(size: int, angle: float) -> np.ndarray:
    """بناء نواة حركة خطية بزاوية معيّنة."""
    size = max(3, odd(size))
    kernel = np.zeros((size, size), np.float32)
    kernel[size // 2, :] = 1.0
    if angle:
        M = cv2.getRotationMatrix2D((size / 2 - 0.5, size / 2 - 0.5), float(angle), 1.0)
        kernel = cv2.warpAffine(kernel, M, (size, size))
    total = kernel.sum()
    return kernel / total if total > 0 else kernel


def _radial_blur(arr: np.ndarray, strength: float, mode: str, center: Tuple[float, float]) -> np.ndarray:
    """
    ضباب شعاعي: تكبير (Zoom) أو دوران (Spin) حول نقطة مركز.
    يُنفَّذ بمزج نسخ مُحوَّلة تدريجياً بدل الحلقات البطيئة.
    """
    h, w = arr.shape[:2]
    cx, cy = center[0] * w, center[1] * h
    steps = 12
    out = arr.astype(np.float32).copy()
    accum = arr.astype(np.float32).copy()

    for i in range(1, steps + 1):
        t = (i / steps) * float(strength)
        if mode == "radial_zoom":
            scale = 1.0 + t * 0.05
            M = cv2.getRotationMatrix2D((cx, cy), 0, scale)
        else:  # radial_spin
            M = cv2.getRotationMatrix2D((cx, cy), t * 6.0, 1.0)
        shifted = cv2.warpAffine(arr, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        accum += shifted
    out = accum / (steps + 1)
    return out


def blur(
    img: Image.Image,
    mode: str = "gaussian",
    radius: float = 3.0,
    angle: float = 0.0,
    strength: float = 1.0,
    center: Tuple[float, float] = (0.5, 0.5),
    color_preserve: bool = True,
) -> Image.Image:
    """تنعيم الصورة بأحد الأنماط المدعومة."""
    arr = to_rgb_array(img).astype(np.uint8)
    k = odd(int(max(1, radius) * 2 + 1))

    if mode == "gaussian":
        out = cv2.GaussianBlur(arr, (k, k), 0)
    elif mode == "box":
        out = cv2.blur(arr, (k, k))
    elif mode == "motion":
        out = cv2.filter2D(arr, -1, _motion_kernel(k, angle))
    elif mode in ("radial_zoom", "radial_spin"):
        out = _radial_blur(arr, strength, mode, center).astype(np.uint8)
    elif mode == "surface":
        # تنعيم الأسطح: يحافظ على الحواف (مناسب للبشرة)
        out = cv2.bilateralFilter(arr, d=max(5, k), sigmaColor=max(10.0, radius * 12), sigmaSpace=max(10.0, radius * 12))
    elif mode == "bilateral":
        out = cv2.bilateralFilter(arr, d=max(5, k), sigmaColor=60, sigmaSpace=60)
    elif mode == "nlmeans":
        out = cv2.fastNlMeansDenoisingColored(arr, None, h=float(max(1, radius)) * 3, hColor=float(max(1, radius)) * 3,
                                              templateWindowSize=7, searchWindowSize=21)
    else:
        raise InvalidParameterError(f"نمط التنعيم «{mode}» غير مدعوم.", detail={"supported": list(BLUR_MODES)})

    if not color_preserve:
        gray = cv2.cvtColor(out, cv2.COLOR_RGB2GRAY)
        out = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    return from_rgb_array(out)


def surface_smooth(img: Image.Image, strength: float = 1.0, detail: float = 0.5) -> Image.Image:
    """
    تنعيم بشرة/أسطح مع الحفاظ على التفاصيل:
    ناتج = أصل · detail + مرشّح ثنائي · (1-detail)
    """
    arr = to_rgb_array(img).astype(np.uint8)
    d = int(np.clip(5 + strength * 9, 5, 21))
    smooth = cv2.bilateralFilter(arr, d=d, sigmaColor=25 + strength * 45, sigmaSpace=25 + strength * 45)
    detail = float(np.clip(detail, 0, 1))
    out = arr.astype(np.float32) * detail + smooth.astype(np.float32) * (1 - detail)
    return from_rgb_array(out)


# ==============================================================================
#  التحديد
# ==============================================================================
def sharpen(
    img: Image.Image,
    mode: str = "unsharp",
    amount: float = 1.0,
    radius: float = 2.0,
    threshold: float = 0.0,
) -> Image.Image:
    """
    تحديد الصورة:
      • unsharp : قناع غير حاد مع عتبة لحماية المناطق الناعمة من الضوضاء.
      • highpass: طرح نسخة مُنعّمة بترددات منخفضة.
      • laplacian: إضافة نواة لابلاس الحادة.
      • detail   : نواة تفاصيل جاهزة.
    """
    arr = to_rgb_array(img).astype(np.float32)
    k = odd(int(max(1, radius) * 2 + 1))

    if mode == "unsharp":
        blurred = cv2.GaussianBlur(arr, (k, k), 0)
        diff = arr - blurred
        if threshold > 0:
            mask = (np.abs(diff).max(axis=2, keepdims=True) > float(threshold)).astype(np.float32)
            diff = diff * mask
        out = arr + diff * float(amount)
    elif mode == "highpass":
        blurred = cv2.GaussianBlur(arr, (k, k), 0)
        high = arr - blurred + 128.0
        out = arr + (high - 128.0) * float(amount)
    elif mode == "laplacian":
        lap = cv2.Laplacian(arr, cv2.CV_32F, ksize=3)
        out = arr - lap * float(amount)
    elif mode == "detail":
        kernel = np.array([[0, -1, 0], [-1, 5 + float(amount) * 3, -1], [0, -1, 0]], np.float32)
        out = cv2.filter2D(arr, -1, kernel)
    else:
        raise InvalidParameterError(f"نمط التحديد «{mode}» غير مدعوم.", detail={"supported": list(SHARPEN_MODES)})

    return from_rgb_array(out)


def denoise(img: Image.Image, strength: float = 1.0, mode: str = "nlmeans") -> Image.Image:
    """تقليل الضوضاء: nlmeans (الأفضل جودة) | median | bilateral."""
    arr = to_rgb_array(img).astype(np.uint8)
    s = float(np.clip(strength, 0.1, 5.0))
    if mode == "median":
        out = cv2.medianBlur(arr, odd(int(1 + s * 2)))
    elif mode == "bilateral":
        out = cv2.bilateralFilter(arr, d=9, sigmaColor=25 * s, sigmaSpace=25 * s)
    else:
        out = cv2.fastNlMeansDenoisingColored(arr, None, h=6 * s, hColor=6 * s,
                                              templateWindowSize=7, searchWindowSize=21)
    return from_rgb_array(out)


# ==============================================================================
#  الحواف والنحت
# ==============================================================================
def detect_edges(img: Image.Image, low: int = 50, high: int = 150, invert_colors: bool = True) -> Image.Image:
    """كشف الحواف بخوارزمية Canny."""
    arr = to_rgb_array(img).astype(np.uint8)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, int(low), int(high))
    if invert_colors:
        edges = 255 - edges
    return from_rgb_array(cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB))


def sobel_edges(img: Image.Image, scale: float = 1.0) -> Image.Image:
    """تدرّج سوبل (اتجاهي) — يُظهر اتجاه الحواف لا وجودها فقط."""
    arr = to_rgb_array(img).astype(np.uint8)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx ** 2 + gy ** 2) * float(scale)
    mag = np.clip(mag, 0, 255).astype(np.uint8)
    return from_rgb_array(cv2.cvtColor(mag, cv2.COLOR_GRAY2RGB))


def emboss(img: Image.Image, strength: float = 1.0) -> Image.Image:
    """تأثير النحت البارز (Emboss)."""
    kernel = np.array([[-2, -1, 0], [-1, 1, 1], [0, 1, 2]], np.float32) * float(strength)
    arr = to_rgb_array(img).astype(np.float32)
    out = cv2.filter2D(arr, -1, kernel) + 128.0
    return from_rgb_array(out)


# ==============================================================================
#  الفلاتر الفنية
# ==============================================================================
def oil_paint(img: Image.Image, radius: int = 4, intensity: int = 24) -> Image.Image:
    """
    تأثير الرسم الزيتي — خوارزمية «أدنى تباين محلي» (Minimum Local Variance):
    لكل بكسل تُقاس نوافذ مُزاحة بعدة اتجاهات، وتُؤخذ mean النافذة الأقل تبايناً.
    النتيجة حواف ملساء شبيهة بضربات الفرشاة مع الحفاظ على حدود الشكل.
    """
    arr = to_rgb_array(img).astype(np.uint8)
    k = max(3, odd(int(np.clip(radius, 1, 15)) * 2 + 1))
    offsets = [(0, 0), (k // 2, 0), (-k // 2, 0), (0, k // 2), (0, -k // 2)]

    f = arr.astype(np.float32)
    best_var = None
    best_mean = None
    for dx, dy in offsets:
        shifted = np.roll(np.roll(f, dy, axis=0), dx, axis=1)
        local_mean = cv2.blur(shifted, (k, k))
        local_sq = cv2.blur(shifted * shifted, (k, k))
        local_var = np.maximum(local_sq - local_mean ** 2, 0).sum(axis=2)
        if best_var is None:
            best_var, best_mean = local_var, local_mean
        else:
            better = local_var < best_var
            best_var = np.where(better, local_var, best_var)
            best_mean = np.where(better[..., None], local_mean, best_mean)

    out = np.clip(best_mean, 0, 255).astype(np.uint8)
    # تعزيز الطابع الزيتي بتنعيم ثنائي خفيف وزيادة تشبّع طفيفة
    out = cv2.bilateralFilter(out, 5, 40, 40)
    return from_rgb_array(out)


def sketch(img: Image.Image, threshold: float = 8.0, invert_colors: bool = False) -> Image.Image:
    """رسم بالقلم الرصاص (تدرّج رمادي) عبر دمج حواف مُنعّمة."""
    arr = to_rgb_array(img).astype(np.uint8)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    inv = 255 - gray
    inv_blur = cv2.GaussianBlur(inv, (21, 21), 0)
    blend = cv2.divide(gray, 255 - inv_blur, scale=256)
    out = cv2.normalize(blend, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    # عتبة لإبراز الخطوط الداكنة فقط (تحاكي ضغط القلم على الورق)
    _, out = cv2.threshold(out, float(np.clip(threshold, 0, 20)) * 6, 255, cv2.THRESH_TOZERO)
    if invert_colors:
        out = 255 - out
    return from_rgb_array(cv2.cvtColor(out, cv2.COLOR_GRAY2RGB))


def pencil_color(img: Image.Image, sigma: float = 60.0, shade: float = 0.02) -> Image.Image:
    """رسم ملوّن بالقلم الرصاص عبر مرشّح Pencil Sketch."""
    arr = to_rgb_array(img).astype(np.uint8)
    gray, color = cv2.pencilSketch(arr, sigma_s=60, sigma_r=float(np.clip(sigma, 0.01, 1.0)), shade_factor=float(shade))
    return from_rgb_array(color)


def halftone(img: Image.Image, dot_size: int = 6, angle: float = 45.0, color: bool = False) -> Image.Image:
    """تأثير Halb tone (نقاط طباعة الصحف)."""
    arr = to_rgb_array(img).astype(np.uint8)
    dot_size = int(np.clip(dot_size, 2, 40))

    def channel_halftone(ch: np.ndarray) -> np.ndarray:
        small = cv2.resize(ch, (max(1, ch.shape[1] // dot_size), max(1, ch.shape[0] // dot_size)),
                           interpolation=cv2.INTER_AREA)
        up = cv2.resize(small, (ch.shape[1], ch.shape[0]), interpolation=cv2.INTER_NEAREST)
        yy, xx = np.mgrid[0:ch.shape[0], 0:ch.shape[1]].astype(np.float32)
        rad = np.sqrt(((xx % dot_size) - dot_size / 2) ** 2 + ((yy % dot_size) - dot_size / 2) ** 2)
        threshold = (255.0 - up) / 255.0 * (dot_size / 1.6)
        return np.where(rad < threshold, 0, 255).astype(np.uint8)

    if color:
        out = np.dstack([channel_halftone(arr[..., i]) for i in range(3)])
    else:
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        h = channel_halftone(gray)
        out = cv2.cvtColor(h, cv2.COLOR_GRAY2RGB)
    return from_rgb_array(out)


def pixelate(img: Image.Image, block: int = 12) -> Image.Image:
    """تأثير الفسيفساء/البكسلة (Pixelate)."""
    arr = to_rgb_array(img).astype(np.uint8)
    block = int(np.clip(block, 2, 200))
    h, w = arr.shape[:2]
    small = cv2.resize(arr, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA)
    out = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    return from_rgb_array(out)


def vignette(img: Image.Image, strength: float = 0.6, radius: float = 0.75) -> Image.Image:
    """تظليل الحواف (Vignette)."""
    arr = to_rgb_array(img)
    h, w = arr.shape[:2]
    y, x = np.ogrid[:h, :w]
    cx, cy = w / 2, h / 2
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (np.sqrt(cx ** 2 + cy ** 2) + 1e-6)
    mask = 1.0 - float(np.clip(strength, 0, 1)) * np.clip((dist - float(radius)) / (1 - float(radius) + 1e-6), 0, 1) ** 1.6
    return from_rgb_array(arr * mask[..., None])


def grain(img: Image.Image, amount: float = 0.25, seed: int = 7) -> Image.Image:
    """حبوب فيلم (Film Grain)."""
    arr = to_rgb_array(img)
    rng = np.random.default_rng(int(seed))
    noise = rng.normal(0.0, 255.0 * float(np.clip(amount, 0, 1)) * 0.25, arr.shape[:2])
    return from_rgb_array(arr + noise[..., None])


def glow(img: Image.Image, amount: float = 0.5, radius: float = 12.0) -> Image.Image:
    """توهّج ناعم (Soft Glow) بدمج شاشة مع نسخة مُنعّمة."""
    arr = to_rgb_array(img).astype(np.float32)
    k = odd(int(radius) * 2 + 1)
    blurred = cv2.GaussianBlur(arr, (k, k), 0)
    screen = 255.0 - ((255.0 - arr) * (255.0 - blurred)) / 255.0
    a = float(np.clip(amount, 0, 1))
    return from_rgb_array(arr * (1 - a) + screen * a)


def hdr_look(img: Image.Image, strength: float = 0.6) -> Image.Image:
    """مظهر HDR محلي عبر تعزيز التباين المحلي (Local Laplacian-like)."""
    arr = to_rgb_array(img).astype(np.float32)
    base = cv2.bilateralFilter(arr.astype(np.uint8), 9, 80, 80).astype(np.float32)
    detail = arr - base
    out = base + detail * (1.0 + float(strength) * 2.0)
    return from_rgb_array(out)


def apply_filter(img: Image.Image, name: str, **params) -> Image.Image:
    """موجّه موحّد لتطبيق فلتر بالاسم."""
    table = {
        "blur": blur, "surface_smooth": surface_smooth, "sharpen": sharpen,
        "denoise": denoise, "edges": detect_edges, "sobel": sobel_edges,
        "emboss": emboss, "oil_paint": oil_paint, "sketch": sketch,
        "pencil_color": pencil_color, "halftone": halftone, "pixelate": pixelate,
        "vignette": vignette, "grain": grain, "glow": glow, "hdr_look": hdr_look,
    }
    if name not in table:
        raise InvalidParameterError(f"الفلتر «{name}» غير معروف.", detail={"supported": sorted(table)})
    return table[name](img, **params)


FILTER_CATALOG = {
    "blur": {"modes": list(BLUR_MODES), "params": {"radius": [0.1, 30]}},
    "sharpen": {"modes": list(SHARPEN_MODES), "params": {"amount": [0, 3], "radius": [0.1, 10]}},
    "denoise": {"modes": ["nlmeans", "median", "bilateral"], "params": {"strength": [0.1, 5]}},
    "edges": {"modes": ["canny"], "params": {"low": [0, 255], "high": [0, 255]}},
    "sobel": {"modes": ["sobel"], "params": {"scale": [0.1, 5]}},
    "emboss": {"modes": ["emboss"], "params": {"strength": [0.1, 3]}},
    "oil_paint": {"modes": ["oil"], "params": {"radius": [1, 12], "intensity": [1, 40]}},
    "sketch": {"modes": ["gray"], "params": {"threshold": [0, 20]}},
    "pencil_color": {"modes": ["color"], "params": {"sigma": [0.01, 1], "shade": [0, 0.1]}},
    "halftone": {"modes": ["mono", "color"], "params": {"dot_size": [2, 40]}},
    "pixelate": {"modes": ["mosaic"], "params": {"block": [2, 200]}},
    "vignette": {"modes": ["dark"], "params": {"strength": [0, 1], "radius": [0, 1]}},
    "grain": {"modes": ["film"], "params": {"amount": [0, 1]}},
    "glow": {"modes": ["soft"], "params": {"amount": [0, 1], "radius": [0.1, 40]}},
    "hdr_look": {"modes": ["local"], "params": {"strength": [0, 2]}},
    "surface_smooth": {"modes": ["skin"], "params": {"strength": [0, 2], "detail": [0, 1]}},
}


__all__ = [
    "BLUR_MODES", "FILTER_CATALOG", "SHARPEN_MODES", "apply_filter", "blur",
    "denoise", "detect_edges", "emboss", "glow", "grain", "halftone", "hdr_look",
    "oil_paint", "pencil_color", "pixelate", "sharpen", "sketch", "sob el_edges",
    "surface_smooth", "vignette",
]

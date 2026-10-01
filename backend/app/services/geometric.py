"""
العمليات الهندسية: قص، تحجيم، دوران، قلب، إمالة، إطار، ظل، توسيع.
================================================================
كل دالة تحافظ على قناة الشفافية إن وُجدت، وتعيد PIL.Image.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..core.exceptions import InvalidParameterError
from ..core.helpers import (
    clamp_size,
    fit_size,
    from_rgba_array,
    parse_color,
    to_rgba_array,
    validate_choice,
)
from ..core.settings import settings as app_settings

RESAMPLE_MODES = {
    "lanczos": Image.LANCZOS,      # الأعلى جودة للتصغير
    "bicubic": Image.BICUBIC,      # متوازن
    "bilinear": Image.BILINEAR,    # سريع
    "nearest": Image.NEAREST,      # للبكسلة الفنية
    "box": Image.BOX,              # تصغير بنسب صحيحة
}

ASPECT_PRESETS = {
    "free": None,
    "1:1": 1.0,
    "4:3": 4 / 3,
    "3:2": 3 / 2,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "3:4": 3 / 4,
    "2:3": 2 / 3,
    "21:9": 21 / 9,
    "5:4": 5 / 4,
}


# ==============================================================================
#  القصّ
# ==============================================================================
def crop(img: Image.Image, box: Sequence[float], unit: str = "px") -> Image.Image:
    """
    قصّ منطقة. `box` = (x, y, w, h) بالبكسل أو بنسب [0..1] عند unit="ratio".
    تُقصّ الإحداثيات تلقائياً داخل حدود الصورة.
    """
    w, h = img.size
    if len(box) != 4:
        raise InvalidParameterError("box يجب أن تحتوي 4 قيم (x, y, w, h).")
    x, y, bw, bh = (float(v) for v in box)
    if bw <= 0 or bh <= 0:
        raise InvalidParameterError(
            f"منطقة القصّ فارغة: العرض والارتفاع يجب أن يكونا أكبر من صفر (المُعطى: {bw}×{bh})."
        )
    if unit == "ratio":
        x, y, bw, bh = x * w, y * h, bw * w, bh * h
    x0 = int(max(0, min(w - 1, round(x))))
    y0 = int(max(0, min(h - 1, round(y))))
    x1 = int(max(x0 + 1, min(w, round(x + bw))))
    y1 = int(max(y0 + 1, min(h, round(y + bh))))
    if x1 - x0 < 1 or y1 - y0 < 1:
        raise InvalidParameterError("منطقة القصّ فارغة أو خارج حدود الصورة.")
    return img.crop((x0, y0, x1, y1))


def crop_auto(img: Image.Image, tolerance: int = 12, padding: int = 0) -> Image.Image:
    """قصّ تلقائي للحواف المتجانسة (مثل Trim في Photoshop)."""
    arr = to_rgba_array(img)
    rgb = arr[..., :3]
    ref = rgb[0, 0]
    diff = np.abs(rgb - ref).max(axis=2)
    mask = diff > int(tolerance)
    if not mask.any():
        return img
    ys, xs = np.where(mask)
    x0 = max(0, int(xs.min()) - padding)
    y0 = max(0, int(ys.min()) - padding)
    x1 = min(img.width, int(xs.max()) + padding + 1)
    y1 = min(img.height, int(ys.max()) + padding + 1)
    return img.crop((x0, y0, x1, y1))


def crop_to_content(img: Image.Image, padding: int = 0) -> Image.Image:
    """قصّ إلى حدود المحتوى غير الشفاف (للصور ذات الشفافية)."""
    arr = to_rgba_array(img)
    alpha = arr[..., 3]
    ys, xs = np.where(alpha > 8)
    if len(xs) == 0:
        return img
    x0 = max(0, int(xs.min()) - padding)
    y0 = max(0, int(ys.min()) - padding)
    x1 = min(img.width, int(xs.max()) + padding + 1)
    y1 = min(img.height, int(ys.max()) + padding + 1)
    return img.crop((x0, y0, x1, y1))


def crop_aspect(img: Image.Image, aspect: str = "1:1", anchor: str = "center") -> Image.Image:
    """قصّ إلى نسبة أبعاد معيّنة مع اختيار نقطة الارتكاز."""
    ratio = ASPECT_PRESETS.get(aspect)
    if ratio is None:
        raise InvalidParameterError(f"نسبة الأبعاد «{aspect}» غير مدعومة.",
                                    detail={"supported": list(ASPECT_PRESETS)})
    w, h = img.size
    target_w, target_h = w, int(round(w / ratio))
    if target_h > h:
        target_h = h
        target_w = int(round(h * ratio))

    anchors = {
        "center": ((w - target_w) / 2, (h - target_h) / 2),
        "top": ((w - target_w) / 2, 0),
        "bottom": ((w - target_w) / 2, h - target_h),
        "left": (0, (h - target_h) / 2),
        "right": (w - target_w, (h - target_h) / 2),
        "top-left": (0, 0),
        "top-right": (w - target_w, 0),
        "bottom-left": (0, h - target_h),
        "bottom-right": (w - target_w, h - target_h),
    }
    x, y = anchors.get(anchor, anchors["center"])
    return img.crop((int(x), int(y), int(x + target_w), int(y + target_h)))


# ==============================================================================
#  التحجيم
# ==============================================================================
def resize(
    img: Image.Image,
    width: Optional[int] = None,
    height: Optional[int] = None,
    percent: Optional[float] = None,
    mode: str = "fit",
    resample: str = "lanczos",
    allow_upscale: bool = True,
) -> Image.Image:
    """
    تغيير الحجم:
      • percent : نسبة مئوية من المقاس الحالي.
      • width/height مع mode:
          fit    — يناسب الصندوق مع الحفاظ على النسبة (الافتراضي).
          fill   — يملأ الصندوق (قد يقصّ).
          exact  — أبعاد دقيقة (يشوّه النسبة).
          longest— يضبط أطول ضلع.
    """
    w, h = img.size
    flag = RESAMPLE_MODES.get(resample, Image.LANCZOS)

    if percent is not None:
        p = float(percent) / 100.0
        if p <= 0:
            raise InvalidParameterError("النسبة المئوية يجب أن تكون أكبر من صفر.")
        nw, nh = max(1, int(round(w * p))), max(1, int(round(h * p)))
    elif mode == "exact":
        nw = int(width or w)
        nh = int(height or h)
    elif mode == "longest":
        side = int(width or height or max(w, h))
        scale = side / max(w, h)
        nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    else:
        nw, nh = fit_size(w, h, int(width or 0) or None, int(height or 0) or None)
        if mode == "fill":
            # ملء الصندوق ثم قصّ الزائد من المنتصف
            scale = max((width or 0) / w, (height or 0) / h) if (width and height) else 1.0
            tw, th = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
            resized = img.resize((tw, th), flag)
            x = max(0, (tw - int(width)) // 2)
            y = max(0, (th - int(height)) // 2)
            return resized.crop((x, y, x + int(width), y + int(height)))

    if not allow_upscale:
        nw, nh = min(nw, w), min(nh, h)

    nw, nh = clamp_size(nw, nh, app_settings.MAX_OUTPUT_SIDE)
    if nw < 1 or nh < 1:
        raise InvalidParameterError("المقاس المطلوب صغير جداً.")
    return img.resize((nw, nh), flag)


def rescale_for_web(img: Image.Image, max_side: int = 1600) -> Image.Image:
    """تصغير للصيغة الويب دون تكبير."""
    return resize(img, width=max_side, height=max_side, mode="fit", allow_upscale=False)


# ==============================================================================
#  الدوران والقلب
# ==============================================================================
def rotate(
    img: Image.Image,
    angle: float,
    expand: bool = True,
    fill: str = "#ffffff",
    fill_transparent: bool = True,
    resample: str = "bicubic",
) -> Image.Image:
    """دوران بزاوية حرة (موجب = عكس عقارب الساعة كما في Pillow)."""
    flag = RESAMPLE_MODES.get(resample, Image.BICUBIC)
    has_alpha = img.mode in ("RGBA", "LA", "PA")
    work = img.convert("RGBA") if (has_alpha or fill_transparent) else img

    if fill_transparent:
        fillcolor = (0, 0, 0, 0)
    else:
        c = parse_color(fill)
        fillcolor = c + (255,) if work.mode == "RGBA" else c

    out = work.rotate(float(angle), resample=flag, expand=bool(expand), fillcolor=fillcolor)
    if img.mode not in ("RGBA", "LA", "PA") and not fill_transparent:
        out = out.convert("RGB")
    return out


def rotate90(img: Image.Image, times: int = 1) -> Image.Image:
    """دوران بمضاعفات 90° (بلا فقد جودة)."""
    from PIL import Image as _I

    mapping = {1: _I.ROTATE_90, 2: _I.ROTATE_180, 3: _I.ROTATE_270}
    times = int(times) % 4
    if times == 0:
        return img
    return img.transpose(mapping[times])


def flip(img: Image.Image, direction: str = "horizontal") -> Image.Image:
    """قلب أفقي أو رأسي."""
    from PIL import Image as _I

    direction = validate_choice("direction", direction, ("horizontal", "vertical"))
    return img.transpose(_I.FLIP_LEFT_RIGHT if direction == "horizontal" else _I.FLIP_TOP_BOTTOM)


def transpose(img: Image.Image, mode: str = "transpose") -> Image.Image:
    """تبديل/تدوير مصفوفي: transpose | transverse | rotate_90 | rotate_180 | rotate_270."""
    from PIL import Image as _I

    table = {
        "transpose": _I.TRANSPOSE,
        "transverse": _I.TRANSVERSE,
        "rotate_90": _I.ROTATE_90,
        "rotate_180": _I.ROTATE_180,
        "rotate_270": _I.ROTATE_270,
    }
    validate_choice("mode", mode, table)
    return img.transpose(table[mode])


def straighten(img: Image.Image, angle: float) -> Image.Image:
    """تعديل ميل الصورة (موجب = تصحيح ميل باتجاه عقارب الساعة)."""
    return rotate(img, -float(angle), expand=True, fill_transparent=True)


# ==============================================================================
#  الإمالة المنظورية (Perspective)
# ==============================================================================
def perspective(
    img: Image.Image,
    src: Optional[Sequence[Sequence[float]]] = None,
    dst: Optional[Sequence[Sequence[float]]] = None,
    coeffs: Optional[Sequence[float]] = None,
    size: Optional[Tuple[int, int]] = None,
) -> Image.Image:
    """
    تحويل منظوري بأربع نقاط (تصحيح الصور المائلة/المسح الضوئي).
    النقاط بنسب [0..1] من أبعاد الصورة.
    """
    w, h = img.size
    if coeffs is None:
        if not src or not dst or len(src) != 4 or len(dst) != 4:
            raise InvalidParameterError("التحويل المنظوري يتطلب 4 نقاط مصدر و4 نقاط هدف.")
        s = np.array([[float(x) * w, float(y) * h] for x, y in src], np.float32)
        d = np.array([[float(x) * w, float(y) * h] for x, y in dst], np.float32)
        M = cv2.getPerspectiveTransform(s, d)
        coeffs = tuple(M.flatten().tolist())

    out_size = size or (w, h)
    return img.transform(
        (int(out_size[0]), int(out_size[1])),
        Image.PERSPECTIVE,
        coeffs,
        resample=Image.BICUBIC,
    )


def deskew_auto(img: Image.Image) -> Tuple[Image.Image, float]:
    """
    اكتشاف ميل المستند تلقائياً (تحويل Hough على الحواف) وتصحيحه.
    يُرجع (الصورة المُصحّحة، الزاوية المكتشفة).
    """
    arr = np.array(img.convert("L"))
    edges = cv2.Canny(arr, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=arr.shape[1] // 4, maxLineGap=10)
    if lines is None or len(lines) == 0:
        return img, 0.0
    angles: List[float] = []
    for x1, y1, x2, y2 in lines[:, 0]:
        ang = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(ang) < 45:      # الأسطر الأفقية فقط
            angles.append(ang)
    if not angles:
        return img, 0.0
    angle = float(np.median(angles))
    if abs(angle) < 0.1:
        return img, angle
    return straighten(img, angle), angle


# ==============================================================================
#  اللوحة والإطار والظل
# ==============================================================================
def pad(
    img: Image.Image,
    top: int = 0, right: int = 0, bottom: int = 0, left: int = 0,
    color: str = "#ffffff", transparent: bool = False,
) -> Image.Image:
    """توسيع اللوحة (Canvas) بحواف ملوّنة أو شفافة."""
    w, h = img.size
    nw, nh = w + int(left) + int(right), h + int(top) + int(bottom)
    if nw <= w or nh <= h:
        raise InvalidParameterError("قيم التوسيع يجب أن تكون موجبة.")
    canvas = Image.new("RGBA" if transparent else "RGB", (nw, nh),
                       (0, 0, 0, 0) if transparent else parse_color(color))
    canvas.paste(img.convert("RGBA" if transparent else "RGB"), (int(left), int(top)),
                 img.convert("RGBA") if transparent else None)
    return canvas


def pad_percent(img: Image.Image, percent: float = 5.0, color: str = "#ffffff", transparent: bool = False) -> Image.Image:
    """توسيع اللوحة بنسبة مئوية من الأبعاد."""
    p = max(0.0, float(percent)) / 100.0
    dx, dy = int(img.width * p), int(img.height * p)
    if dx == 0 and dy == 0:
        return img
    return pad(img, dy, dx, dy, dx, color=color, transparent=transparent)


def add_border(
    img: Image.Image,
    width: int = 10,
    color: str = "#000000",
    style: str = "solid",
    inner_gap: int = 0,
) -> Image.Image:
    """إطار: solid | double | shadow | polaroid | rounded."""
    width = int(max(1, width))
    base = img.convert("RGBA")
    w, h = base.size

    if style == "rounded":
        radius = min(w, h) // 8
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.paste(base, (0, 0), mask)
        return out

    if style == "polaroid":
        gap = int(width * 0.5)
        bottom = int(width * 4)
        canvas = Image.new("RGBA", (w + gap * 2, h + gap + bottom), (255, 255, 255, 255))
        canvas.paste(base, (gap, gap), base)
        return canvas

    if style == "shadow":
        shadow_offset = width
        canvas = Image.new("RGBA", (w + width * 3, h + width * 3), (0, 0, 0, 0))
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rectangle([0, 0, w - 1, h - 1], fill=(0, 0, 0, 120))
        shadow = shadow.filter(ImageFilter.GaussianBlur(width / 2))
        canvas.paste(shadow, (width + shadow_offset, width + shadow_offset), shadow)
        canvas.paste(base, (width, width), base)
        return canvas

    total = width + int(inner_gap)
    canvas = Image.new("RGBA", (w + total * 2, h + total * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, canvas.width - 1, canvas.height - 1], fill=parse_color(color) + (255,))
    if style == "double":
        mid = width // 2
        draw.rectangle([mid, mid, canvas.width - mid - 1, canvas.height - mid - 1],
                       outline=(255, 255, 255, 255), width=max(1, width // 5))
    if int(inner_gap) > 0:
        draw.rectangle([width, width, width + w + int(inner_gap) * 2 - 1, width + h + int(inner_gap) * 2 - 1],
                       fill=(255, 255, 255, 255))
    canvas.paste(base, (total, total), base)
    return canvas


def add_shadow(
    img: Image.Image,
    opacity: float = 0.5,
    blur_radius: float = 12.0,
    offset: Tuple[int, int] = (8, 12),
    color: str = "#000000",
) -> Image.Image:
    """ظل سقوط خلف المحتوى الشفاف (لصور المنتجات بعد إزالة الخلفية)."""
    base = img.convert("RGBA")
    w, h = base.size
    margin = int(max(blur_radius * 2, 20))
    canvas = Image.new("RGBA", (w + margin * 2, h + margin * 2), (0, 0, 0, 0))

    alpha = base.split()[-1]
    shadow = Image.new("RGBA", (w, h), parse_color(color) + (int(255 * float(np.clip(opacity, 0, 1))),))
    shadow.putalpha(alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(float(blur_radius)))
    canvas.paste(shadow, (margin + int(offset[0]), margin + int(offset[1])), shadow)
    canvas.paste(base, (margin, margin), base)
    return canvas


def fit_to_canvas(
    img: Image.Image,
    width: int,
    height: int,
    mode: str = "contain",
    background: str = "#ffffff",
    transparent: bool = False,
    position: str = "center",
) -> Image.Image:
    """
    ملاءمة الصورة داخل لوحة بمقاس محدد:
      contain — تظهر كاملة (مع حواف).  cover — تملأ اللوحة (مع قصّ).
      stretch — تمدّد لتشغل اللوحة.
    """
    w, h = img.size
    width, height = int(width), int(height)
    bg = (0, 0, 0, 0) if transparent else parse_color(background) + (255,)
    canvas = Image.new("RGBA", (width, height), bg)

    if mode == "stretch":
        fitted = img.convert("RGBA").resize((width, height), Image.LANCZOS)
        canvas.paste(fitted, (0, 0), fitted)
        return canvas

    scale = min(width / w, height / h) if mode == "contain" else max(width / w, height / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    fitted = img.convert("RGBA").resize((nw, nh), Image.LANCZOS)

    positions = {
        "center": ((width - nw) // 2, (height - nh) // 2),
        "top": ((width - nw) // 2, 0),
        "bottom": ((width - nw) // 2, height - nh),
        "left": (0, (height - nh) // 2),
        "right": (width - nw, (height - nh) // 2),
    }
    x, y = positions.get(position, positions["center"])
    canvas.paste(fitted, (x, y), fitted)
    return canvas


__all__ = [
    "ASPECT_PRESETS", "RESAMPLE_MODES", "add_border", "add_shadow", "crop",
    "crop_aspect", "crop_auto", "crop_to_content", "deskew_auto", "fit_to_canvas",
    "flip", "pad", "pad_percent", "perspective", "rescale_for_web", "resize",
    "rotate", "rotate90", "straighten", "transpose",
]

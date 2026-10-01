"""
مؤثرات إبداعية إضافية (الميزات الإبداعية في المشروع).
=====================================================
كل مؤثر خوارزمي بحت — بلا نماذج ذكاء اصطناعي وبلا موارد خارجية.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..core.exceptions import InvalidParameterError
from ..core.helpers import from_rgb_array, parse_color, to_rgb_array, unit, byte


def glitch(img: Image.Image, amount: float = 0.6, seed: int = 11, slices: int = 14) -> Image.Image:
    """
    تأثير الخلل الرقمي (Glitch): إزاحة قنوات RGB + تقطيع أفقي + خطوط مسح.
    """
    arr = to_rgb_array(img).astype(np.uint8)
    h, w = arr.shape[:2]
    rng = np.random.default_rng(int(seed))
    amount = float(np.clip(amount, 0, 2))
    shift = int(amount * w * 0.03)

    out = arr.copy()
    if shift > 0:
        out[..., 0] = np.roll(arr[..., 0], shift, axis=1)
        out[..., 2] = np.roll(arr[..., 2], -shift, axis=1)

    # تقطيع أفقي مُزاح
    for _ in range(int(slices * amount)):
        y = int(rng.integers(0, h))
        bh = int(rng.integers(2, max(3, h // 24)))
        dx = int(rng.integers(-int(w * 0.08), int(w * 0.08)))
        if bh <= 0:
            continue
        y2 = min(h, y + bh)
        out[y:y2] = np.roll(out[y:y2], dx, axis=1)

    # خطوط مسح (Scanlines)
    lines = np.ones((h, 1, 1), np.float32)
    lines[::3] = 0.94
    out = np.clip(out.astype(np.float32) * lines, 0, 255).astype(np.uint8)
    return from_rgb_array(out)


def duotone(img: Image.Image, dark: str = "#1a1a40", light: str = "#ffd166") -> Image.Image:
    """ثنائي اللون: تظليل الإضاءة بلون والظلال بلون آخر عبر الإضاءة."""
    from ..core.helpers import luminance

    arr = to_rgb_array(img)
    lum = luminance(arr) / 255.0
    d = np.array(parse_color(dark), np.float32).reshape(1, 1, 3)
    l = np.array(parse_color(light), np.float32).reshape(1, 1, 3)
    out = d * (1 - lum[..., None]) + l * lum[..., None]
    return from_rgb_array(out)


def vintage(img: Image.Image, strength: float = 1.0) -> Image.Image:
    """مظهر قديم: بهتان + صبغة دافئة + حبيبات + تظليل حواف."""
    arr = unit(to_rgb_array(img))
    s = float(np.clip(strength, 0, 2))

    # بهتان (رفع الأسود)
    arr = arr * (1 - 0.12 * s) + 0.06 * s
    # صبغة دافئة
    warm = np.array([1.06, 1.0, 0.88], np.float32).reshape(1, 1, 3)
    arr = arr * (1 + (warm - 1) * s)
    # تقليل تشبّع طفيف
    gray = arr.mean(axis=2, keepdims=True)
    arr = arr * (1 - 0.18 * s) + gray * 0.18 * s

    out = byte(arr)
    h, w = out.shape[:2]
    rng = np.random.default_rng(3)
    out += (rng.normal(0, 6 * s, (h, w, 1))).astype(np.float32)
    # تظليل حواف
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((x / w - 0.5) / 0.62) ** 2 + ((y / h - 0.5) / 0.62) ** 2)
    out *= (1 - 0.32 * s * np.clip(d - 0.55, 0, 1) ** 1.4)[..., None]
    return from_rgb_array(out)


def cinematic(img: Image.Image, strength: float = 1.0, teal_orange: bool = True) -> Image.Image:
    """
    مظهر سينمائي: منحنى S على الإضاءة + تلوين الظلال/Eضاءات (Teal & Orange).
    """
    from ..core.helpers import luminance

    arr = unit(to_rgb_array(img))
    s = float(np.clip(strength, 0, 2))

    # منحنى S (تباين سينمائي)
    x = np.linspace(0, 1, 256, dtype=np.float32)
    s_curve = 1 / (1 + np.exp(-(x - 0.5) * 8))
    s_curve = (s_curve - s_curve[0]) / (s_curve[-1] - s_curve[0])
    lut = np.clip(x * (1 - s * 0.55) + np.interp(x, x, s_curve) * s * 0.55, 0, 1)
    arr = np.interp(arr, x, lut).astype(np.float32)

    if teal_orange:
        lum = arr.mean(axis=2, keepdims=True)
        teal = np.array([0.05, 0.16, 0.20], np.float32).reshape(1, 1, 3)
        orange = np.array([0.20, 0.11, 0.0], np.float32).reshape(1, 1, 3)
        arr = arr + (teal * (1 - lum) + orange * lum) * 0.55 * s

    # أشرطة سوداء سينمائية اختيارية تُترك للواجهة (لا نغيّر الأبعاد هنا)
    return from_rgb_array(byte(arr))


def light_leak(img: Image.Image, hue: float = 24.0, amount: float = 0.5, corner: str = "right") -> Image.Image:
    """تسريب ضوء (Light Leak) من زاوية الصورة."""
    arr = to_rgb_array(img).astype(np.float32)
    h, w = arr.shape[:2]
    import colorsys

    r, g, b = colorsys.hsv_to_rgb((float(hue) % 360) / 360.0, 0.75, 1.0)
    color = np.array([r, g, b], np.float32).reshape(1, 1, 3) * 255.0

    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    if corner == "left":
        d = x / w
    elif corner == "top":
        d = y / h
    elif corner == "bottom":
        d = 1 - y / h
    else:
        d = 1 - x / w
    mask = np.clip(1 - d * 2.2, 0, 1) ** 1.7

    leak = mask[..., None] * float(np.clip(amount, 0, 1))
    out = arr * (1 - leak * 0.55) + color * leak * 0.75
    return from_rgb_array(out)


def frame_borders(img: Image.Image, style: str = "cinema", ratio: float = 0.06) -> Image.Image:
    """أشرطة/إطارات جاهزة: cinema (2.35:1) | square | thin | thick | instant."""
    base = img.convert("RGBA")
    w, h = base.size
    r = float(np.clip(ratio, 0.01, 0.3))

    if style == "cinema":
        bar = int(h * 0.13)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        canvas.paste(base, (0, 0), base)
        ImageDraw.Draw(canvas).rectangle([0, 0, w, bar], fill=(0, 0, 0, 255))
        ImageDraw.Draw(canvas).rectangle([0, h - bar, w, h], fill=(0, 0, 0, 255))
        return canvas
    if style == "thin":
        t = int(min(w, h) * 0.02)
    elif style == "thick":
        t = int(min(w, h) * 0.10)
    elif style == "instant":
        t = int(min(w, h) * 0.07)
    else:  # square
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
        canvas.paste(base, ((side - w) // 2, (side - h) // 2), base)
        return canvas

    canvas = Image.new("RGBA", (w + t * 2, h + t * 2), (255, 255, 255, 255) if style != "instant" else (245, 245, 245, 255))
    canvas.paste(base, (t, t), base)
    return canvas


def lens_blur(img: Image.Image, focus: Tuple[float, float] = (0.5, 0.5), radius: float = 14.0, falloff: float = 0.35) -> Image.Image:
    """
    عمق ميدان مصطنع: منطقة تركيز دائرية حادة وضباب يزداد بالابتعاد عنها.
    """
    arr = to_rgb_array(img).astype(np.uint8)
    h, w = arr.shape[:2]
    blurred = cv2.GaussianBlur(arr, (0, 0), max(1.0, float(radius)))

    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = float(focus[0]) * w, float(focus[1]) * h
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (max(w, h) * 0.5)
    weight = np.clip((dist - float(falloff)) / (1 - float(falloff) + 1e-6), 0, 1) ** 1.4

    out = arr.astype(np.float32) * (1 - weight[..., None]) + blurred.astype(np.float32) * weight[..., None]
    return from_rgb_array(out)


def bokeh_overlay(img: Image.Image, count: int = 26, amount: float = 0.35, hue: Optional[float] = None, seed: int = 5) -> Image.Image:
    """طبقة بوكيه مضيئة فوق الصورة."""
    arr = to_rgb_array(img).astype(np.float32)
    h, w = arr.shape[:2]
    rng = np.random.default_rng(int(seed))
    import colorsys

    for _ in range(int(np.clip(count, 1, 120))):
        cx, cy = float(rng.uniform(0, w)), float(float(rng.uniform(0, h)))
        r = float(rng.uniform(min(w, h) * 0.02, min(w, h) * 0.11))
        hh = float(hue) / 360.0 if hue is not None else float(rng.uniform(0, 1))
        rr, gg, bb = colorsys.hsv_to_rgb(hh, 0.45, 1.0)
        color = np.array([rr, gg, bb], np.float32).reshape(1, 1, 3) * 255.0
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        mask = (np.clip(1 - dist / r, 0, 1) ** 1.2 + np.clip(1 - np.abs(dist / r - 0.8) / 0.2, 0, 1) * 0.5)
        mask = (mask * float(np.clip(amount, 0, 1)) * 0.5)[..., None]
        arr = arr * (1 - mask) + color * mask
    return from_rgb_array(arr)


def mirror(img: Image.Image, axis: str = "vertical") -> Image.Image:
    """انعكاس مرآتي (يُنشئ تناظراً فنياً)."""
    base = img.convert("RGBA")
    if axis == "vertical":
        left = base.crop((0, 0, base.width // 2, base.height))
        right = left.transpose(Image.FLIP_LEFT_RIGHT)
        canvas = Image.new("RGBA", (left.width * 2, base.height))
    else:
        left = base.crop((0, 0, base.width, base.height // 2))
        right = left.transpose(Image.FLIP_TOP_BOTTOM)
        canvas = Image.new("RGBA", (base.width, left.height * 2))
    canvas.paste(left, (0, 0), left)
    canvas.paste(right, (left.width if axis == "vertical" else 0, 0 if axis == "vertical" else left.height), right)
    return canvas


def kaleidoscope(img: Image.Image, segments: int = 6) -> Image.Image:
    """مشكال (Kaleidoscope) بعدد قطاعات قابل للضبط."""
    base = img.convert("RGBA")
    w, h = base.size
    size = min(w, h)
    cx, cy = w // 2, h // 2
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    segments = int(np.clip(segments, 2, 16))
    angle_step = 360.0 / segments

    wedge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    wedge.paste(base, ((size - w) // 2, (size - h) // 2), base)
    mask = Image.new("L", (size, size), 0)
    half = angle_step / 2
    import math

    r = size
    p1 = (size / 2 + math.cos(math.radians(-half)) * r, size / 2 + math.sin(math.radians(-half)) * r)
    p2 = (size / 2 + math.cos(math.radians(half)) * r, size / 2 + math.sin(math.radians(half)) * r)
    ImageDraw.Draw(mask).polygon([(size / 2, size / 2), p1, p2], fill=255)

    for i in range(segments):
        piece = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        src = wedge if i % 2 == 0 else wedge.transpose(Image.FLIP_LEFT_RIGHT)
        rotated = src.rotate(-i * angle_step, resample=Image.BICUBIC, center=(size / 2, size / 2))
        piece.paste(rotated, (0, 0), mask)
        canvas = Image.alpha_composite(canvas, piece)
    return canvas


def color_shift_gradient(img: Image.Image, first: str = "#ff0080", second: str = "#7928ca", mode: str = "color") -> Image.Image:
    """غسل لوني متدرّج بنمط مزج قابل للاختيار."""
    from .composite import blend_images

    w, h = img.size
    grad = Image.new("RGB", (w, h))
    c1 = np.array(parse_color(first), np.float32)
    c2 = np.array(parse_color(second), np.float32)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    t = ((x / w) * 0.6 + (y / h) * 0.4)[..., None]
    grad_arr = (c1 * (1 - t) + c2 * t).astype(np.uint8)
    grad = Image.fromarray(grad_arr, "RGB")
    return blend_images(img, grad, mode=mode, opacity=0.55)


def ascii_art(img: Image.Image, cell: int = 10, charset: str = "@%#*+=-:. ", on_dark: bool = True) -> Image.Image:
    """تحويل الصورة إلى فن ASCII مرسوم كصورة (بلا نص حقيقي)."""
    arr = to_rgb_array(img).astype(np.uint8)
    h, w = arr.shape[:2]
    cell = int(np.clip(cell, 4, 40))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(gray, (max(1, w // cell), max(1, h // cell)), interpolation=cv2.INTER_AREA)

    out = np.full((h, w, 3), 12 if on_dark else 245, np.uint8)
    img_pil = Image.fromarray(out, "RGB")
    draw = ImageDraw.Draw(img_pil)
    from ..core.fonts import get_mono_font

    font = get_mono_font(int(cell))

    chars = charset or "@%#*+=-:. "
    for gy in range(small.shape[0]):
        for gx in range(small.shape[1]):
            idx = int((255 - small[gy, gx]) / 256 * len(chars))
            idx = min(idx, len(chars) - 1)
            ch = chars[idx]
            if ch == " ":
                continue
            draw.text((gx * cell, gy * cell), ch, fill=(235, 235, 235) if on_dark else (20, 20, 20), font=font)
    return img_pil


def double_exposure(img: Image.Image, second: Image.Image, amount: float = 0.5, mode: str = "screen") -> Image.Image:
    """تعريض مزدوج بين صورتين."""
    from .composite import blend_images

    sized = second.convert("RGB").resize(img.size, Image.LANCZOS)
    return blend_images(img, sized, mode=mode, opacity=float(np.clip(amount, 0, 1)))


def thermal(img: Image.Image) -> Image.Image:
    """خريطة حرارية (Thermal) عبر تدرّج لوني على الإضاءة."""
    from ..core.helpers import luminance

    arr = to_rgb_array(img)
    lum = luminance(arr) / 255.0
    stops = [
        (0.00, (10, 4, 40)), (0.25, (40, 10, 140)), (0.50, (200, 40, 60)),
        (0.75, (250, 170, 30)), (1.00, (255, 250, 220)),
    ]
    xs = np.array([s[0] for s in stops], np.float32)
    ys = np.array([s[1] for s in stops], np.float32)
    out = np.stack([np.interp(lum, xs, ys[:, c]) for c in range(3)], axis=-1)
    return from_rgb_array(out)


def night_vision(img: Image.Image, amount: float = 1.0) -> Image.Image:
    """رؤية ليلية: أخضر فسفوري + تضخيم + حبيبات + تظليل دائري."""
    from ..core.helpers import luminance

    arr = to_rgb_array(img)
    lum = luminance(arr)
    boosted = np.clip((lum / 255.0) ** 0.6, 0, 1) * 255
    h, w = arr.shape[:2]
    rng = np.random.default_rng(9)
    boosted += rng.normal(0, 10 * float(amount), (h, w))
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((x / w - 0.5) / 0.5) ** 2 + ((y / h - 0.5) / 0.5) ** 2)
    boosted *= 1 - 0.55 * np.clip(d - 0.6, 0, 1)
    out = np.dstack([boosted * 0.35, boosted, boosted * 0.35])
    return from_rgb_array(out)


def pop_art(img: Image.Image, levels: int = 4, saturation: float = 1.6) -> Image.Image:
    """فن البوب: ألوان مسطّحة عالية التشبّع (تأثير Andy Warhol)."""
    arr = to_rgb_array(img).astype(np.uint8)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * float(saturation), 0, 255)
    arr = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    step = 255.0 / max(2, int(levels) - 1)
    arr = np.round(arr.astype(np.float32) / step) * step
    return from_rgb_array(arr)


def sepia(img: Image.Image, strength: float = 1.0) -> Image.Image:
    """سيبيا كلاسيكية بمصفوفة قياسية."""
    matrix = np.array(
        [[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]], np.float32
    )
    arr = to_rgb_array(img)
    s = float(np.clip(strength, 0, 1))
    sep = arr.reshape(-1, 3) @ matrix.T
    sep = sep.reshape(arr.shape)
    return from_rgb_array(arr * (1 - s) + sep * s)


def cross_process(img: Image.Image, strength: float = 1.0) -> Image.Image:
    """معالجة متصالبة (Cross Processing): انزياح لوني في القنوات."""
    arr = unit(to_rgb_array(img))
    s = float(np.clip(strength, 0, 2))
    out = arr.copy()
    # منحنى S مختلف لكل قناة
    x = np.linspace(0, 1, 256, dtype=np.float32)
    curves = {
        0: np.clip(x ** 0.85 * 1.08, 0, 1),
        1: np.clip(x ** 1.12 * 1.02, 0, 1),
        2: np.clip(x ** 1.25 * 1.10, 0, 1),
    }
    for c in range(3):
        out[..., c] = np.interp(arr[..., c], x, curves[c])
    out = arr * (1 - s * 0.6) + out * s * 0.6
    return from_rgb_array(byte(out))


def apply_creative(img: Image.Image, name: str, **params) -> Image.Image:
    """موجّه موحّد للمؤثرات الإبداعية."""
    table = {
        "glitch": glitch, "duotone": duotone, "vintage": vintage, "cinematic": cinematic,
        "light_leak": light_leak, "frame": frame_borders, "lens_blur": lens_blur,
        "bokeh": bokeh_overlay, "mirror": mirror, "kaleidoscope": kaleidoscope,
        "color_shift": color_shift_gradient, "ascii": ascii_art,
        "double_exposure": double_exposure, "thermal": thermal,
        "night_vision": night_vision, "pop_art": pop_art, "sepia": sepia,
        "cross_process": cross_process,
    }
    if name not in table:
        raise InvalidParameterError(f"المؤثر «{name}» غير معروف.", detail={"supported": sorted(table)})
    return table[name](img, **params)


CREATIVE_CATALOG: Dict[str, Dict[str, object]] = {
    "glitch": {"name": "خلل رقمي", "params": {"amount": [0, 2], "slices": [1, 40]}},
    "duotone": {"name": "ثنائي اللون", "params": {"dark": "color", "light": "color"}},
    "vintage": {"name": "قديم", "params": {"strength": [0, 2]}},
    "cinematic": {"name": "سينمائي", "params": {"strength": [0, 2], "teal_orange": "bool"}},
    "light_leak": {"name": "تسريب ضوء", "params": {"hue": [0, 360], "amount": [0, 1]}},
    "frame": {"name": "أشرطة/إطارات", "params": {"style": ["cinema", "square", "thin", "thick", "instant"]}},
    "lens_blur": {"name": "عمق ميدان", "params": {"radius": [1, 40], "falloff": [0, 0.9]}},
    "bokeh": {"name": "بوكيه مضيء", "params": {"count": [1, 120], "amount": [0, 1]}},
    "mirror": {"name": "مرآة", "params": {"axis": ["vertical", "horizontal"]}},
    "kaleidoscope": {"name": "مشكال", "params": {"segments": [2, 16]}},
    "color_shift": {"name": "غسل لوني", "params": {"first": "color", "second": "color"}},
    "ascii": {"name": "فن ASCII", "params": {"cell": [4, 40]}},
    "double_exposure": {"name": "تعريض مزدوج", "params": {"amount": [0, 1]}},
    "thermal": {"name": "خريطة حرارية", "params": {}},
    "night_vision": {"name": "رؤية ليلية", "params": {"amount": [0, 2]}},
    "pop_art": {"name": "فن البوب", "params": {"levels": [2, 8], "saturation": [0, 3]}},
    "sepia": {"name": "سيبيا", "params": {"strength": [0, 1]}},
    "cross_process": {"name": "معالجة متصالبة", "params": {"strength": [0, 2]}},
}


__all__ = [
    "CREATIVE_CATALOG", "apply_creative", "ascii_art", "bokeh_overlay", "cinematic",
    "color_shift_gradient", "cross_process", "double_exposure", "duotone",
    "frame_borders", "glitch", "kaleidoscope", "lens_blur", "light_leak", "mirror",
    "night_vision", "pop_art", "sepia", "thermal", "vintage",
]

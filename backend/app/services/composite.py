"""
الدمج والمزج: طبقات، أنماط مزج، تخطيطات، مزج هرمي، وعلامات مائية.
=================================================================
كل أنماط المزج مطبّقة رياضياً على مجال [0,1] ثم تُعاد إلى [0,255].
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..core.exceptions import InvalidParameterError
from ..core.fonts import get_font, measure, shape_text
from ..core.helpers import from_rgba_array, parse_color, to_rgba_array, unit, byte

# ------------------------------------------------------------------------------
#  أنماط المزج (Photoshop-compatible)
# ------------------------------------------------------------------------------
def _normal(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return b


def _multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a * b


def _screen(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return 1 - (1 - a) * (1 - b)


def _overlay(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.where(a < 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))


def _darken(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.minimum(a, b)


def _lighten(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.maximum(a, b)


def _color_dodge(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = np.clip(1 - b, 1e-6, None)
    return np.clip(a / denom, 0, 1)


def _color_burn(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    denom = np.clip(b, 1e-6, None)
    return 1 - np.clip((1 - a) / denom, 0, 1)


def _hard_light(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.where(b < 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))


def _soft_light(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Soft Light بصيغة Pegtop:  a + (2b-1)·(a - a²)
    صيغة مستقرة عددياً وتعطي انتقالاً ناعماً حول منتصف السطوع.
    """
    return np.clip(a + (2 * b - 1) * (a - a * a), 0, 1)


def _difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.abs(a - b)


def _exclusion(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a + b - 2 * a * b


def _hue(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return _hsl_replace(a, b, hue=True, sat=False, lum=False)


def _saturation(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return _hsl_replace(a, b, hue=False, sat=True, lum=False)


def _color_mode(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return _hsl_replace(a, b, hue=True, sat=True, lum=False)


def _luminosity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return _hsl_replace(a, b, hue=False, sat=False, lum=True)


def _hsl_replace(base: np.ndarray, blend: np.ndarray, hue: bool, sat: bool, lum: bool) -> np.ndarray:
    """استبدال مكوّنات HSL بشكل انتقائي (تُنفَّذ على نسخ uint8 عبر OpenCV)."""
    h, w = base.shape[:2]
    b_u8 = np.clip(base * 255, 0, 255).astype(np.uint8).reshape(h, w, 3)
    l_u8 = np.clip(blend * 255, 0, 255).astype(np.uint8).reshape(h, w, 3)
    bh = cv2.cvtColor(b_u8, cv2.COLOR_RGB2HLS).astype(np.float32)
    lh = cv2.cvtColor(l_u8, cv2.COLOR_RGB2HLS).astype(np.float32)
    out = bh.copy()
    if hue:
        out[..., 0] = lh[..., 0]
    if lum:
        out[..., 1] = lh[..., 1]
    if sat:
        out[..., 2] = lh[..., 2]
    res = cv2.cvtColor(out.astype(np.uint8), cv2.COLOR_HLS2RGB)
    return res.astype(np.float32) / 255.0


def _linear_light(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.clip(a + 2 * (b - 0.5), 0, 1)


def _pin_light(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.where(b < 0.5, np.minimum(a, 2 * b), np.maximum(a, 2 * b - 1))


def _hard_mix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.where(a + b >= 1.0, 1.0, 0.0)


BLEND_MODES: Dict[str, callable] = {
    "normal": _normal,
    "multiply": _multiply,
    "screen": _screen,
    "overlay": _overlay,
    "darken": _darken,
    "lighten": _lighten,
    "color_dodge": _color_dodge,
    "color_burn": _color_burn,
    "hard_light": _hard_light,
    "soft_light": _soft_light,
    "difference": _difference,
    "exclusion": _exclusion,
    "hue": _hue,
    "saturation": _saturation,
    "color": _color_mode,
    "luminosity": _luminosity,
    "linear_light": _linear_light,
    "pin_light": _pin_light,
    "hard_mix": _hard_mix,
}

# ترتيب العرض في الواجهة (مجموعات مفهومة)
BLEND_GROUPS = {
    "عادي": ["normal"],
    "تغميق": ["darken", "multiply", "color_burn", "linear_light"],
    "تفتيح": ["lighten", "screen", "color_dodge"],
    "تباين": ["overlay", "soft_light", "hard_light", "pin_light", "hard_mix"],
    "فارق": ["difference", "exclusion"],
    "مكوّنات": ["hue", "saturation", "color", "luminosity"],
}


# ------------------------------------------------------------------------------
#  أدوات الموضع
# ------------------------------------------------------------------------------
def resolve_position(
    base_size: Tuple[int, int],
    layer_size: Tuple[int, int],
    x: Optional[float] = None,
    y: Optional[float] = None,
    anchor: str = "center",
) -> Tuple[int, int]:
    """
    حساب موضع الطبقة:
      • x,y مُعطاة بنسب [0..1] من اللوحة ⇒ تُستخدم مباشرة.
      • وإلا تُستخدم نقطة ارتكاز نصية (top-left, center, …).
    """
    bw, bh = base_size
    lw, lh = layer_size
    if x is not None and y is not None:
        return int(round(float(x) * bw - lw / 2)), int(round(float(y) * bh - lh / 2))

    table = {
        "center": (0.5, 0.5), "top-left": (0.0, 0.0), "top": (0.5, 0.0),
        "top-right": (1.0, 0.0), "left": (0.0, 0.5), "right": (1.0, 0.5),
        "bottom-left": (0.0, 1.0), "bottom": (0.5, 1.0), "bottom-right": (1.0, 1.0),
    }
    fx, fy = table.get(anchor, (0.5, 0.5))
    return int(round((bw - lw) * fx)), int(round((bh - lh) * fy))


# ------------------------------------------------------------------------------
#  الدمج الأساسي
# ------------------------------------------------------------------------------
def blend_images(
    base: Image.Image,
    layer: Image.Image,
    mode: str = "normal",
    opacity: float = 1.0,
    x: Optional[float] = None,
    y: Optional[float] = None,
    anchor: str = "center",
    scale: float = 1.0,
    invert_layer_alpha: bool = False,
) -> Image.Image:
    """
    دمج طبقة فوق أساس بنمط مزج وشفافية وموضع ومقياس.
    تُحترم قناة ألفا في الطبقة (قناع طبيعي).
    """
    if mode not in BLEND_MODES:
        raise InvalidParameterError(f"نمط المزج «{mode}» غير مدعوم.",
                                    detail={"supported": sorted(BLEND_MODES)})

    base_rgba = base.convert("RGBA")
    layer_rgba = layer.convert("RGBA")

    if abs(float(scale) - 1.0) > 1e-3:
        s = float(np.clip(scale, 0.02, 20.0))
        layer_rgba = layer_rgba.resize(
            (max(1, int(layer_rgba.width * s)), max(1, int(layer_rgba.height * s))), Image.LANCZOS
        )

    bw, bh = base_rgba.size
    lw, lh = layer_rgba.size
    px, py = resolve_position((bw, bh), (lw, lh), x, y, anchor)

    a = unit(to_rgba_array(base_rgba))
    b_full = np.zeros_like(a)
    b_full[..., 3] = 0.0

    # نسخ الطبقة داخل لوحة بمقاس الأساس (مع اقتطاع ما يخرج عن الحدود)
    x0, y0 = max(0, px), max(0, py)
    x1, y1 = min(bw, px + lw), min(bh, py + lh)
    if x1 <= x0 or y1 <= y0:
        return base_rgba  # الطبقة خارج اللوحة كلياً

    l_arr = unit(to_rgba_array(layer_rgba))
    src = l_arr[y0 - py: y1 - py, x0 - px: x1 - px]
    region = a[y0:y1, x0:x1]

    b_full[y0:y1, x0:x1] = src

    if invert_layer_alpha:
        b_full[..., 3] = 1.0 - b_full[..., 3]

    fn = BLEND_MODES[mode]
    blended_rgb = fn(region[..., :3], b_full[y0:y1, x0:x1, :3])

    # ألفا الطبقة × الشفافية = وزن المزج
    w_alpha = b_full[y0:y1, x0:x1, 3:4] * float(np.clip(opacity, 0, 1))
    out_region = region[..., :3] * (1 - w_alpha) + np.clip(blended_rgb, 0, 1) * w_alpha

    result = a.copy()
    result[y0:y1, x0:x1, :3] = out_region
    # تحديث ألفا الأساس: α_out = α_l + α_b·(1-α_l)
    result[y0:y1, x0:x1, 3:4] = np.clip(
        w_alpha + region[..., 3:4] * (1 - w_alpha), 0, 1
    )
    return from_rgba_array(byte(result))


# ------------------------------------------------------------------------------
#  المزج الهرمي (Laplacian Pyramid) — دمج سلس بلا خط فاصل
# ------------------------------------------------------------------------------
def _gaussian_pyramid(img: np.ndarray, levels: int) -> List[np.ndarray]:
    pyr = [img]
    for _ in range(levels):
        pyr.append(cv2.pyrDown(pyr[-1]))
    return pyr


def _laplacian_pyramid(img: np.ndarray, levels: int) -> List[np.ndarray]:
    gp = _gaussian_pyramid(img, levels)
    lp = []
    for i in range(levels):
        size = (gp[i].shape[1], gp[i].shape[0])
        up = cv2.pyrUp(gp[i + 1], dstsize=size)
        lp.append(gp[i] - up)
    lp.append(gp[-1])
    return lp


def _reconstruct(lp: List[np.ndarray]) -> np.ndarray:
    img = lp[-1]
    for level in reversed(lp[:-1]):
        size = (level.shape[1], level.shape[0])
        img = cv2.pyrUp(img, dstsize=size) + level
    return img


def blend_seamless(
    base: Image.Image,
    layer: Image.Image,
    mask: Optional[Image.Image] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    anchor: str = "center",
    levels: int = 5,
    feather: float = 20.0,
) -> Image.Image:
    """
    دمج هرمي (Multiband / Laplacian Pyramid Blending):
    يمزج الترددات المنخفضة في منطقة واسعة والترددات العالية في منطقة ضيقة،
    فيختفي الخط الفاصل بين الصورتين.
    """
    base_rgba = np.array(base.convert("RGB"), dtype=np.float32)
    layer_img = layer.convert("RGBA")
    bh, bw = base_rgba.shape[:2]

    # موضع الطبقة
    px, py = resolve_position((bw, bh), layer_img.size, x, y, anchor)
    canvas = np.zeros_like(base_rgba)
    alpha_canvas = np.zeros((bh, bw), np.float32)

    x0, y0 = max(0, px), max(0, py)
    x1, y1 = min(bw, px + layer_img.width), min(bh, py + layer_img.height)
    if x1 <= x0 or y1 <= y0:
        return base.convert("RGB")

    l_arr = np.array(layer_img, dtype=np.float32)
    canvas[y0:y1, x0:x1] = l_arr[y0 - py: y1 - py, x0 - px: x1 - px, :3]
    alpha_canvas[y0:y1, x0:x1] = l_arr[y0 - py: y1 - py, x0 - px: x1 - px, 3] / 255.0

    # القناع
    if mask is not None:
        m = mask.convert("L").resize((bw, bh), Image.BILINEAR)
        m = np.array(m, dtype=np.float32) / 255.0
    else:
        m = alpha_canvas
    if feather > 0:
        k = int(max(1, feather)) * 2 + 1
        m = cv2.GaussianBlur(m, (k, k), 0)

    levels = int(np.clip(levels, 1, 8))
    lp_a = _laplacian_pyramid(base_rgba, levels)
    lp_b = _laplacian_pyramid(canvas, levels)
    gp_m = _gaussian_pyramid(m[..., None], levels)

    out_pyr = []
    for la, lb, gm in zip(lp_a, lp_b, gp_m):
        # cv2.pyrDown يُسقط البعد المفرد أحياناً ⇒ نُعيده ليكون (H,W,1) صالحاً للبثّ
        if gm.ndim == 2:
            gm = gm[..., None]
        gm = gm.reshape(gm.shape[0], gm.shape[1], 1).astype(np.float32)
        out_pyr.append(la * (1 - gm) + lb * gm)

    result = np.clip(_reconstruct(out_pyr), 0, 255).astype(np.uint8)
    return Image.fromarray(result, "RGB")


# ------------------------------------------------------------------------------
#  تخطيطات الدمج
# ------------------------------------------------------------------------------
def merge_images(
    images: Sequence[Image.Image],
    layout: str = "horizontal",
    gap: int = 0,
    background: str = "#ffffff",
    transparent: bool = False,
    align: str = "center",
    radius: int = 0,
    border: int = 0,
    border_color: str = "#dddddd",
) -> Image.Image:
    """
    دمج عدة صور في تخطيط واحد:
      horizontal | vertical | grid | stacked
    """
    if not images:
        raise InvalidParameterError("لا توجد صور للدمج.")
    if len(images) == 1:
        return images[0].convert("RGBA")

    gap = int(max(0, gap))
    bg = (0, 0, 0, 0) if transparent else parse_color(background) + (255,)
    items = [im.convert("RGBA") for im in images]

    if layout == "grid":
        n = len(items)
        cols = int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols))
        cell_w = max(im.width for im in items)
        cell_h = max(im.height for im in items)
        canvas = Image.new("RGBA", (cols * cell_w + (cols - 1) * gap, rows * cell_h + (rows - 1) * gap), bg)
        for i, im in enumerate(items):
            r, c = divmod(i, cols)
            x = c * (cell_w + gap)
            y = r * (cell_h + gap)
            if align == "center":
                x += (cell_w - im.width) // 2
                y += (cell_h - im.height) // 2
            elif align == "bottom":
                y += cell_h - im.height
            canvas.paste(im, (x, y), im)
        return _finish_merge(canvas, radius, border, border_color)

    if layout == "vertical":
        width = max(im.width for im in items)
        height = sum(im.height for im in items) + gap * (len(items) - 1)
        canvas = Image.new("RGBA", (width, height), bg)
        y = 0
        for im in items:
            x = {"center": (width - im.width) // 2, "left": 0, "right": width - im.width}.get(align, 0)
            canvas.paste(im, (x, y), im)
            y += im.height + gap
        return _finish_merge(canvas, radius, border, border_color)

    if layout == "stacked":
        # تكديس متدرّج (كصور مبعثرة)
        width = max(im.width for im in items) + 40 * (len(items) - 1)
        height = max(im.height for im in items) + 40 * (len(items) - 1)
        canvas = Image.new("RGBA", (width, height), bg)
        for i, im in enumerate(items):
            canvas.paste(im, (i * 40, i * 40), im)
        return _finish_merge(canvas, radius, border, border_color)

    # horizontal (الافتراضي)
    height = max(im.height for im in items)
    width = sum(im.width for im in items) + gap * (len(items) - 1)
    canvas = Image.new("RGBA", (width, height), bg)
    x = 0
    for im in items:
        y = {"center": (height - im.height) // 2, "top": 0, "bottom": height - im.height}.get(align, 0)
        canvas.paste(im, (x, y), im)
        x += im.width + gap
    return _finish_merge(canvas, radius, border, border_color)


def _finish_merge(canvas: Image.Image, radius: int, border: int, border_color: str) -> Image.Image:
    """تطبيق الحواف الدائرية والإطار على نتيجة الدمج."""
    if radius > 0:
        mask = Image.new("L", canvas.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, canvas.width - 1, canvas.height - 1],
                                               radius=int(radius), fill=255)
        out = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        out.paste(canvas, (0, 0), mask)
        canvas = out
    if border > 0:
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, 0, canvas.width - 1, canvas.height - 1],
                       outline=parse_color(border_color) + (255,), width=int(border))
    return canvas


def picture_in_picture(
    base: Image.Image,
    inset: Image.Image,
    size: float = 0.28,
    anchor: str = "bottom-right",
    margin: float = 0.04,
    border: int = 4,
    border_color: str = "#ffffff",
    radius: int = 10,
    shadow: bool = True,
) -> Image.Image:
    """صورة داخل صورة (PiP) مع إطار وظل اختياري."""
    base_rgba = base.convert("RGBA")
    bw, bh = base_rgba.size
    scale = size * max(bw, bh) / max(inset.width, inset.height)
    small = inset.convert("RGBA").resize(
        (max(1, int(inset.width * scale)), max(1, int(inset.height * scale))), Image.LANCZOS
    )

    if radius > 0:
        mask = Image.new("L", small.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, small.width - 1, small.height - 1],
                                               radius=int(radius), fill=255)
        rounded = Image.new("RGBA", small.size, (0, 0, 0, 0))
        rounded.paste(small, (0, 0), mask)
        small = rounded

    m = int(margin * min(bw, bh))
    positions = {
        "bottom-right": (bw - small.width - m, bh - small.height - m),
        "bottom-left": (m, bh - small.height - m),
        "top-right": (bw - small.width - m, m),
        "top-left": (m, m),
        "center": ((bw - small.width) // 2, (bh - small.height) // 2),
    }
    px, py = positions.get(anchor, positions["bottom-right"])

    if shadow:
        sh = Image.new("RGBA", small.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([0, 0, small.width - 1, small.height - 1],
                                             radius=int(radius), fill=(0, 0, 0, 110))
        sh = sh.filter(ImageFilter.GaussianBlur(6))
        base_rgba.paste(sh, (px + 4, py + 6), sh)

    if border > 0:
        draw = ImageDraw.Draw(base_rgba)
        draw.rounded_rectangle([px, py, px + small.width - 1, py + small.height - 1],
                               radius=int(radius), outline=parse_color(border_color) + (255,),
                               width=int(border))
    base_rgba.paste(small, (px, py), small)
    return base_rgba


# ------------------------------------------------------------------------------
#  العلامة المائية
# ------------------------------------------------------------------------------
def watermark_text(
    img: Image.Image,
    text: str,
    font_size: int = 36,
    color: str = "#ffffff",
    opacity: float = 0.5,
    position: str = "bottom-right",
    margin: int = 24,
    tile: bool = False,
    angle: float = 0.0,
    outline: bool = True,
) -> Image.Image:
    """علامة مائية نصية (مفردة أو مبلّطة على كامل الصورة)."""
    base = img.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # تشكيل النص العربي ثم اختيار خط يدعمه
    text = shape_text(text)
    font = get_font(int(font_size), bold=True)

    fill = parse_color(color) + (int(255 * float(np.clip(opacity, 0, 1))),)
    stroke = (0, 0, 0, fill[3]) if outline else None

    if tile:
        tw, th, ox, oy = measure(draw, text, font)
        tile_layer = Image.new("RGBA", (tw + 40, th + 40), (0, 0, 0, 0))
        ImageDraw.Draw(tile_layer).text((20, 20), text, font=font, fill=fill,
                                        stroke_width=1 if outline else 0, stroke_fill=stroke)
        if angle:
            tile_layer = tile_layer.rotate(float(angle), expand=True, resample=Image.BICUBIC)
        for y in range(0, base.height, tile_layer.height + 60):
            for x in range(0, base.width, tile_layer.width + 60):
                layer.paste(tile_layer, (x, y), tile_layer)
    else:
        tw, th, ox, oy = measure(draw, text, font)
        positions = {
            "bottom-right": (base.width - tw - margin, base.height - th - margin),
            "bottom-left": (margin, base.height - th - margin),
            "top-right": (base.width - tw - margin, margin),
            "top-left": (margin, margin),
            "center": ((base.width - tw) // 2, (base.height - th) // 2),
            "bottom": ((base.width - tw) // 2, base.height - th - margin),
            "top": ((base.width - tw) // 2, margin),
        }
        x, y = positions.get(position, positions["bottom-right"])
        if angle:
            txt_layer = Image.new("RGBA", (tw + 40, th + 40), (0, 0, 0, 0))
            ImageDraw.Draw(txt_layer).text((20, 20), text, font=font, fill=fill,
                                           stroke_width=1 if outline else 0, stroke_fill=stroke)
            txt_layer = txt_layer.rotate(float(angle), expand=True, resample=Image.BICUBIC)
            layer.paste(txt_layer, (x - 20, y - 20), txt_layer)
        else:
            draw.text((x, y), text, font=font, fill=fill,
                      stroke_width=1 if outline else 0, stroke_fill=stroke)

    out = Image.alpha_composite(base, layer)
    return out


def watermark_image(
    img: Image.Image,
    logo: Image.Image,
    size: float = 0.18,
    position: str = "bottom-right",
    margin: float = 0.03,
    opacity: float = 0.85,
    tile: bool = False,
) -> Image.Image:
    """علامة مائية بشعار/صورة."""
    base = img.convert("RGBA")
    bw, bh = base.size
    scale = size * max(bw, bh) / max(logo.width, logo.height)
    small = logo.convert("RGBA").resize(
        (max(1, int(logo.width * scale)), max(1, int(logo.height * scale))), Image.LANCZOS
    )
    if opacity < 1.0:
        r, g, b, a = small.split()
        a = a.point(lambda p: int(p * float(np.clip(opacity, 0, 1))))
        small = Image.merge("RGBA", (r, g, b, a))

    if tile:
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        for y in range(0, bh, small.height + 80):
            for x in range(0, bw, small.width + 80):
                layer.paste(small, (x, y), small)
        return Image.alpha_composite(base, layer)

    m = int(margin * min(bw, bh))
    positions = {
        "bottom-right": (bw - small.width - m, bh - small.height - m),
        "bottom-left": (m, bh - small.height - m),
        "top-right": (bw - small.width - m, m),
        "top-left": (m, m),
        "center": ((bw - small.width) // 2, (bh - small.height) // 2),
    }
    x, y = positions.get(position, positions["bottom-right"])
    base.paste(small, (x, y), small)
    return base


__all__ = [
    "BLEND_GROUPS", "BLEND_MODES", "blend_images", "blend_seamless", "merge_images",
    "picture_in_picture", "resolve_position", "watermark_image", "watermark_text",
]

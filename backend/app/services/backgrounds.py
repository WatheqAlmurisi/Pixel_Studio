"""
مكتبة خلفيات المنتجات — مولَّدة برمجياً بالكامل.
=================================================
لا يعتمد المشروع على أي صور خارجية: كل خلفية تُرسم بالخوارزميات
(تدرّجات، ضوضاء بيرلِن مبسّطة، دوائر بوكيه، عروق رخام، ألياف خشب…) ثم تُخزَّن
مؤقتاً في .cache/backgrounds لتفادي إعادة الحساب.
"""
from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..core.exceptions import NotFoundError
from ..core.helpers import from_rgb_array, to_rgb_array
from ..core.settings import settings


# ==============================================================================
#  أدوات الرسم المساعدة
# ==============================================================================
def _rng(seed: str) -> np.random.Generator:
    """مولّد عشوائي ثابت البذرة ⇒ نفس الخلفية في كل مرة (نتائج قابلة للتكرار)."""
    return np.random.default_rng(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16))


def _smooth_noise(h: int, w: int, rng: np.random.Generator, scale: int = 8, octaves: int = 4) -> np.ndarray:
    """ضوضاء ناعمة متعددة الطبقات (fBm مبسّط) بمجال [0,1]."""
    out = np.zeros((h, w), np.float32)
    amp, freq, total = 1.0, 1.0, 0.0
    base_h, base_w = max(2, h // int(scale)), max(2, w // int(scale))
    freq = 1
    for _ in range(int(octaves)):
        # القسمة الصحيحة على freq (عدد صحيح) ضرورية لأن range/الأبعاد لا تقبل عشرياً
        sh = max(2, base_h // freq + 2)
        sw = max(2, base_w // freq + 2)
        small = rng.random((sh, sw)).astype(np.float32)
        up = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
        out += up * amp
        total += amp
        amp *= 0.5
        freq *= 2
    return out / max(total, 1e-6)


def _radial_mask(h: int, w: int, cx: float = 0.5, cy: float = 0.5, power: float = 1.6) -> np.ndarray:
    """قناع شعاعي (1 في المركز ← 0 عند الحواف)."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = (x / w - cx) / 0.75
    dy = (y / h - cy) / 0.75
    d = np.sqrt(dx ** 2 + dy ** 2)
    return np.clip(1.0 - d, 0, 1) ** power


def _linear_gradient(h: int, w: int, c1: Tuple[int, int, int], c2: Tuple[int, int, int], angle: float = 90.0) -> np.ndarray:
    """تدرّج خطي بزاوية."""
    rad = math.radians(angle)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    proj = (x / w) * math.cos(rad) + (y / h) * math.sin(rad)
    # np.ptp بدل الخاصية .ptp() (أُزيلت من ndarray في NumPy 2.0)
    proj = (proj - proj.min()) / max(float(np.ptp(proj)), 1e-6)
    c1a = np.array(c1, np.float32).reshape(1, 1, 3)
    c2a = np.array(c2, np.float32).reshape(1, 1, 3)
    return c1a * (1 - proj[..., None]) + c2a * proj[..., None]


def _vignette(arr: np.ndarray, strength: float = 0.35) -> np.ndarray:
    """تعتيم الحواف لإبراز المنتج في المنتصف."""
    h, w = arr.shape[:2]
    mask = _radial_mask(h, w, power=1.4)[..., None]
    factor = 1.0 - strength * (1.0 - mask)
    return np.clip(arr * factor, 0, 255)


# ==============================================================================
#  مولّدات الخلفيات
# ==============================================================================
def bg_studio(size: int, tone: str = "white") -> np.ndarray:
    """خلفية استوديو سلسة مع بقعة ضوء مركزية وأرضية."""
    tones = {
        "white": ((252, 252, 253), (214, 216, 220)),
        "grey": ((196, 198, 202), (128, 130, 136)),
        "dark": ((72, 74, 80), (24, 25, 28)),
        "warm": ((250, 244, 234), (216, 200, 178)),
        "cool": ((238, 245, 250), (196, 214, 228)),
    }
    c1, c2 = tones.get(tone, tones["white"])
    h = w = size
    arr = _linear_gradient(h, w, c1, c2, angle=90)
    spot = _radial_mask(h, w, 0.5, 0.38, 1.8)[..., None]
    arr = arr * (0.78 + 0.34 * spot)
    # خط الأفق (التقاء الخلفية بالأرضية)
    horizon = int(h * 0.72)
    floor_dark = np.clip((np.arange(h)[:, None] - horizon) / (h * 0.3), 0, 1)
    arr *= (1.0 - 0.16 * floor_dark[..., None])
    return np.clip(arr, 0, 255)


def bg_radial_spot(size: int, color: str = "blue") -> np.ndarray:
    """تدرّج شعاعي ملوّن (Spotlight)."""
    palettes = {
        "blue": ((46, 96, 168), (8, 16, 34)),
        "teal": ((24, 148, 148), (6, 34, 38)),
        "violet": ((118, 74, 188), (22, 12, 40)),
        "amber": ((226, 152, 46), (46, 26, 8)),
        "rose": ((214, 92, 128), (44, 12, 24)),
        "green": ((58, 158, 96), (8, 32, 20)),
    }
    c1, c2 = palettes.get(color, palettes["blue"])
    h = w = size
    spot = _radial_mask(h, w, 0.5, 0.42, 1.5)[..., None]
    arr = np.array(c2, np.float32).reshape(1, 1, 3) * np.ones((h, w, 1), np.float32)
    arr = arr + (np.array(c1, np.float32).reshape(1, 1, 3) - arr) * spot
    return np.clip(arr, 0, 255)


def bg_marble(size: int, base: str = "white") -> np.ndarray:
    """رخام: عروق عبر دالة جيبية مشوَّشة بضوضاء."""
    bases = {
        "white": ((248, 247, 245), (96, 98, 104)),
        "black": ((34, 34, 38), (186, 188, 194)),
        "gold": ((244, 236, 220), (150, 118, 58)),
        "green": ((226, 238, 230), (58, 104, 82)),
    }
    c1, c2 = bases.get(base, bases["white"])
    h = w = size
    rng = _rng(f"marble-{base}")
    n1 = _smooth_noise(h, w, rng, scale=16, octaves=5)
    n2 = _smooth_noise(h, w, rng, scale=48, octaves=3)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    veins = np.sin((x / w * 6.0 + n1 * 5.0 + n2 * 2.0) * math.pi)
    veins = np.clip(np.abs(veins) ** 0.35, 0, 1)
    t = 1.0 - veins[..., None]
    arr = np.array(c1, np.float32) * t + np.array(c2, np.float32) * (1 - t)
    # لمعان خفيف
    arr += (_smooth_noise(h, w, rng, scale=4, octaves=2)[..., None] - 0.5) * 8
    return np.clip(arr, 0, 255)


def bg_wood(size: int, tone: str = "oak") -> np.ndarray:
    """خشب: خطوط ألياف متموّجة + عُقد."""
    tones = {
        "oak": ((196, 148, 96), (122, 84, 48)),
        "walnut": ((116, 78, 50), (58, 36, 22)),
        "maple": ((228, 196, 152), (176, 138, 92)),
        "ebony": ((64, 52, 46), (26, 20, 18)),
    }
    c1, c2 = tones.get(tone, tones["oak"])
    h = w = size
    rng = _rng(f"wood-{tone}")
    n = _smooth_noise(h, w, rng, scale=24, octaves=4)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    rings = np.sin((y / h * 42.0 + n * 7.0) * math.pi)
    grain = (rings * 0.5 + 0.5) ** 1.7
    fine = _smooth_noise(h, w, rng, scale=3, octaves=2)
    t = np.clip(grain * 0.85 + fine * 0.15, 0, 1)[..., None]
    arr = np.array(c1, np.float32) * (1 - t) + np.array(c2, np.float32) * t
    return np.clip(arr, 0, 255)


def bg_concrete(size: int, tone: str = "grey") -> np.ndarray:
    """خرسانة/إسمنت: ضوضاء خشنة + بقع."""
    tones = {"grey": (168, 168, 170), "dark": (86, 86, 90), "sand": (196, 182, 162)}
    base = np.array(tones.get(tone, tones["grey"]), np.float32)
    h = w = size
    rng = _rng(f"concrete-{tone}")
    n1 = _smooth_noise(h, w, rng, scale=6, octaves=5)
    n2 = _smooth_noise(h, w, rng, scale=40, octaves=3)
    arr = base.reshape(1, 1, 3) + (n1[..., None] - 0.5) * 46 + (n2[..., None] - 0.5) * 30
    # حبيبات دقيقة
    arr += (rng.random((h, w, 1)).astype(np.float32) - 0.5) * 10
    return np.clip(arr, 0, 255)


def bg_bokeh(size: int, palette: str = "warm") -> np.ndarray:
    """بوكيه: دوائر ضبابية متراكبة بشفافية."""
    palettes = {
        "warm": ((58, 32, 20), [(255, 196, 120), (255, 158, 92), (255, 226, 176)]),
        "cool": ((14, 26, 48), [(120, 190, 255), (150, 220, 240), (90, 150, 230)]),
        "pastel": ((240, 236, 246), [(255, 198, 214), (198, 226, 255), (214, 255, 224)]),
        "neon": ((12, 8, 26), [(255, 72, 190), (72, 220, 255), (255, 226, 72)]),
        "gold": ((40, 28, 10), [(255, 214, 120), (255, 182, 66), (255, 240, 190)]),
    }
    base_c, colors = palettes.get(palette, palettes["warm"])
    h = w = size
    rng = _rng(f"bokeh-{palette}")
    arr = np.full((h, w, 3), base_c, np.float32)
    arr += _linear_gradient(h, w, base_c, tuple(min(255, int(c * 1.35)) for c in base_c), 120) * 0.25

    for i in range(46):
        cx = float(rng.uniform(0, w))
        cy = float(rng.uniform(0, h))
        r = float(rng.uniform(size * 0.03, size * 0.16))
        color = colors[int(rng.integers(0, len(colors)))]
        alpha = float(rng.uniform(0.10, 0.30))
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        circle = np.clip(1.0 - dist / r, 0, 1) ** 1.3
        # حلقة أطول (Bokeh حقيقي له حافة أوضح)
        ring = np.clip(1.0 - np.abs(dist / r - 0.82) / 0.16, 0, 1) * 0.55
        mask = np.clip(circle + ring, 0, 1)[..., None] * alpha
        arr = arr * (1 - mask) + np.array(color, np.float32).reshape(1, 1, 3) * mask
    return np.clip(arr, 0, 255)


def bg_geometric(size: int, style: str = "triangles") -> np.ndarray:
    """أشكال هندسية: مثلثات / دوائر / خطوط."""
    h = w = size
    rng = _rng(f"geo-{style}")
    arr = _linear_gradient(h, w, (246, 247, 250), (216, 222, 232), 135)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    palette = [(74, 108, 247), (247, 122, 88), (60, 186, 154), (250, 196, 66), (142, 96, 220)]

    if style == "circles":
        for _ in range(28):
            r = int(rng.uniform(size * 0.02, size * 0.14))
            x = int(rng.uniform(0, w)); y = int(rng.uniform(0, h))
            c = palette[int(rng.integers(0, len(palette)))]
            draw.ellipse([x - r, y - r, x + r, y + r], fill=c + (int(rng.uniform(40, 110)),))
    elif style == "lines":
        for _ in range(40):
            x1 = int(rng.uniform(-w * 0.2, w * 1.2)); y1 = int(rng.uniform(-h * 0.2, h * 1.2))
            ang = float(rng.uniform(0, math.pi))
            length = float(rng.uniform(size * 0.2, size * 0.9))
            c = palette[int(rng.integers(0, len(palette)))]
            draw.line([x1, y1, x1 + math.cos(ang) * length, y1 + math.sin(ang) * length],
                      fill=c + (int(rng.uniform(50, 120)),), width=int(rng.uniform(2, 10)))
    else:  # triangles
        for _ in range(26):
            cx = float(rng.uniform(0, w)); cy = float(rng.uniform(0, h))
            s = float(rng.uniform(size * 0.05, size * 0.2))
            rot = float(rng.uniform(0, 2 * math.pi))
            pts = [(cx + math.cos(rot + i * 2 * math.pi / 3) * s, cy + math.sin(rot + i * 2 * math.pi / 3) * s)
                   for i in range(3)]
            c = palette[int(rng.integers(0, len(palette)))]
            draw.polygon(pts, fill=c + (int(rng.uniform(40, 100)),))
    return np.array(img.convert("RGB"), np.float32)


def bg_mesh_gradient(size: int, palette: str = "sunset") -> np.ndarray:
    """تدرّج شبكي ناعم (Mesh Gradient) بعدة مراكز لونية."""
    schemes = {
        "sunset": [(255, 154, 108), (255, 96, 148), (140, 82, 255), (255, 206, 128)],
        "ocean": [(64, 200, 220), (46, 116, 226), (120, 240, 200), (28, 60, 140)],
        "forest": [(126, 214, 130), (46, 148, 110), (206, 236, 140), (24, 84, 66)],
        "candy": [(255, 182, 214), (182, 214, 255), (255, 236, 182), (226, 182, 255)],
        "mono": [(238, 238, 240), (196, 198, 204), (250, 250, 252), (150, 152, 158)],
    }
    colors = schemes.get(palette, schemes["sunset"])
    h = w = size
    rng = _rng(f"mesh-{palette}")
    small = 96
    y, x = np.mgrid[0:small, 0:small].astype(np.float32)
    acc = np.zeros((small, small, 3), np.float32)
    wsum = np.zeros((small, small, 1), np.float32)
    for c in colors:
        cx, cy = float(rng.uniform(0, small)), float(rng.uniform(0, small))
        dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) + 1e-3
        weight = (1.0 / dist ** 2)[..., None]
        acc += np.array(c, np.float32).reshape(1, 1, 3) * weight
        wsum += weight
    small_img = acc / np.maximum(wsum, 1e-6)
    arr = cv2.resize(small_img, (w, h), interpolation=cv2.INTER_CUBIC)
    return np.clip(arr, 0, 255)


def bg_pastel(size: int, tone: str = "pink") -> np.ndarray:
    """خلفية باستيل ناعمة مع حبيبات ورقية."""
    tones = {
        "pink": ((255, 232, 238), (248, 202, 216)),
        "mint": ((228, 248, 240), (196, 236, 222)),
        "lavender": ((240, 234, 252), (216, 202, 244)),
        "peach": ((255, 240, 226), (252, 214, 184)),
        "sky": ((228, 242, 255), (194, 222, 250)),
        "butter": ((255, 250, 226), (250, 236, 184)),
    }
    c1, c2 = tones.get(tone, tones["pink"])
    h = w = size
    rng = _rng(f"pastel-{tone}")
    arr = _linear_gradient(h, w, c1, c2, 110)
    arr += _radial_mask(h, w, 0.5, 0.35, 1.6)[..., None] * 14
    arr += (rng.random((h, w, 1)).astype(np.float32) - 0.5) * 7
    return np.clip(arr, 0, 255)


def bg_solid(size: int, hex_color: str = "#f5f5f5") -> np.ndarray:
    """لون سادة مع تدرّج طفيف جداً (لتفادي الحزم اللونية Banding)."""
    from ..core.helpers import parse_color

    c = parse_color(hex_color)
    h = w = size
    arr = np.full((h, w, 3), c, np.float32)
    arr += _radial_mask(h, w, 0.5, 0.45, 2.0)[..., None] * 10 - 5
    return np.clip(arr, 0, 255)


def bg_linen(size: int, tone: str = "natural") -> np.ndarray:
    """قماش/كتان: نسيج متقاطع."""
    tones = {"natural": (232, 224, 208), "grey": (214, 214, 212), "black": (52, 52, 54)}
    base = np.array(tones.get(tone, tones["natural"]), np.float32)
    h = w = size
    rng = _rng(f"linen-{tone}")
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    warp = np.sin(x / 3.0) * 6 + np.sin(y / 3.0) * 6
    n = _smooth_noise(h, w, rng, scale=4, octaves=3)
    arr = base.reshape(1, 1, 3) + warp[..., None] + (n[..., None] - 0.5) * 26
    return np.clip(arr, 0, 255)


def bg_water(size: int, tone: str = "light") -> np.ndarray:
    """سطح ماء: تموجات + انعكاسات."""
    tones = {"light": ((222, 240, 248), (160, 206, 228)), "deep": ((46, 118, 158), (12, 44, 68))}
    c1, c2 = tones.get(tone, tones["light"])
    h = w = size
    rng = _rng(f"water-{tone}")
    n = _smooth_noise(h, w, rng, scale=30, octaves=4)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    ripple = np.sin((x / w * 12 + n * 5) * math.pi) * np.sin((y / h * 8 + n * 4) * math.pi)
    arr = _linear_gradient(h, w, c1, c2, 90)
    arr += ripple[..., None] * 26
    arr += _radial_mask(h, w, 0.5, 0.4, 1.6)[..., None] * 22
    return np.clip(arr, 0, 255)


def bg_reflective(size: int, tone: str = "black") -> np.ndarray:
    """سطح عاكس (زجاج/أكريليك) مع انعكاس متدرّج."""
    tones = {"black": ((46, 46, 50), (12, 12, 14)), "white": ((250, 250, 252), (206, 208, 214))}
    c1, c2 = tones.get(tone, tones["black"])
    h = w = size
    arr = _linear_gradient(h, w, c1, c2, 90)
    y = np.arange(h, dtype=np.float32)[:, None] / h
    horizon = 0.62
    refl = np.clip(1.0 - np.abs(y - horizon) / 0.18, 0, 1) ** 1.4
    arr = arr * (1.0 - 0.35 * refl[..., None]) + np.array(c1, np.float32) * 0.35 * refl[..., None]
    arr = arr * (0.86 + 0.3 * _radial_mask(h, w, 0.5, 0.42, 1.7)[..., None])
    return np.clip(arr, 0, 255)


def bg_paper(size: int, tone: str = "kraft") -> np.ndarray:
    """ورق: كرافت / أبيض / ملوّن مع ألياف."""
    tones = {"kraft": (206, 172, 128), "white": (250, 249, 246), "cream": (246, 238, 220), "navy": (36, 52, 84)}
    base = np.array(tones.get(tone, tones["kraft"]), np.float32)
    h = w = size
    rng = _rng(f"paper-{tone}")
    n = _smooth_noise(h, w, rng, scale=5, octaves=4)
    fibers = _smooth_noise(h, w, rng, scale=2, octaves=2)
    arr = base.reshape(1, 1, 3) + (n[..., None] - 0.5) * 30 + (fibers[..., None] - 0.5) * 14
    arr = arr * (0.94 + 0.14 * _radial_mask(h, w, 0.5, 0.45, 1.5)[..., None])
    return np.clip(arr, 0, 255)


def bg_gradient_duo(size: int, first: str = "#6a5cff", second: str = "#00d4ff") -> np.ndarray:
    """تدرّج ثنائي اللون قابل للتخصيص."""
    from ..core.helpers import parse_color

    c1, c2 = parse_color(first), parse_color(second)
    h = w = size
    arr = _linear_gradient(h, w, c1, c2, 135)
    arr += _radial_mask(h, w, 0.3, 0.25, 1.8)[..., None] * 26
    return np.clip(arr, 0, 255)


# ==============================================================================
#  السجل (Registry)
# ==============================================================================
@dataclass
class BackgroundSpec:
    id: str
    name: str                     # الاسم العربي
    category: str
    generator: Callable[..., np.ndarray]
    kwargs: Dict[str, str]
    description: str = ""


def _spec(id_: str, name: str, category: str, gen: Callable, description: str = "", **kw) -> BackgroundSpec:
    return BackgroundSpec(id_, name, category, gen, kw, description)


CATALOG: List[BackgroundSpec] = [
    # --- استوديو ---
    _spec("studio_white", "استوديو أبيض", "studio", bg_studio, "الخلفية القياسية لمتاجر المنتجات", tone="white"),
    _spec("studio_grey", "استوديو رمادي", "studio", bg_studio, "رمادي محايد يبرز الألوان", tone="grey"),
    _spec("studio_dark", "استوديو داكن", "studio", bg_studio, "إضاءة درامية للمنتجات الفخمة", tone="dark"),
    _spec("studio_warm", "استوديو دافئ", "studio", bg_studio, "إضاءة صفراء ناعمة", tone="warm"),
    _spec("studio_cool", "استوديو بارد", "studio", bg_studio, "إضاءة زرقاء نظيفة", tone="cool"),
    # --- تدرّجات ---
    _spec("spot_blue", "بقعة ضوء زرقاء", "gradient", bg_radial_spot, "", color="blue"),
    _spec("spot_teal", "بقعة ضوء فيروزية", "gradient", bg_radial_spot, "", color="teal"),
    _spec("spot_violet", "بقعة ضوء بنفسجية", "gradient", bg_radial_spot, "", color="violet"),
    _spec("spot_amber", "بقعة ضوء كهرمانية", "gradient", bg_radial_spot, "", color="amber"),
    _spec("spot_rose", "بقعة ضوء وردية", "gradient", bg_radial_spot, "", color="rose"),
    _spec("spot_green", "بقعة ضوء خضراء", "gradient", bg_radial_spot, "", color="green"),
    _spec("mesh_sunset", "تدرّج شبكي غروب", "gradient", bg_mesh_gradient, "", palette="sunset"),
    _spec("mesh_ocean", "تدرّج شبكي محيط", "gradient", bg_mesh_gradient, "", palette="ocean"),
    _spec("mesh_forest", "تدرّج شبكي غابة", "gradient", bg_mesh_gradient, "", palette="forest"),
    _spec("mesh_candy", "تدرّج شبكي حلوى", "gradient", bg_mesh_gradient, "", palette="candy"),
    _spec("mesh_mono", "تدرّج شبكي رمادي", "gradient", bg_mesh_gradient, "", palette="mono"),
    # --- خامات ---
    _spec("marble_white", "رخام أبيض", "texture", bg_marble, "خامة فخمة للمجوهرات والعطور", base="white"),
    _spec("marble_black", "رخام أسود", "texture", bg_marble, "", base="black"),
    _spec("marble_gold", "رخام ذهبي", "texture", bg_marble, "", base="gold"),
    _spec("marble_green", "رخام أخضر", "texture", bg_marble, "", base="green"),
    _spec("wood_oak", "خشب بلوط", "texture", bg_wood, "", tone="oak"),
    _spec("wood_walnut", "خشب جوز", "texture", bg_wood, "", tone="walnut"),
    _spec("wood_maple", "خشب قيقب", "texture", bg_wood, "", tone="maple"),
    _spec("wood_ebony", "خشب أبنوس", "texture", bg_wood, "", tone="ebony"),
    _spec("concrete_grey", "خرسانة رمادية", "texture", bg_concrete, "", tone="grey"),
    _spec("concrete_dark", "خرسانة داكنة", "texture", bg_concrete, "", tone="dark"),
    _spec("concrete_sand", "خرسانة رملية", "texture", bg_concrete, "", tone="sand"),
    _spec("linen_natural", "كتان طبيعي", "texture", bg_linen, "", tone="natural"),
    _spec("linen_grey", "كتان رمادي", "texture", bg_linen, "", tone="grey"),
    _spec("paper_kraft", "ورق كرافت", "texture", bg_paper, "مناسب للمنتجات اليدوية", tone="kraft"),
    _spec("paper_white", "ورق أبيض", "texture", bg_paper, "", tone="white"),
    _spec("paper_cream", "ورق كريمي", "texture", bg_paper, "", tone="cream"),
    # --- إبداعية ---
    _spec("bokeh_warm", "بوكيه دافئ", "creative", bg_bokeh, "", palette="warm"),
    _spec("bokeh_cool", "بوكيه بارد", "creative", bg_bokeh, "", palette="cool"),
    _spec("bokeh_pastel", "بوكيه باستيل", "creative", bg_bokeh, "", palette="pastel"),
    _spec("bokeh_neon", "بوكيه نيون", "creative", bg_bokeh, "", palette="neon"),
    _spec("bokeh_gold", "بوكيه ذهبي", "creative", bg_bokeh, "", palette="gold"),
    _spec("geo_triangles", "مثلثات", "creative", bg_geometric, "", style="triangles"),
    _spec("geo_circles", "دوائر", "creative", bg_geometric, "", style="circles"),
    _spec("geo_lines", "خطوط", "creative", bg_geometric, "", style="lines"),
    _spec("water_light", "ماء فاتح", "creative", bg_water, "", tone="light"),
    _spec("water_deep", "ماء عميق", "creative", bg_water, "", tone="deep"),
    _spec("reflect_black", "سطح عاكس أسود", "creative", bg_reflective, "", tone="black"),
    _spec("reflect_white", "سطح عاكس أبيض", "creative", bg_reflective, "", tone="white"),
    # --- باستيل وألوان ---
    _spec("pastel_pink", "باستيل وردي", "color", bg_pastel, "", tone="pink"),
    _spec("pastel_mint", "باستيل نعناعي", "color", bg_pastel, "", tone="mint"),
    _spec("pastel_lavender", "باستيل بنفسجي فاتح", "color", bg_pastel, "", tone="lavender"),
    _spec("pastel_peach", "باستيل خوخي", "color", bg_pastel, "", tone="peach"),
    _spec("pastel_sky", "باستيل سماوي", "color", bg_pastel, "", tone="sky"),
    _spec("pastel_butter", "باستيل زبدي", "color", bg_pastel, "", tone="butter"),
    _spec("solid_light", "سادة فاتح", "color", bg_solid, "", hex_color="#f5f5f5"),
    _spec("solid_black", "سادة أسود", "color", bg_solid, "", hex_color="#111111"),
    _spec("solid_cream", "سادة كريمي", "color", bg_solid, "", hex_color="#f6efe3"),
    _spec("solid_sage", "سادة مريمي", "color", bg_solid, "", hex_color="#cfd8c8"),
    _spec("duo_indigo", "تدرّج نيلي/سماوي", "color", bg_gradient_duo, "", first="#6a5cff", second="#00d4ff"),
    _spec("duo_coral", "تدرّج مرجاني", "color", bg_gradient_duo, "", first="#ff7a59", second="#ffd166"),
    _spec("duo_forest", "تدرّج غابي", "color", bg_gradient_duo, "", first="#0f7a5a", second="#b7e04b"),
]

INDEX: Dict[str, BackgroundSpec] = {s.id: s for s in CATALOG}
CATEGORIES: List[str] = ["studio", "gradient", "texture", "creative", "color"]
CATEGORY_NAMES = {
    "studio": "استوديو", "gradient": "تدرّجات", "texture": "خامات",
    "creative": "إبداعية", "color": "ألوان",
}


# ==============================================================================
#  التوليد والتخزين المؤقت
# ==============================================================================
def _cache_path(bg_id: str, size: int) -> "object":
    from pathlib import Path

    return Path(settings.BG_CACHE_DIR) / f"{bg_id}_{size}.jpg"


def generate_background(bg_id: str, size: Optional[int] = None, use_cache: bool = True) -> Image.Image:
    """توليد خلفية بالمعرّف المطلوب (مع تخزين مؤقت على القرص)."""
    spec = INDEX.get(bg_id)
    if spec is None:
        raise NotFoundError(f"الخلفية «{bg_id}» غير موجودة.", detail={"available": sorted(INDEX)})

    size = int(size or settings.BG_SIZE)
    size = int(np.clip(size, 128, 4096))

    path = _cache_path(bg_id, size)
    if use_cache and settings.cache_enabled:
        try:
            from pathlib import Path

            p = Path(path)
            if p.exists() and p.stat().st_size > 0:
                img = Image.open(p)
                img.load()
                return img.convert("RGB")
        except Exception:
            pass

    arr = spec.generator(size, **spec.kwargs)
    img = from_rgb_array(_vignette(arr, 0.18))

    if use_cache and settings.cache_enabled:
        try:
            from pathlib import Path

            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            img.save(p, "JPEG", quality=90)
        except Exception:
            pass
    return img


def list_backgrounds(category: Optional[str] = None) -> List[Dict[str, str]]:
    """قائمة الخلفيات (اختياريًا حسب الفئة) لعرضها في الواجهة."""
    items = [s for s in CATALOG if not category or s.category == category]
    return [
        {
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "category_name": CATEGORY_NAMES.get(s.category, s.category),
            "description": s.description,
        }
        for s in items
    ]


# ==============================================================================
#  تركيب المنتج على الخلفية
# ==============================================================================
def compose_on_background(
    product: Image.Image,
    background: Image.Image,
    scale: float = 0.62,
    position: str = "center",
    shadow: bool = True,
    reflection: bool = False,
    padding_bottom: float = 0.06,
) -> Image.Image:
    """
    تركيب منتج (يفضَّل أن يكون RGBA بعد إزالة الخلفية) على خلفية المكتبة:
    تحجيم نسبي + ظل واقعي + انعكاس اختياري + محاذاة بصرية.
    """
    prod = product.convert("RGBA")
    bg = background.convert("RGB").copy()
    bw, bh = bg.size

    # التحجيم: أطول ضلع للمنتج = scale × أطول ضلع للخلفية
    target = scale * max(bw, bh)
    ratio = target / max(prod.width, prod.height)
    nw, nh = max(1, int(prod.width * ratio)), max(1, int(prod.height * ratio))
    prod = prod.resize((nw, nh), Image.LANCZOS)

    canvas = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    positions = {
        "center": ((bw - nw) // 2, (bh - nh) // 2 - int(bh * padding_bottom)),
        "bottom": ((bw - nw) // 2, bh - nh - int(bh * padding_bottom * 2)),
        "top": ((bw - nw) // 2, int(bh * padding_bottom)),
    }
    px, py = positions.get(position, positions["center"])

    if shadow:
        alpha = prod.split()[-1]
        sh_layer = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
        black = Image.new("RGBA", (nw, nh), (0, 0, 0, 130))
        sh_layer.paste(black, (0, 0), alpha)
        # ظل مفلطح (Elliptical contact shadow)
        sh_layer = sh_layer.resize((int(nw * 1.0), max(2, int(nh * 0.35))), Image.BILINEAR)
        sh_layer = sh_layer.filter(ImageFilter.GaussianBlur(max(6, nw // 24)))
        canvas.paste(sh_layer, (px, py + nh - sh_layer.height // 2), sh_layer)

    canvas.paste(prod, (px, py), prod)

    if reflection:
        refl = prod.transpose(Image.FLIP_TOP_BOTTOM)
        mask = Image.new("L", refl.size, 0)
        grad = Image.new("L", (1, refl.height), 0)
        for i in range(refl.height):
            grad.putpixel((0, i), int(110 * (1 - i / max(1, refl.height)) ** 1.6))
        mask = grad.resize(refl.size)
        refl.putalpha(mask)
        canvas.paste(refl, (px, py + nh), refl)

    bg_rgba = bg.convert("RGBA")
    out = Image.alpha_composite(bg_rgba, canvas)
    return out.convert("RGB")


__all__ = [
    "CATALOG", "CATEGORIES", "CATEGORY_NAMES", "INDEX", "BackgroundSpec",
    "compose_on_background", "generate_background", "list_backgrounds",
]

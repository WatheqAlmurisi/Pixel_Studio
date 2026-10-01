"""
فحص شامل لنقاط النهاية (End-to-End عبر TestClient).
===================================================
يُولّد صوراً اختبارية حقيقية، ثم يستدعي **كل** نقطة في API ويتحقق من:
  • رمز الاستجابة 200
  • أن الحقل `image` صورة Base64 صالحة يمكن فكّها
  • أن الأبعاد/الصيغة منطقية
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app

client = TestClient(app)

# ------------------------------------------------------------------------------
#  صور اختبارية
# ------------------------------------------------------------------------------
def make_studio(w: int = 480, h: int = 360) -> Image.Image:
    img = Image.new("RGB", (w, h), (246, 246, 248))
    d = ImageDraw.Draw(img)
    for y in range(h):
        v = int(246 - 40 * (y / h))
        d.line([(0, y), (w, y)], fill=(v, v, v + 2))
    d.ellipse([190, 250, 330, 290], fill=(214, 214, 218))
    d.rounded_rectangle([200, 90, 320, 270], radius=22, fill=(198, 42, 52), outline=(120, 20, 28), width=3)
    d.ellipse([225, 115, 295, 165], fill=(255, 226, 180))
    return img


def make_gradient(w: int = 320, h: int = 240) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=(30 + int(120 * y / h), 90 + int(60 * (1 - y / h)), 160 - int(60 * y / h)))
    d.ellipse([110, 40, 220, 190], fill=(250, 240, 220), outline=(60, 50, 40), width=3)
    return img


def make_rgba(w: int = 200, h: int = 200) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([30, 30, 170, 170], fill=(40, 160, 120, 255))
    return img


def b64(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return "data:image/{};base64,{}".format(fmt.lower(), base64.b64encode(buf.getvalue()).decode())


STUDIO = b64(make_studio())
GRADIENT = b64(make_gradient())
RGBA = b64(make_rgba())

RESULTS: List[Tuple[str, str, bool, str]] = []


def call(name: str, method: str, url: str, *, json: Any = None, params: Any = None) -> Dict[str, Any]:
    """استدعاء نقطة نهاية وتسجيل النتيجة مع التحقق من صحة الصورة العائدة."""
    try:
        if method == "GET":
            res = client.get(url, params=params)
        else:
            res = client.post(url, json=json)
        if res.status_code != 200:
            RESULTS.append((name, url, False, f"HTTP {res.status_code}: {res.text[:160]}"))
            return {}
        data = res.json()
        if "image" in data:
            raw = base64.b64decode(data["image"])
            img = Image.open(io.BytesIO(raw))
            img.load()
            meta = data.get("meta", {})
            if img.size[0] < 1 or img.size[1] < 1:
                RESULTS.append((name, url, False, "أبعاد غير صالحة"))
                return data
            if meta and (meta.get("width") != img.width or meta.get("height") != img.height):
                RESULTS.append((name, url, False,
                                f"عدم تطابق meta {meta.get('width')}x{meta.get('height')} مع {img.size}"))
                return data
        RESULTS.append((name, url, True, f"{res.status_code} {img.size if 'image' in data else ''}"))
        return data
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, url, False, f"{type(exc).__name__}: {exc}"))
        return {}


def run_all() -> int:
    """تنفيذ الفحص على كل النقاط."""
    P = "/api/v1"

    # --- النظام ---
    r = client.get(f"{P}/health")
    RESULTS.append(("health", f"{P}/health", r.status_code == 200 and r.json().get("status") == "ok",
                    f"{r.status_code}"))
    r = client.get(f"{P}")
    RESULTS.append(("api_index", f"{P}", r.status_code == 200 and r.json().get("total_endpoints", 0) > 50,
                    f"{r.status_code} endpoints={r.json().get('total_endpoints')}"))
    r = client.get(f"{P}/convert/formats")
    RESULTS.append(("formats", f"{P}/convert/formats", r.status_code == 200, f"{r.status_code}"))
    r = client.get("/api/docs")
    RESULTS.append(("swagger_ui", "/api/docs", r.status_code == 200, f"{r.status_code}"))
    r = client.get("/api/openapi.json")
    RESULTS.append(("openapi", "/api/openapi.json", r.status_code == 200, f"{r.status_code}"))
    r = client.get("/")
    RESULTS.append(("frontend_index", "/", r.status_code in (200, 503), f"{r.status_code}"))

    # --- تحويل الصيغ ---
    for fmt in ["png", "jpeg", "webp", "bmp", "tiff", "gif", "ico", "avif", "ppm"]:
        call(f"convert:{fmt}", "POST", f"{P}/convert",
             json={"image": STUDIO, "format": fmt, "quality": 85})
    call("convert:alpha→jpeg", "POST", f"{P}/convert",
         json={"image": RGBA, "format": "jpeg", "background": "#101010"})
    call("convert:keep_exif", "POST", f"{P}/convert",
         json={"image": STUDIO, "format": "jpeg", "keep_exif": True})

    # --- الهندسي ---
    call("crop", "POST", f"{P}/geometry/crop", json={"image": STUDIO, "box": [50, 40, 200, 160]})
    call("crop:ratio", "POST", f"{P}/geometry/crop",
         json={"image": STUDIO, "box": [0.1, 0.1, 0.5, 0.5], "unit": "ratio"})
    for aspect in ["1:1", "4:3", "16:9", "9:16", "3:2"]:
        call(f"crop-aspect:{aspect}", "POST", f"{P}/geometry/crop-aspect",
             json={"image": STUDIO, "aspect": aspect, "anchor": "center"})
    call("crop-auto", "POST", f"{P}/geometry/crop-auto", json={"image": STUDIO, "tolerance": 10})
    call("crop-content", "POST", f"{P}/geometry/crop-content", json={"image": RGBA, "padding": 6})
    call("resize:fit", "POST", f"{P}/geometry/resize", json={"image": STUDIO, "width": 300, "height": 300})
    call("resize:fill", "POST", f"{P}/geometry/resize",
         json={"image": STUDIO, "width": 200, "height": 200, "mode": "fill"})
    call("resize:exact", "POST", f"{P}/geometry/resize",
         json={"image": STUDIO, "width": 400, "height": 120, "mode": "exact"})
    call("resize:percent", "POST", f"{P}/geometry/resize", json={"image": STUDIO, "percent": 45})
    call("resize:longest", "POST", f"{P}/geometry/resize", json={"image": STUDIO, "width": 600, "mode": "longest"})
    for resample in ["lanczos", "bicubic", "bilinear", "nearest", "box"]:
        call(f"resize:{resample}", "POST", f"{P}/geometry/resize",
             json={"image": STUDIO, "width": 240, "resample": resample})
    for angle in [15, -37, 90, 180]:
        call(f"rotate:{angle}", "POST", f"{P}/geometry/rotate", json={"image": STUDIO, "angle": angle})
    for times in [1, 2, 3]:
        call(f"rotate90:{times}", "POST", f"{P}/geometry/rotate90", json={"image": STUDIO, "times": times})
    for direction in ["horizontal", "vertical"]:
        call(f"flip:{direction}", "POST", f"{P}/geometry/flip", json={"image": STUDIO, "direction": direction})
    for mode in ["transpose", "transverse", "rotate_90", "rotate_180", "rotate_270"]:
        call(f"transpose:{mode}", "POST", f"{P}/geometry/transpose", json={"image": STUDIO, "mode": mode})
    call("straighten", "POST", f"{P}/geometry/straighten", json={"image": STUDIO, "angle": 3.5})
    call("deskew", "POST", f"{P}/geometry/deskew", json={"image": STUDIO})
    call("perspective", "POST", f"{P}/geometry/perspective",
         json={"image": STUDIO,
               "src": [[0, 0], [1, 0], [1, 1], [0, 1]],
               "dst": [[0.08, 0.04], [0.96, 0.02], [1, 0.94], [0.02, 1]]})
    call("pad", "POST", f"{P}/geometry/pad", json={"image": STUDIO, "top": 20, "right": 30, "bottom": 20, "left": 30})
    call("pad:percent", "POST", f"{P}/geometry/pad", json={"image": STUDIO, "percent": 8, "color": "#eee"})
    for style in ["solid", "double", "shadow", "polaroid", "rounded"]:
        call(f"border:{style}", "POST", f"{P}/geometry/border",
             json={"image": STUDIO, "width": 14, "style": style, "color": "#222"})
    call("shadow", "POST", f"{P}/geometry/shadow", json={"image": RGBA, "opacity": 0.6, "blur_radius": 10})
    for mode in ["contain", "cover", "stretch"]:
        call(f"canvas:{mode}", "POST", f"{P}/geometry/canvas",
             json={"image": STUDIO, "width": 600, "height": 400, "mode": mode})

    # --- البكسل ---
    call("adjust:full", "POST", f"{P}/pixel/adjust",
         json={"image": STUDIO, "brightness": 12, "contrast": 18, "saturation": 20,
               "temperature": 8, "gamma": 1.08, "vibrance": 15, "exposure": 0.3})
    call("adjust:levels", "POST", f"{P}/pixel/adjust",
         json={"image": STUDIO, "levels": {"in_black": 0.06, "in_white": 0.94, "gamma": 1.2}})
    call("adjust:curves", "POST", f"{P}/pixel/adjust",
         json={"image": STUDIO, "curves": [[0, 0], [0.35, 0.28], [0.7, 0.78], [1, 1]]})
    call("adjust:posterize", "POST", f"{P}/pixel/adjust", json={"image": STUDIO, "posterize_levels": 5})
    call("adjust:grayscale", "POST", f"{P}/pixel/adjust", json={"image": STUDIO, "grayscale": True})
    call("adjust:invert", "POST", f"{P}/pixel/adjust", json={"image": STUDIO, "invert": True})
    call("adjust:channel_mixer", "POST", f"{P}/pixel/adjust",
         json={"image": STUDIO, "channel_mixer": [[1.1, 0, 0], [0, 1, 0], [0, 0, 0.9]]})
    call("adjust:color_balance", "POST", f"{P}/pixel/adjust",
         json={"image": STUDIO, "color_balance": {"shadows": [-8, 0, 8], "midtones": [0, 4, 0], "highlights": [6, 0, -6]}})
    call("adjust:auto", "POST", f"{P}/pixel/adjust", json={"image": STUDIO, "auto_levels": True, "auto_contrast": True})
    call("curves", "POST", f"{P}/pixel/curves",
         json={"image": STUDIO, "points": [[0, 0], [0.5, 0.62], [1, 1]], "channel": "rgb"})
    call("curves:red", "POST", f"{P}/pixel/curves",
         json={"image": STUDIO, "points": [[0, 0.1], [1, 1]], "channel": "r"})
    call("levels", "POST", f"{P}/pixel/levels", json={"image": STUDIO, "in_black": 0.05, "in_white": 0.95, "gamma": 0.9})
    for mode in ["binary", "binary_inv", "otsu", "adaptive", "tozero", "trunc"]:
        call(f"threshold:{mode}", "POST", f"{P}/pixel/threshold", json={"image": STUDIO, "mode": mode})
    call("threshold:color", "POST", f"{P}/pixel/threshold", json={"image": STUDIO, "mode": "otsu", "color": True})
    call("auto-levels", "POST", f"{P}/pixel/auto-levels", json={"image": STUDIO})
    call("auto-contrast", "POST", f"{P}/pixel/auto-contrast", json={"image": STUDIO})
    for wb in ["grayworld", "whitepatch"]:
        call(f"white-balance:{wb}", "POST", f"{P}/pixel/white-balance", json={"image": STUDIO, "white_balance": wb})
    call("black-white", "POST", f"{P}/pixel/black-white", json={"image": STUDIO, "params": {"mix": [0.3, 0.59, 0.11]}})
    call("split-toning", "POST", f"{P}/pixel/split-toning",
         json={"image": STUDIO, "name": "split", "params": {"shadow_hue": 210, "highlight_hue": 40}})
    call("selective-color", "POST", f"{P}/pixel/selective-color",
         json={"image": STUDIO, "name": "sel", "params": {"hue": 8, "width": 70, "scale": 0.7}})
    call("posterize", "POST", f"{P}/pixel/posterize", json={"image": STUDIO, "name": "p", "params": {"levels": 6}})
    call("invert", "POST", f"{P}/pixel/invert", json={"image": STUDIO})
    call("grayscale", "POST", f"{P}/pixel/grayscale", json={"image": STUDIO})

    # --- الفلاتر ---
    for mode in ["gaussian", "box", "motion", "radial_zoom", "radial_spin", "surface", "bilateral", "nlmeans"]:
        call(f"blur:{mode}", "POST", f"{P}/filters/blur", json={"image": STUDIO, "mode": mode, "radius": 4})
    call("surface-smooth", "POST", f"{P}/filters/surface-smooth", json={"image": STUDIO, "strength": 1.2, "detail": 0.4})
    for mode in ["unsharp", "highpass", "laplacian", "detail"]:
        call(f"sharpen:{mode}", "POST", f"{P}/filters/sharpen", json={"image": STUDIO, "mode": mode, "amount": 1.1})
    for mode in ["nlmeans", "median", "bilateral"]:
        call(f"denoise:{mode}", "POST", f"{P}/filters/denoise", json={"image": STUDIO, "mode": mode})
    call("edges", "POST", f"{P}/filters/edges", json={"image": STUDIO, "low": 40, "high": 130})
    call("sobel", "POST", f"{P}/filters/sobel", json={"image": STUDIO, "name": "s", "params": {"scale": 1.2}})
    call("emboss", "POST", f"{P}/filters/emboss", json={"image": STUDIO, "name": "e", "params": {"strength": 1.2}})
    call("oil-paint", "POST", f"{P}/filters/oil-paint", json={"image": STUDIO, "radius": 5})
    call("sketch", "POST", f"{P}/filters/sketch", json={"image": STUDIO, "threshold": 7})
    call("pencil-color", "POST", f"{P}/filters/pencil-color", json={"image": STUDIO, "sigma": 0.06})
    call("halftone", "POST", f"{P}/filters/halftone", json={"image": STUDIO, "dot_size": 7})
    call("halftone:color", "POST", f"{P}/filters/halftone", json={"image": STUDIO, "dot_size": 8, "color": True})
    call("pixelate", "POST", f"{P}/filters/pixelate", json={"image": STUDIO, "block": 14})
    call("vignette", "POST", f"{P}/filters/vignette", json={"image": STUDIO, "strength": 0.7})
    call("grain", "POST", f"{P}/filters/grain", json={"image": STUDIO, "amount": 0.3})
    call("glow", "POST", f"{P}/filters/glow", json={"image": STUDIO, "amount": 0.5})
    call("hdr", "POST", f"{P}/filters/hdr", json={"image": STUDIO, "name": "h", "params": {"strength": 0.8}})
    call("filters/apply", "POST", f"{P}/filters/apply", json={"image": STUDIO, "name": "emboss", "params": {"strength": 1}})
    call("filters/catalog", "GET", f"{P}/filters/catalog")

    # --- إزالة الخلفية ---
    call("seg/methods", "GET", f"{P}/segmentation/methods")
    for method in ["auto", "grabcut", "color_key", "flood_fill", "edge_cut", "kmeans"]:
        data = call(f"remove-bg:{method}", "POST", f"{P}/segmentation/remove-background",
                    json={"image": STUDIO, "method": method, "feather": 1.5})
        if data:
            img = Image.open(io.BytesIO(base64.b64decode(data["image"])))
            RESULTS.append((f"remove-bg:{method}:RGBA", "…", img.mode == "RGBA", img.mode))
    call("remove-bg:crop", "POST", f"{P}/segmentation/remove-background",
         json={"image": STUDIO, "method": "flood_fill", "crop_to_content": True})
    call("preview-mask", "POST", f"{P}/segmentation/preview-mask", json={"image": STUDIO, "method": "auto"})
    # قناع يدوي
    mask = Image.new("L", (480, 360), 0)
    ImageDraw.Draw(mask).ellipse([200, 90, 320, 270], fill=255)
    call("apply-mask", "POST", f"{P}/segmentation/mask", json={"image": STUDIO, "mask": b64(mask, "PNG")})

    # تلميحات يدوية + Matting: تحقق دقة فعلي (الجسم يبقى والخلفية تُحذف)
    hint = Image.new("L", (480, 360), 0)
    ImageDraw.Draw(hint).ellipse([250, 170, 270, 190], fill=255)   # نقطة جسم في مركز الصندوق الأحمر
    data = call("remove-bg:hints-precise", "POST", f"{P}/segmentation/remove-background",
                json={"image": STUDIO, "method": "grabcut", "hint_mask": b64(hint, "PNG"),
                      "iterations": 12, "matte": True, "feather": 1.0})
    if data:
        img = Image.open(io.BytesIO(base64.b64decode(data["image"]))).convert("RGBA")
        a_fg = img.getpixel((260, 180))[3]
        a_bg = img.getpixel((10, 10))[3]
        RESULTS.append(("remove-bg:hints-keeps-subject", "alpha@hint", a_fg > 150, f"alpha={a_fg}"))
        RESULTS.append(("remove-bg:hints-drops-bg", "alpha@corner", a_bg < 60, f"alpha={a_bg}"))
    data = call("remove-bg:matte-off", "POST", f"{P}/segmentation/remove-background",
                json={"image": STUDIO, "method": "grabcut", "matte": False})
    if data:
        img = Image.open(io.BytesIO(base64.b64decode(data["image"])))
        RESULTS.append(("remove-bg:matte-off:RGBA", "…", img.mode == "RGBA", img.mode))

    # العصا السحرية: نقرة داخل الصندوق الأحمر ⇒ يُنتقى الصندوق وتُحذف الخلفية
    data = call("remove-bg:wand", "POST", f"{P}/segmentation/remove-background",
                json={"image": STUDIO, "method": "wand", "seeds": [[260, 180, 1]],
                      "wand_tolerance": 36, "iterations": 10, "matte": True, "feather": 1.0})
    if data:
        img = Image.open(io.BytesIO(base64.b64decode(data["image"]))).convert("RGBA")
        a_fg = img.getpixel((260, 180))[3]
        a_bg = img.getpixel((10, 10))[3]
        RESULTS.append(("remove-bg:wand-keeps-subject", "alpha@seed", a_fg > 150, f"alpha={a_fg}"))
        RESULTS.append(("remove-bg:wand-drops-bg", "alpha@corner", a_bg < 60, f"alpha={a_bg}"))

    # العصا مع بذرة خلفية (Shift+نقرة): لا تفسد النتيجة
    data = call("remove-bg:wand-bg-seed", "POST", f"{P}/segmentation/remove-background",
                json={"image": STUDIO, "method": "wand",
                      "seeds": [[260, 180, 1], [10, 10, 0]], "wand_tolerance": 36})
    if data:
        img = Image.open(io.BytesIO(base64.b64decode(data["image"]))).convert("RGBA")
        a_fg = img.getpixel((260, 180))[3]
        RESULTS.append(("remove-bg:wand-bg-seed-keeps-subject", "alpha@seed", a_fg > 150, f"alpha={a_fg}"))

    # العصا الذكية: بذور تلقائية بلا نقر
    data = call("remove-bg:smart", "POST", f"{P}/segmentation/remove-background",
                json={"image": STUDIO, "method": "smart"})
    if data:
        img = Image.open(io.BytesIO(base64.b64decode(data["image"])))
        RESULTS.append(("remove-bg:smart:RGBA", "…", img.mode == "RGBA", img.mode))
        RESULTS.append(("remove-bg:smart-has-fg", "fg_ratio",
                        float(data.get("foreground_ratio", 0)) > 0.02, data.get("foreground_ratio")))

    # معاينة قناع العصا (استجابة سريعة بلا معالجة لاحقة ثقيلة)
    call("preview-mask:wand", "POST", f"{P}/segmentation/preview-mask",
         json={"image": STUDIO, "method": "wand", "seeds": [[260, 180, 1]], "wand_tolerance": 36})

    # العصا بلا بذور ⇒ خطأ معلمة صالح (400)
    r = client.post(f"{P}/segmentation/remove-background", json={"image": STUDIO, "method": "wand"})
    RESULTS.append(("error:wand-no-seeds", "…", r.status_code == 400, f"{r.status_code}"))

    # تسامح العصا خارج المدى المسموح ⇒ رفض تحقق (422)
    r = client.post(f"{P}/segmentation/remove-background",
                    json={"image": STUDIO, "method": "wand", "seeds": [[260, 180, 1]],
                          "wand_tolerance": 500})
    RESULTS.append(("error:wand-tolerance-range", "…", r.status_code == 422, f"{r.status_code}"))

    # --- الترميم والتنقيح والمستندات ---
    # صورة «قديمة» صناعية: باهتة + خدش ساطع + غبار
    import numpy as _np
    from PIL import Image as _Image
    _a = _np.full((240, 320, 3), 150, _np.uint8)
    _a[50:190, 60:260] = (120, 100, 80)
    _a = (_a.astype(_np.int16) * 0.75 + 45).astype(_np.uint8)   # بهتان
    _a[30:210, 150] = (235, 230, 220)                           # خدش رأسي
    _g = _np.random.default_rng(7)
    _a[_g.integers(0, 240, 60), _g.integers(0, 320, 60)] = (240, 235, 225)  # غبار
    OLD = b64(_Image.fromarray(_a))
    data = call("pro/restore", "POST", f"{P}/pro/restore-old-photo",
                json={"image": OLD, "scratches": True, "dust": True, "recolor": True,
                      "denoise": 0.5, "sharpen": 0.4})
    if data:
        img = Image.open(io.BytesIO(base64.b64decode(data["image"]))).convert("RGB")
        arr = np.array(img)
        # الخدش الساطع (كان ~235) يجب أن يخبو بعد الترميم
        scratch_after = float(arr[120, 150].mean())
        RESULTS.append(("pro/restore:scratch-dimmed", "سطوع الخدش",
                        scratch_after < 210, f"بعد={scratch_after:.0f}"))
        RESULTS.append(("pro/restore:stats", "defect_pixels",
                        int(data.get("defect_pixels", 0)) > 0, str(data.get("defect_pixels"))))
    call("pro/restore:opts-off", "POST", f"{P}/pro/restore-old-photo",
         json={"image": OLD, "scratches": False, "dust": False, "recolor": False,
               "denoise": 0, "sharpen": 0})

    # تنقيح الوجوه: يعيد عدد الوجوه (الصورة الصناعية بلا وجوه حقيقية ⇒ 0 بلا خطأ)
    data = call("pro/retouch", "POST", f"{P}/pro/retouch-faces",
                json={"image": STUDIO, "smooth": 0.6, "blemish": True, "redeye": True})
    if data:
        img = Image.open(io.BytesIO(base64.b64decode(data["image"])))
        RESULTS.append(("pro/retouch:RGBA-valid", "…", img.width > 0, img.size))
        RESULTS.append(("pro/retouch:faces-field", "faces>=0",
                        int(data.get("faces", -1)) >= 0, str(data.get("faces"))))
    call("pro/retouch:no-redeye", "POST", f"{P}/pro/retouch-faces",
         json={"image": STUDIO, "redeye": False, "blemish": False})

    # مستند صناعي: ورقة فاتحة مائلة على خلفية داكنة مع أسطر نص
    _doc = _np.full((400, 500, 3), 40, _np.uint8)
    _quad = _np.array([[90, 70], [430, 55], [450, 340], [70, 355]], _np.float32)
    import cv2 as _cv2
    _cv2.fillPoly(_doc, [_quad.astype(_np.int32)], (235, 235, 230))
    _M = _cv2.getPerspectiveTransform(
        _np.array([[0, 0], [339, 0], [339, 259], [0, 259]], _np.float32), _quad)
    _txt = _np.full((260, 340), 255, _np.uint8)
    for _y in range(30, 240, 28):
        _cv2.putText(_txt, "DOCUMENT TEXT LINE", (10, _y), _cv2.FONT_HERSHEY_SIMPLEX, 0.6, 60, 2)
    _wt = _cv2.warpPerspective(_txt, _M, (500, 400))
    _doc[_wt < 200] = (60, 60, 90)
    DOC = b64(_Image.fromarray(_doc))
    data = call("pro/document:bw", "POST", f"{P}/pro/document-scan",
                json={"image": DOC, "mode": "bw", "perspective": True})
    if data:
        img = Image.open(io.BytesIO(base64.b64decode(data["image"]))).convert("L")
        arr = np.array(img)
        # بعد الأعتاب الثنائي: البكسلات إما قريبة من 0 أو 255
        bimodal = float(((arr < 40) | (arr > 215)).mean())
        RESULTS.append(("pro/document:bw-bimodal", "بكسلات ثنائية",
                        bimodal > 0.85, f"{bimodal:.2f}"))
        RESULTS.append(("pro/document:perspective", "منظور مطبق",
                        bool(data.get("perspective_applied")), str(data.get("perspective_applied"))))
    for mode in ("enhance", "color"):
        call(f"pro/document:{mode}", "POST", f"{P}/pro/document-scan",
             json={"image": DOC, "mode": mode})
    call("pro/document:no-persp", "POST", f"{P}/pro/document-scan",
         json={"image": DOC, "mode": "bw", "perspective": False})
    r = client.post(f"{P}/pro/document-scan", json={"image": DOC, "mode": "ultra"})
    RESULTS.append(("error:document-bad-mode", "…", r.status_code == 422, f"{r.status_code}"))

    # --- الدمج ---
    call("blend-modes", "GET", f"{P}/composite/blend-modes")
    for mode in ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color_dodge",
                 "color_burn", "hard_light", "soft_light", "difference", "exclusion",
                 "hue", "saturation", "color", "luminosity", "linear_light", "pin_light", "hard_mix"]:
        call(f"blend:{mode}", "POST", f"{P}/composite/blend",
             json={"image": STUDIO, "second": GRADIENT, "mode": mode, "opacity": 0.75})
    call("blend:pos", "POST", f"{P}/composite/blend",
         json={"image": STUDIO, "second": GRADIENT, "x": 0.25, "y": 0.3, "scale": 0.5})
    call("blend-seamless", "POST", f"{P}/composite/blend-seamless",
         json={"image": STUDIO, "second": GRADIENT, "levels": 5, "feather": 25})
    call("blend-seamless:mask", "POST", f"{P}/composite/blend-seamless",
         json={"image": STUDIO, "second": GRADIENT, "mask": b64(mask, "PNG"), "levels": 4})
    for layout in ["horizontal", "vertical", "grid", "stacked"]:
        call(f"merge:{layout}", "POST", f"{P}/composite/merge",
             json={"images": [STUDIO, GRADIENT, RGBA], "layout": layout, "gap": 8})
    call("pip", "POST", f"{P}/composite/pip", json={"image": STUDIO, "second": GRADIENT, "size": 0.3})
    call("watermark-text", "POST", f"{P}/composite/watermark-text",
         json={"image": STUDIO, "text": "استوديو بكسل © 2026", "font_size": 30, "opacity": 0.6})
    call("watermark-text:tile", "POST", f"{P}/composite/watermark-text",
         json={"image": STUDIO, "text": "© Demo", "tile": True, "angle": -28, "opacity": 0.18})
    call("watermark-image", "POST", f"{P}/composite/watermark-image",
         json={"image": STUDIO, "second": RGBA, "size": 0.2})

    # --- الإبداعية ---
    call("creative/catalog", "GET", f"{P}/creative/catalog")
    for name, params in [
        ("glitch", {"amount": 0.8}), ("duotone", {"dark": "#101830", "light": "#ffd166"}),
        ("vintage", {"strength": 1}), ("cinematic", {"strength": 1}),
        ("light_leak", {"hue": 28, "amount": 0.5}), ("frame", {"style": "cinema"}),
        ("lens_blur", {"radius": 12}), ("bokeh", {"count": 20}),
        ("mirror", {"axis": "vertical"}), ("kaleidoscope", {"segments": 6}),
        ("color_shift", {"first": "#ff0080", "second": "#7928ca", "mode": "color"}),
        ("ascii", {"cell": 10}), ("thermal", {}), ("night_vision", {}),
        ("pop_art", {"levels": 4}), ("sepia", {}), ("cross_process", {}),
    ]:
        call(f"creative:{name}", "POST", f"{P}/creative/apply",
             json={"image": STUDIO, "name": name, "params": params})
    call("double-exposure", "POST", f"{P}/creative/double-exposure",
         json={"image": STUDIO, "second": GRADIENT, "amount": 0.5})

    # --- الخلفيات ---
    listing = call("backgrounds:list", "GET", f"{P}/backgrounds")
    ids = [i["id"] for i in listing.get("items", [])]
    RESULTS.append(("backgrounds:count>=40", "…", len(ids) >= 40, f"{len(ids)} خلفية"))
    for bg_id in ids[:8]:
        r = client.get(f"{P}/backgrounds/preview/{bg_id}", params={"size": 128})
        RESULTS.append((f"bg-preview:{bg_id}", "…", r.status_code == 200 and r.headers.get("content-type") == "image/jpeg",
                        f"{r.status_code}"))
    call("backgrounds:generate", "POST", f"{P}/backgrounds/generate",
         json={"background": "marble_white", "size": 600})
    for bg_id in ["studio_white", "marble_black", "bokeh_warm", "wood_oak", "pastel_pink"]:
        call(f"compose:{bg_id}", "POST", f"{P}/backgrounds/compose",
             json={"image": RGBA, "background": bg_id, "size": 700, "scale": 0.6, "shadow": True})

    # --- التحليل ---
    data = call("analysis", "POST", f"{P}/analysis", json={"image": STUDIO})
    if data:
        RESULTS.append(("analysis:fields", "…",
                        all(k in data for k in ("mean_brightness", "entropy_bits", "dominant_colors", "suggestions")),
                        "الحقول كاملة" if data else ""))
    call("analysis/colors", "POST", f"{P}/analysis/colors", json={"image": STUDIO, "name": "c", "params": {"k": 5}})
    call("analysis/suggestions", "POST", f"{P}/analysis/suggestions", json={"image": STUDIO})

    # --- السلاسل والدفعات ---
    call("pipeline/operations", "GET", f"{P}/pipeline/operations")
    call("pipeline/run", "POST", f"{P}/pipeline/run", json={
        "image": STUDIO,
        "steps": [
            {"op": "remove_bg", "method": "auto", "feather": 1.5},
            {"op": "adjust", "brightness": 6, "contrast": 12, "saturation": 12},
            {"op": "sharpen", "amount": 0.8},
            {"op": "background", "background": "marble_white", "scale": 0.55},
            {"op": "resize", "width": 700, "height": 700, "mode": "fit"},
            {"op": "watermark", "text": "متجري", "font_size": 26, "opacity": 0.45},
            {"op": "creative", "name": "cinematic", "params": {"strength": 0.6}},
        ],
    })
    call("pipeline/batch", "POST", f"{P}/pipeline/batch", json={
        "images": [STUDIO, GRADIENT, RGBA],
        "names": ["منتج.png", "خلفية.png", "شعار.png"],
        "steps": [{"op": "resize", "width": 200, "height": 200}, {"op": "adjust", "contrast": 10}, {"op": "flip"}],
        "format": "webp", "quality": 82,
    })

    # --- التنزيل ---
    r = client.post(f"{P}/download", json={"image": STUDIO, "filename": "test.webp", "format": "webp", "quality": 85})
    ok = r.status_code == 200 and r.headers.get("content-type") == "image/webp" and "attachment" in r.headers.get("content-disposition", "")
    RESULTS.append(("download", f"{P}/download", ok, f"{r.status_code} {r.headers.get('content-disposition','')[:40]}"))

    # --- معالجة الأخطاء ---
    r = client.post(f"{P}/convert", json={"image": "not-base64-at-all!!!", "format": "png"})
    RESULTS.append(("error:bad_base64", "…", r.status_code == 422 and r.json()["error"]["code"] == "image_decode_error",
                    f"{r.status_code} {r.json().get('error',{}).get('code')}"))
    r = client.post(f"{P}/convert", json={"image": STUDIO, "format": "psd"})
    RESULTS.append(("error:bad_format", "…", r.status_code == 415, f"{r.status_code}"))
    r = client.post(f"{P}/pixel/adjust", json={"image": STUDIO, "brightness": 5000})
    RESULTS.append(("error:validation", "…", r.status_code == 422, f"{r.status_code}"))
    r = client.post(f"{P}/geometry/crop", json={"image": STUDIO, "box": [0, 0, 0, 0]})
    RESULTS.append(("error:empty_crop", "…", r.status_code in (400, 422), f"{r.status_code}"))
    r = client.post(f"{P}/composite/blend", json={"image": STUDIO, "second": GRADIENT, "mode": "not_a_mode"})
    RESULTS.append(("error:bad_blend_mode", "…", r.status_code == 400, f"{r.status_code}"))
    r = client.get(f"{P}/backgrounds/preview/does_not_exist")
    RESULTS.append(("error:missing_bg", "…", r.status_code == 404, f"{r.status_code}"))
    r = client.post(f"{P}/pipeline/run", json={"image": STUDIO, "steps": [{"op": "unknown_op"}]})
    RESULTS.append(("error:unknown_op", "…", r.status_code == 400, f"{r.status_code}"))

    # --- التقرير ---
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r[2])
    print("\n" + "=" * 78)
    print(f"نتيجة فحص نقاط النهاية: {passed}/{total} ناجح")
    print("=" * 78)
    failed = [r for r in RESULTS if not r[2]]
    if failed:
        print("\n❌ النقاط الفاشلة:")
        for name, url, _, msg in failed:
            print(f"   • {name:<34} {msg}")
    else:
        print("\n✅ كل النقاط ناجحة.")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(run_all())

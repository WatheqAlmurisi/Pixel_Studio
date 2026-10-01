"""
تحليل الصورة: مدرّج تكراري، مقاييس جودة، بيانات وصفية، ألوان سائدة.
===================================================================
يُستخدم في الواجهة لعرض معلومات تشخيصية تساعد المستخدم على قرارات التحرير.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from ..core.helpers import luminance, to_rgb_array

EXIF_TAGS: Dict[int, str] = {
    271: "make", 272: "model", 274: "orientation", 282: "x_resolution", 283: "y_resolution",
    305: "software", 306: "datetime", 315: "artist", 33432: "copyright",
    34665: "exif_ifd", 36867: "datetime_original", 36868: "datetime_digitized",
    37377: "shutter_speed", 37378: "aperture", 37380: "exposure_bias",
    37381: "max_aperture", 37383: "metering_mode", 37384: "light_source",
    37385: "flash", 37386: "focal_length", 37396: "subject_area",
    41986: "exposure_mode", 41987: "white_balance", 41990: "scene_capture_type",
    42240: "gamma", 33434: "exposure_time", 34855: "iso",
}


def histogram(img: Image.Image, bins: int = 64) -> Dict[str, Any]:
    """مدرّج تكراري لكل قناة + الإضاءة (مُطبَّع إلى [0,1] للعرض)."""
    bins = int(np.clip(bins, 8, 256))
    arr = to_rgb_array(img).astype(np.uint8)
    result: Dict[str, Any] = {"bins": bins, "channels": {}}

    for idx, name in enumerate(["red", "green", "blue"]):
        hist, _ = np.histogram(arr[..., idx], bins=bins, range=(0, 256))
        hist = hist.astype(np.float32)
        peak = float(hist.max()) if hist.size and hist.max() > 0 else 1.0
        result["channels"][name] = (hist / peak).round(4).tolist()

    lum = luminance(arr).astype(np.uint8)
    hist, _ = np.histogram(lum, bins=bins, range=(0, 256))
    hist = hist.astype(np.float32)
    peak = float(hist.max()) if hist.size and hist.max() > 0 else 1.0
    result["channels"]["luminance"] = (hist / peak).round(4).tolist()
    return result


def image_stats(img: Image.Image) -> Dict[str, Any]:
    """مقاييس إحصائية: الإضاءة، التباين، التشبّع، الإنتروبيا، الحِدّة، والألوان الباهتة/المحروقة."""
    arr = to_rgb_array(img).astype(np.float32)
    gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2HSV)

    lum = gray.astype(np.float32)
    mean_lum = float(lum.mean())
    contrast = float(lum.std())

    # الإنتروبيا (مقياس تعقيد المعلومات في الصورة)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel()
    probs = hist / max(hist.sum(), 1)
    probs = probs[probs > 0]
    entropy = float(-(probs * np.log2(probs)).sum())

    # الحِدّة عبر تباين استجابة لابلاس (كلما زاد ⇒ صورة أحدّ)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # ضبابية تقديرية: نسبة الحواف الضعيفة
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(edges.mean() / 255.0)

    sat = hsv[..., 1].astype(np.float32)
    return {
        "width": img.width,
        "height": img.height,
        "megapixels": round(img.width * img.height / 1_000_000, 3),
        "aspect_ratio": round(img.width / max(1, img.height), 4),
        "mean_brightness": round(mean_lum, 2),
        "brightness_percent": round(mean_lum / 255 * 100, 1),
        "contrast_std": round(contrast, 2),
        "dynamic_range": round(float(lum.max() - lum.min()), 2),
        "entropy_bits": round(entropy, 3),
        "sharpness_laplacian_var": round(sharpness, 1),
        "edge_density": round(edge_density, 4),
        "mean_saturation": round(float(sat.mean()), 2),
        "clipped_shadows_percent": round(float((gray <= 4).mean() * 100), 2),
        "clipped_highlights_percent": round(float((gray >= 251).mean() * 100), 2),
        "is_blurry_estimate": bool(sharpness < 60),
        "is_dark_estimate": bool(mean_lum < 70),
        "is_bright_estimate": bool(mean_lum > 200),
    }


def dominant_colors(img: Image.Image, k: int = 6) -> List[Dict[str, Any]]:
    """استخراج الألوان السائدة عبر K-Means مع نسبتها في الصورة."""
    k = int(np.clip(k, 1, 12))
    arr = to_rgb_array(img).astype(np.uint8)
    small = cv2.resize(arr, (min(arr.shape[1], 160), max(1, int(arr.shape[0] * 160 / max(1, arr.shape[1])))),
                       interpolation=cv2.INTER_AREA)
    pixels = small.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)

    counts = np.bincount(labels.flatten(), minlength=k).astype(np.float32)
    order = np.argsort(-counts)
    total = counts.sum()
    out: List[Dict[str, Any]] = []
    for i in order:
        if counts[i] == 0:
            continue
        r, g, b = (int(round(v)) for v in centers[i])
        out.append({
            "rgb": [r, g, b],
            "hex": "#{:02x}{:02x}{:02x}".format(r, g, b),
            "percent": round(float(counts[i] / total * 100), 2),
        })
    return out


def color_palette_image(img: Image.Image, k: int = 6, height: int = 64) -> Image.Image:
    """إنشاء صورة شريط الألوان السائدة (للعرض في الواجهة)."""
    colors = dominant_colors(img, k)
    if not colors:
        return Image.new("RGB", (k * 40, height), (200, 200, 200))
    total_w = 40 * len(colors)
    out = Image.new("RGB", (total_w, height))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(out)
    for i, c in enumerate(colors):
        draw.rectangle([i * 40, 0, (i + 1) * 40, height], fill=tuple(c["rgb"]))
    return out


def channel_histogram_image(img: Image.Image, width: int = 320, height: int = 120) -> Image.Image:
    """رسم المدرّج التكراري كصورة (للاستخدام في التقرير والواجهة)."""
    from PIL import ImageDraw

    hist = histogram(img, bins=64)["channels"]
    canvas = Image.new("RGB", (width, height), (18, 20, 26))
    draw = ImageDraw.Draw(canvas, "RGBA")
    colors = {"red": (255, 70, 70), "green": (80, 220, 120), "blue": (90, 150, 255),
              "luminance": (230, 230, 230)}
    for name, color in colors.items():
        values = hist[name]
        n = len(values)
        pts = [(int(i * width / max(1, n - 1)), int(height - v * (height - 6) - 3))
               for i, v in enumerate(values)]
        pts += [(width, height), (0, height)]
        draw.polygon(pts, fill=color + (60,), outline=color + (220,))
    return canvas


def exif_summary(img: Image.Image) -> Dict[str, Any]:
    """ملخّص بيانات EXIF بأسماء مفهومة."""
    out: Dict[str, Any] = {}
    try:
        exif = img.getexif()
    except Exception:
        return out
    for tag_id, value in exif.items():
        name = EXIF_TAGS.get(int(tag_id), f"tag_{tag_id}")
        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8", "replace")
            except Exception:
                value = repr(value)
        out[name] = value
    return out


def suggest_edits(img: Image.Image) -> List[Dict[str, Any]]:
    """
    اقتراحات تحرير تلقائية مبنية على المقاييس (نظام توصية بسيط قائم على قواعد).
    """
    s = image_stats(img)
    tips: List[Dict[str, Any]] = []

    if s["is_dark_estimate"]:
        tips.append({"key": "brightness", "label": "الصورة داكنة", "action": "زيادة السطوع",
                     "value": min(40, int((85 - s["mean_brightness"]) * 0.6))})
    if s["is_bright_estimate"]:
        tips.append({"key": "brightness", "label": "الصورة فاتحة جداً", "action": "تقليل السطوع",
                     "value": -min(35, int((s["mean_brightness"] - 190) * 0.5))})
    if s["contrast_std"] < 45:
        tips.append({"key": "contrast", "label": "تباين منخفض", "action": "رفع التباين", "value": 25})
    if s["is_blurry_estimate"]:
        tips.append({"key": "sharpen", "label": "الصورة غير حادة", "action": "تطبيق تحديد", "value": 1.2})
    if s["clipped_highlights_percent"] > 5:
        tips.append({"key": "exposure", "label": "إضاءات محروقة", "action": "تقليل التعرّض", "value": -0.5})
    if s["clipped_shadows_percent"] > 8:
        tips.append({"key": "exposure", "label": "ظلال مسحوقة", "action": "رفع التعرّض", "value": 0.4})
    if s["mean_saturation"] < 45:
        tips.append({"key": "vibrance", "label": "ألوان باهتة", "action": "رفع التشبّع الذكي", "value": 30})
    if not tips:
        tips.append({"key": "none", "label": "الصورة متوازنة", "action": "لا حاجة لتعديلات كبيرة", "value": 0})
    return tips


def full_analysis(img: Image.Image) -> Dict[str, Any]:
    """حزمة التحليل الكاملة (تُستخدم في نقطة /analysis)."""
    stats = image_stats(img)
    stats["dominant_colors"] = dominant_colors(img, 6)
    stats["exif"] = exif_summary(img)
    stats["suggestions"] = suggest_edits(img)
    stats["histogram"] = histogram(img, 48)["channels"]["luminance"]
    return stats


__all__ = [
    "channel_histogram_image", "color_palette_image", "dominant_colors", "exif_summary",
    "full_analysis", "histogram", "image_stats", "suggest_edits",
]

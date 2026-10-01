"""
محرك إزالة الخلفية — خوارزميات كلاسيكية فقط (بلا أي نموذج ذكاء اصطناعي).
========================================================================
الخوارزميات المتاحة:
  1. grabcut   : تقسيم تفاعلي بالرسوم البيانية (Graph-Cut) — الأدق للأجسام العامة.
  2. color_key : عزل لوني (Chroma Key) بمسافة في فضاء LAB/HSV + نموذج K-Means.
  3. flood_fill: تعبئة فيضية من زوايا الصورة — الأنسب لخلفيات الاستوديو الموحّدة.
  4. edge_cut  : كشف حواف (Canny) + تجاويف + قناع محدّب — للأجسام الحادة الحواف.
  5. kmeans    : تجميع لوني K-Means وإبقاء العنقود الأكثر مركزية.
  6. auto      : تشغّل المرشّحات المناسبة وتختار الأفضل آلياً بدالة تقييم.

معالجة لاحقة للقناع: تنعيم (Feathering)، تقليص (Shrink)، إزالة البقع (Despeckle)،
ملء الثقوب، وإزالة تلوّث لون الخلفية عن الحواف (Color Decontamination).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import time

import cv2
import numpy as np
from PIL import Image, ImageFilter

from ..core.exceptions import InvalidParameterError
from ..core.helpers import bgr, clamp_size, from_rgba_array, rgb, to_rgb_array, to_rgba_array

METHODS: Tuple[str, ...] = (
    "grabcut", "color_key", "flood_fill", "edge_cut", "kmeans", "wand", "smart", "auto",
)


# ==============================================================================
#  هياكل البيانات
# ==============================================================================
@dataclass
class MaskOptions:
    """خيارات معالجة القناع النهائية."""

    feather: float = 1.5          # نصف قطر تنعيم الحافة (بكسل)
    shrink: float = 0.0           # تقليص القناع (بكسل) — لإزالة الهالة
    despeckle: int = 120          # حذف المكوّنات الأصغر من هذه المساحة (بكسل)
    fill_holes: bool = True       # ملء الثقوب الداخلية
    decontaminate: float = 0.6    # قوة إزالة تلوّث لون الخلفية [0..1]
    matte: bool = True            # تحسين الحواف بمرشّح موجّه (Guided-Filter Matting)


@dataclass
class SegmentationResult:
    image: Image.Image            # RGBA
    mask: Image.Image             # L (القناع الناعم)
    method: str
    foreground_ratio: float
    scores: Dict[str, float]


# ==============================================================================
#  أدوات القناع
# ==============================================================================
def _normalize_mask(mask: np.ndarray) -> np.ndarray:
    """توحيد القناع إلى uint8 بمجال [0,255]."""
    m = np.asarray(mask)
    if m.dtype != np.uint8:
        m = np.clip(m, 0, 255).astype(np.uint8)
    if m.ndim == 3:
        m = m[..., 0]
    return m


def guided_filter(guide: np.ndarray, src: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """
    المرشّح الموجّه (He et al.) بدليل ملوّن — يُستخدم هنا لصقل ألفا القناع:
    يُنتج حوافاً ناعمة **مطابقة لحواف الصورة الحقيقية** (شعر/وبر/حواف دقيقة)
    بدل الحواف المسنّنة للقناع الثنائي. كل الحسابات بصناديق متوسط (Box Filter)
    ⇒ تعقيد خطي O(N) وسريع جداً (بلا أي نموذج ذكاء اصطناعي).
    guide: صورة RGB بمجال [0,255]، src: قناع بمجال [0,255] ⇒ النتيجة [0,1].
    """
    g = np.asarray(guide, dtype=np.float32) / 255.0
    p = np.asarray(src, dtype=np.float32) / 255.0
    k = 2 * int(max(1, radius)) + 1
    ks = (k, k)

    mean_p = cv2.boxFilter(p, -1, ks)
    means = [cv2.boxFilter(g[..., c], -1, ks) for c in range(3)]
    corr_p = [cv2.boxFilter(g[..., c] * p, -1, ks) for c in range(3)]
    corr_i = [cv2.boxFilter(g[..., c] * g[..., c], -1, ks) for c in range(3)]

    denom = sum(corr_i[c] - means[c] * means[c] for c in range(3)) + float(eps)
    a = [(corr_p[c] - means[c] * mean_p) / denom for c in range(3)]
    b = mean_p - sum(a[c] * means[c] for c in range(3))

    mean_a = [cv2.boxFilter(a[c], -1, ks) for c in range(3)]
    mean_b = cv2.boxFilter(b, -1, ks)
    q = sum(mean_a[c] * g[..., c] for c in range(3)) + mean_b
    return np.clip(q, 0.0, 1.0)


def refine_mask(
    mask: np.ndarray,
    shape: Tuple[int, int],
    opts: MaskOptions,
    guide: Optional[np.ndarray] = None,
) -> np.ndarray:
    """تطبيق المعالجات اللاحقة على القناع الثنائي/الرمادي."""
    mask = _normalize_mask(mask)
    if mask.shape[:2] != (shape[0], shape[1]):
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)

    # 1) تحويل إلى ثنائي للعمليات المورفولوجية ثم العودة إلى رمادي
    binary = (mask > 127).astype(np.uint8) * 255

    # 2) ملء الثقوب الداخلية:
    #    نغمر «الخلفية» ابتداءً من حدّ الصورة؛ ما لم يصله الغمر من بكسلات الخلفية
    #    فهو ثقب محاط بالجسم ⇒ نضمّه إلى القناع.
    if opts.fill_holes:
        h, w = binary.shape
        flood = np.zeros((h + 2, w + 2), np.uint8)
        inverse = cv2.bitwise_not(binary)
        cv2.floodFill(inverse, flood, (0, 0), 255)
        holes = cv2.bitwise_and(cv2.bitwise_not(inverse), cv2.bitwise_not(binary))
        binary = cv2.bitwise_or(binary, holes)

    # 3) إزالة البقع الصغيرة (المكوّنات المتصلة)
    if opts.despeckle and opts.despeckle > 0:
        num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        keep = np.zeros_like(binary)
        for i in range(1, num):
            if stats[i, cv2.CC_STAT_AREA] >= opts.despeckle:
                keep[labels == i] = 255
        # إن حُذف كل شيء (قناع صغير جداً) نتجاهل هذه الخطوة
        if keep.any():
            binary = keep

    # 4) تقليص القناع (مفيد للتخلّص من هالة الخلفية)
    if opts.shrink and opts.shrink > 0:
        k = max(1, int(round(opts.shrink)) * 2 + 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        binary = cv2.erode(binary, kernel, iterations=1)

    # 5) صقل الحواف بالمرشّح الموجّه (Matting): يُلصق حافة القناع على حافة
    #    الصورة الحقيقية فتبدو الحواف (الشعر/الوبر/الانحناءات) طبيعية ودقيقة.
    mask_out = binary.astype(np.float32)
    if opts.matte and guide is not None and min(shape) >= 48 and binary.any():
        radius = int(np.clip(round(min(shape) * 0.012), 2, 24))
        alpha = guided_filter(guide, binary, radius=radius, eps=1e-3)
        # نُثبّت المناطق البعيدة عن الحافة (داخل/خارج) ونترك الصقل عند المحيط فقط
        far_in = cv2.erode(binary, np.ones((5, 5), np.uint8)) > 0
        far_out = cv2.erode(cv2.bitwise_not(binary), np.ones((5, 5), np.uint8)) > 0
        alpha = np.where(far_in, 1.0, np.where(far_out, 0.0, alpha))
        mask_out = alpha * 255.0

    # 6) تنعيم الحافة
    if opts.feather and opts.feather > 0:
        k = max(1, int(round(opts.feather)) * 2 + 1)
        mask_out = cv2.GaussianBlur(mask_out, (k, k), 0)

    return np.clip(mask_out, 0, 255).astype(np.uint8)


def decontaminate(
    img_rgb: np.ndarray,
    mask: np.ndarray,
    bg_color: Tuple[float, float, float],
    strength: float,
) -> np.ndarray:
    """
    إزالة تلوّث لون الخلفية عن البكسلات شبه الشفافة.
    الفكرة: البكسل الملحوظ  C = α·F + (1-α)·B  ⇒  F = (C - (1-α)·B) / α
    نطبّق ذلك على الحواف فقط (حيث 0 < α < 1) ونمزج بالنتيجة حسب `strength`.
    """
    if strength <= 0:
        return img_rgb
    alpha = np.asarray(mask, dtype=np.float32)[..., None] / 255.0
    img = np.asarray(img_rgb, dtype=np.float32)
    bg = np.array(bg_color, dtype=np.float32).reshape(1, 1, 3)

    a_safe = np.clip(alpha, 0.05, 1.0)
    est_f = (img - (1.0 - alpha) * bg) / a_safe
    est_f = np.clip(est_f, 0, 255)

    # وزن المزج: أقصى تأثير عند الحواف (α≈0.5)، صفر داخل الجسم وخارجه
    edge_w = np.clip(1.0 - np.abs(alpha - 0.5) * 2.0, 0, 1) * float(strength)
    return img * (1 - edge_w) + est_f * edge_w


def estimate_bg_color(img_rgb: np.ndarray) -> Tuple[float, float, float]:
    """
    تقدير لون الخلفية من حدود الصورة.
    نأخذ وسيط كل جهة على حدة ثم وسيط الوسائط، حتى لا تطغى جهة واحدة على التقدير.
    """
    h, w = img_rgb.shape[:2]
    band = max(2, int(min(h, w) * 0.04))
    per_side = [
        np.median(img_rgb[:band, :].reshape(-1, 3), axis=0),
        np.median(img_rgb[-band:, :].reshape(-1, 3), axis=0),
        np.median(img_rgb[:, :band].reshape(-1, 3), axis=0),
        np.median(img_rgb[:, -band:].reshape(-1, 3), axis=0),
    ]
    med = np.median(np.stack(per_side, axis=0), axis=0)
    return float(med[0]), float(med[1]), float(med[2])


# ==============================================================================
#  1) GrabCut
# ==============================================================================
def mask_grabcut(
    img: Image.Image,
    rect: Optional[Sequence[float]] = None,
    iterations: int = 8,
) -> np.ndarray:
    """
    خوارزمية GrabCut: نموذج لوني (GMM) + تحسين بالطاقة على رسم بياني.
    `rect` = (x, y, w, h) بنسب مئوية [0..1] تحيط بالجسم. إن لم تُعطَ تُحسب تلقائياً.
    """
    w, h = img.size
    img_bgr = bgr(to_rgb_array(img).astype(np.uint8))

    if rect is None:
        margin_x = int(w * 0.05)
        margin_y = int(h * 0.05)
        rectangle = (margin_x, margin_y, max(1, w - 2 * margin_x), max(1, h - 2 * margin_y))
    else:
        rx, ry, rw, rh = rect
        rectangle = (
            max(0, int(rx * w)),
            max(0, int(ry * h)),
            max(1, int(rw * w)),
            max(1, int(rh * h)),
        )
    # ضمان بقاء 1 بكسل خلفية على الأقل (شرط GrabCut)
    rectangle = (
        min(rectangle[0], w - 2),
        min(rectangle[1], h - 2),
        min(rectangle[2], w - rectangle[0] - 1),
        min(rectangle[3], h - rectangle[1] - 1),
    )
    if rectangle[2] < 2 or rectangle[3] < 2:
        raise InvalidParameterError("مستطيل الجسم صغير جداً بحيث لا يمكن تشغيل GrabCut.")

    mask = np.zeros((h, w), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(img_bgr, mask, rectangle, bgd_model, fgd_model, max(1, int(iterations)), cv2.GC_INIT_WITH_RECT)

    out = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    return out


def mask_grabcut_with_hints(
    img: Image.Image,
    hint_mask: np.ndarray,
    rect: Optional[Sequence[float]] = None,
    iterations: int = 8,
) -> np.ndarray:
    """
    GrabCut مع تلميحات يدوية من المستخدم (مسار رسم على الواجهة).
    قيم hint_mask: 0=مجهول، 128=خلفية مؤكدة، 255=جسم مؤكد.

    تحسينات الدقة:
      • توسيع بذور التلميح قليلاً (Dilate) كي يبني نموذج GMM تقديراً لونياً ثابتاً.
      • بعد التقطيع لا يُبقى إلا المكوّنات المتصلة التي تلمس تلميحات «الجسم»،
        فلا تتسرّب بقع خلفية متشابهة اللون إلى النتيجة.
    """
    w, h = img.size
    if hint_mask.shape[:2] != (h, w):
        hint_mask = cv2.resize(_normalize_mask(hint_mask), (w, h), interpolation=cv2.INTER_NEAREST)
    hint_mask = _normalize_mask(hint_mask)

    fgd_seed = (hint_mask >= 200).astype(np.uint8)
    bgd_seed = ((hint_mask > 60) & (hint_mask < 200)).astype(np.uint8)

    # توسيع البذور: نقرة واحدة ⇒ بقعة صغيرة ثابتة بدل بكسل واحد
    k = max(3, int(round(min(w, h) / 160)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    fgd_seed = cv2.dilate(fgd_seed, kernel)
    bgd_seed = cv2.dilate(bgd_seed, kernel)

    gc_mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    gc_mask[bgd_seed > 0] = cv2.GC_BGD
    gc_mask[fgd_seed > 0] = cv2.GC_FGD          # تلميح الجسم أولى عند التعارض

    use_rect = cv2.GC_INIT_WITH_MASK
    rectangle: Optional[Tuple[int, int, int, int]] = None
    if rect is not None:
        rx, ry, rw, rh = rect
        rectangle = (
            max(0, int(rx * w)), max(0, int(ry * h)),
            max(1, int(rw * w)), max(1, int(rh * h)),
        )
        use_rect = cv2.GC_INIT_WITH_MASK | cv2.GC_INIT_WITH_RECT

    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    img_bgr = bgr(to_rgb_array(img).astype(np.uint8))
    cv2.grabCut(
        img_bgr, gc_mask, rectangle, bgd_model, fgd_model,
        max(1, int(iterations)), use_rect if rectangle else cv2.GC_INIT_WITH_MASK,
    )
    out = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)

    # إبقاء المكوّنات التي تلمس تلميحات الجسم فقط (إن وُجدت تلميحات جسم)
    if fgd_seed.any() and out.any():
        num, labels = cv2.connectedComponents(out, connectivity=8)
        if num > 1:
            keep_ids = np.unique(labels[fgd_seed > 0])
            keep_ids = keep_ids[keep_ids > 0]
            if len(keep_ids):
                out = np.isin(labels, keep_ids).astype(np.uint8) * 255

    # تمرير صقل نهائي: GrabCut ثانٍ على شريط حدودي حول القناع يُلصق الحافة
    # على الحافة الحقيقية للكائن (نفس أسلوب «تحسين الحافة» في المحررات الكبرى)
    out = grabcut_refine(img_bgr, out, iterations=max(4, int(iterations) // 2))
    return out


# ==============================================================================
#  1ب) صقل حدود قناع بتمرير GrabCut شريطي (Boundary Refinement)
# ==============================================================================
def grabcut_refine(img_bgr: np.ndarray, binary: np.ndarray, iterations: int = 6) -> np.ndarray:
    """
    صقل قناع ثنائي: يُبنى قناع GrabCut من ثلاث مناطق —
      • داخل مؤكد (تآكل القناع)  = GC_FGD
      • خارج مؤكد (تآكل المكمّل) = GC_BGD
      • شريط حدودي مجهول بينهما  = GC_PR_*
    ثم تمريرات GrabCut قصيرة تُ snapping الحافة على حدود الألوان الحقيقية.
    أي فشل (قناع فارغ/كامل/خطأ) يُعيد القناع الأصلي كما هو (سلوك آمن).
    """
    binary = _normalize_mask(binary)
    binary = ((binary > 127).astype(np.uint8)) * 255
    if not binary.any() or binary.all():
        return binary
    h, w = binary.shape

    band = max(2, int(round(min(h, w) * 0.02)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * band + 1, 2 * band + 1))
    sure_fg = cv2.erode(binary, kernel)
    sure_bg = cv2.erode(cv2.bitwise_not(binary), kernel)
    if not sure_fg.any() or not sure_bg.any():
        return binary

    gc = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    gc[binary > 0] = cv2.GC_PR_FGD
    gc[sure_fg > 0] = cv2.GC_FGD
    gc[sure_bg > 0] = cv2.GC_BGD

    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img_bgr, gc, None, bgd_model, fgd_model,
                    max(1, int(iterations)), cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return binary
    out = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    if not out.any() or out.all():
        return binary
    return out


# ==============================================================================
#  1ج) العصا السحرية (Magic Wand) — نمو منطقة لوني متعدد البذور
# ==============================================================================
def magic_wand(
    img_rgb: np.ndarray,
    seeds: Sequence[Tuple[int, int, int]],
    tolerance: float = 32.0,
    contiguous: bool = True,
    refine: bool = True,
    iterations: int = 6,
) -> np.ndarray:
    """
    العصا السحرية على نمط المحررات الكلاسيكية (Photoshop/GIMP):
      • كل بذرة = نقرة مستخدم: (x, y, kind) — kind 1 جسم، 0 خلفية.
      • تُحسب مسافة كل بكسل عن لون البذرة في فضاء LAB (الأقرب لإدراك العين)،
        وما دون `tolerance` يُضم للمنطقة.
      • `contiguous`: نمو فيضي من البذرة فقط (المكوّن المتصل الذي يحويها)،
        فلا يقفز التحديد إلى مناطق بعيدة تشبه اللون.
      • بذور الخلفية تُطرح من النتيجة (Shift+نقرة في الواجهة).
      • `refine`: تمرير GrabCut شريطي لصقل الحواف بعد النمو.
    """
    if not seeds:
        raise InvalidParameterError("العصا السحرية تتطلب نقطة نقر واحدة على الأقل.")
    h, w = img_rgb.shape[:2]
    lab = cv2.cvtColor(np.clip(img_rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    # معايرة قناة L (في LAB الخاص بـ OpenCV مضروبة في 255/100)
    lab[..., 0] *= 255.0 / 100.0
    tol = float(max(2.0, tolerance))

    fg = np.zeros((h, w), np.uint8)     # مناطق الجسم
    bg = np.zeros((h, w), np.uint8)     # مناطق الخلفية المستثناة
    for x, y, kind in seeds:
        xi, yi = int(np.clip(round(x), 0, w - 1)), int(np.clip(round(y), 0, h - 1))
        ref = lab[yi, xi]
        dist = np.sqrt(((lab - ref) ** 2).sum(axis=2))
        region = (dist <= tol).astype(np.uint8) * 255
        if contiguous:
            # المكوّن المتصل الذي يحوي البذرة فقط
            num, labels = cv2.connectedComponents((region > 0).astype(np.uint8), connectivity=8)
            if num <= 1:
                continue
            comp_id = labels[yi, xi]
            if comp_id == 0:
                continue
            region = ((labels == comp_id).astype(np.uint8)) * 255
        if int(kind) == 1:
            fg = cv2.bitwise_or(fg, region)
        else:
            bg = cv2.bitwise_or(bg, region)

    out = cv2.bitwise_and(fg, cv2.bitwise_not(bg))

    # تنظيف مورفولوجي خفيف (إغلاق فجوات صغيرة ثم فتح زوائد رقيقة)
    if out.any():
        k = max(3, int(round(min(h, w) / 200)) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, kernel)
        out = cv2.morphologyEx(out, cv2.MORPH_OPEN, kernel)

    if not out.any():
        raise InvalidParameterError(
            "العصا السحرية لم تجد منطقة مطابقة عند هذه النقطة — جرّب رفع التسامح أو نقطة أوضح."
        )

    if refine:
        out = grabcut_refine(bgr(np.clip(img_rgb, 0, 255).astype(np.uint8)), out,
                             iterations=max(2, int(iterations) // 2))
    return out


def _auto_wand_seeds(img_rgb: np.ndarray, n: int = 5) -> List[Tuple[int, int, int]]:
    """
    بذور تلقائية للعصا الذكية: تُنمذج ألوان الحدود (K-Means)، ثم تُختار أبعد
    البكسلات عن نموذج الخلفية داخل منطقة مركزية من الصورة كبذور «جسم».
    """
    h, w = img_rgb.shape[:2]
    rgb_u8 = np.clip(img_rgb, 0, 255).astype(np.uint8)
    norm = _to_space_norm(rgb_u8, "lab")

    centers, stds = _kmeans_bg_clusters(norm, k=3)
    flat = norm.reshape(-1, 3)
    best = np.full((len(flat),), np.inf, np.float32)
    for center, std in zip(centers, stds):
        d = np.sqrt((((flat - center) / std) ** 2).sum(axis=1))
        best = np.minimum(best, d)
    dist = best.reshape(h, w)

    # تقييد الاختيار بالمنطقة المركزية (الكائن عادةً في الوسط وليس على الحواف)
    y0, y1 = int(h * 0.15), int(h * 0.85)
    x0, x1 = int(w * 0.15), int(w * 0.85)
    if y1 - y0 < 4 or x1 - x0 < 4:
        y0, y1, x0, x1 = 0, h, 0, w
    sub = dist[y0:y1, x0:x1]

    # قمم محلية مباعدة: أعلى نقطة ثم أبعدها عنها وهكذا (Non-Maximum بأبعاد مكانية)
    seeds: List[Tuple[int, int, int]] = []
    work = sub.copy()
    min_sep = max(8, int(min(h, w) * 0.08))
    for _ in range(max(1, n)):
        if not np.isfinite(work).any():
            break
        iy, ix = np.unravel_index(int(np.argmax(work)), work.shape)
        seeds.append((int(ix + x0), int(iy + y0), 1))
        yy, xx = np.ogrid[: work.shape[0], : work.shape[1]]
        work[((yy - iy) ** 2 + (xx - ix) ** 2) < min_sep ** 2] = -np.inf
    if not seeds:
        seeds = [(w // 2, h // 2, 1)]
    return seeds


# ==============================================================================
#  2) Color Key (عزل لوني)
# ==============================================================================
def _border_strips(img_rgb: np.ndarray, ratio: float = 0.08) -> np.ndarray:
    """جمع بكسلات شريط حدودي من الجهات الأربع في مصفوفة واحدة (N,3)."""
    h, w = img_rgb.shape[:2]
    band = max(2, int(min(h, w) * ratio))
    parts = [
        img_rgb[:band, :].reshape(-1, 3),
        img_rgb[-band:, :].reshape(-1, 3),
        img_rgb[:, :band].reshape(-1, 3),
        img_rgb[:, -band:].reshape(-1, 3),
    ]
    return np.concatenate(parts, axis=0).astype(np.float32)


def _channel_scale(space: str) -> np.ndarray:
    """
    معاير معايرة القنوات حتى تكون المسافة اللونية عادلة بين القنوات.
    في LAB الخاص بـ OpenCV تكون L مضروبة في 255/100 ⇒ نقسّمها لتعود لمجال [0,255].
    """
    if space == "lab":
        return np.array([255.0 / 100.0, 1.0, 1.0], dtype=np.float32)
    if space == "hsv":
        return np.array([255.0 / 180.0, 1.0, 1.0], dtype=np.float32)
    return np.ones(3, dtype=np.float32)


def _to_space_norm(img_rgb_u8: np.ndarray, space: str) -> np.ndarray:
    """تحويل الصورة إلى الفضاء اللوني المطلوب مع معايرة القنوات."""
    if space == "lab":
        work = cv2.cvtColor(img_rgb_u8, cv2.COLOR_RGB2LAB).astype(np.float32)
    elif space == "hsv":
        work = cv2.cvtColor(img_rgb_u8, cv2.COLOR_RGB2HSV).astype(np.float32)
    elif space == "rgb":
        work = img_rgb_u8.astype(np.float32)
    else:
        raise InvalidParameterError(f"الفضاء اللوني «{space}» غير مدعوم.",
                                    detail={"supported": ["lab", "hsv", "rgb"]})
    return work / _channel_scale(space)


def _kmeans_bg_clusters(
    img_space: np.ndarray,
    k: int = 3,
    floor_std: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    تجميع بكسلات حدود الصورة (في الفضاء اللوني المُمرَّر) لاستخلاص مراكز ألوان
    الخلفية وانتشارها. يجب أن يكون الإدخال بنفس فضاء حساب المسافة.
    """
    strips = _border_strips(img_space, 0.08)

    # عيّنة عشوائية لتسريع التجميع على الصور الكبيرة
    if len(strips) > 20000:
        idx = np.random.choice(len(strips), 20000, replace=False)
        strips = strips[idx]

    k = int(max(1, min(k, len(strips))))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(
        strips, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    # الانحراف المعياري لكل عنقود (مع حد أدنى يمنع القسمة على صفر)
    stds = np.zeros((k, 3), np.float32)
    for i in range(k):
        members = strips[labels.flatten() == i]
        stds[i] = members.std(axis=0) if len(members) > 1 else np.full(3, floor_std, np.float32)
    return centers.astype(np.float32), np.maximum(stds, floor_std)


def mask_color_key(
    img: Image.Image,
    color: Optional[Tuple[int, int, int]] = None,
    tolerance: float = 40.0,
    softness: float = 20.0,
    space: str = "lab",
    auto_sample: bool = True,
) -> np.ndarray:
    """
    عزل لوني: تُحسب مسافة كل بكسل عن لون (أو ألوان) الخلفية في فضاء LAB أو HSV،
    ثم تُحوَّل إلى ألفا ناعمة عبر منحنى انحدار (Soft Ramp).
    """
    rgb_u8 = np.clip(to_rgb_array(img), 0, 255).astype(np.uint8)
    work = _to_space_norm(rgb_u8, space)          # الفضاء الذي تُحسب فيه المسافة

    if color is not None and not auto_sample:
        # تحويل اللون المُدخل إلى نفس الفضاء والمعايرة
        patch = np.array(color, dtype=np.uint8).reshape(1, 1, 3)
        patch_norm = _to_space_norm(patch, space).reshape(1, 3)
        centers = patch_norm
        # التسامح يُعطى بوحدات معايرة (0..255)
        stds = np.full((1, 3), max(2.0, float(tolerance) / 3.0), np.float32)
    else:
        centers, stds = _kmeans_bg_clusters(work, k=3)

    # المسافة المعيارية إلى أقرب مركز (Mahalanobis مبسّط)
    flat = work.reshape(-1, 3)
    best = np.full((len(flat),), np.inf, np.float32)
    for center, std in zip(centers, stds):
        d = np.sqrt((((flat - center) / std) ** 2).sum(axis=1))
        best = np.minimum(best, d)
    dist = best.reshape(work.shape[:2])

    # تحويل المسافة إلى ألفا: قريبة من الخلفية ⇒ شفاف
    lo = max(0.2, float(tolerance) / 10.0)
    hi = lo + max(0.2, float(softness) / 10.0)
    alpha = np.clip((dist - lo) / (hi - lo), 0.0, 1.0)
    return (alpha * 255).astype(np.uint8)


# ==============================================================================
#  3) Flood Fill من الزوايا
# ==============================================================================
def mask_flood_fill(
    img: Image.Image,
    tolerance: Optional[float] = None,
    seed_mode: str = "corners",
    adaptive: bool = True,
) -> np.ndarray:
    """
    تعبئة فيضية متعددة البذور من حدود الصورة: كل بكسل متصل لونياً بالحدود
    ضمن التسامح يُعتبر خلفية. ممتاز لصور الاستوديو ذات الخلفية الموحّدة.

    عند `adaptive` يُشتق التسامح من تشتّت ألوان الحدود، وتُنفَّذ عدة تمريرات
    بتسامح متصاعد لابتلاع التدرّجات اللينة في الخلفية دون الوصول إلى الجسم.
    """
    img_rgb = to_rgb_array(img).astype(np.uint8)
    h, w = img_rgb.shape[:2]
    img_bgr = np.ascontiguousarray(bgr(img_rgb))

    if tolerance is None:
        border = _border_strips(img_rgb.astype(np.float32), 0.05)
        base = float(max(12.0, np.median(border.std(axis=0)) * 3.0))
    else:
        base = float(max(1.0, tolerance))

    bg = np.zeros((h, w), np.uint8)          # 1 = خلفية
    flags = 4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY

    if seed_mode == "edges":
        step = max(1, min(h, w) // 60)
        seeds = [(x, 0) for x in range(0, w, step)] + [(x, h - 1) for x in range(0, w, step)]
        seeds += [(0, y) for y in range(0, h, step)] + [(w - 1, y) for y in range(0, h, step)]
    else:  # corners
        inset = max(1, int(min(h, w) * 0.02))
        seeds = [(inset, inset), (w - inset - 1, inset), (inset, h - inset - 1), (w - inset - 1, h - inset - 1)]

    passes = [1.0, 2.0, 3.0] if adaptive else [1.0]
    scratch = np.zeros((h + 2, w + 2), np.uint8)
    for factor in passes:
        tol = int(max(1, min(120, round(base * factor))))
        for x, y in seeds:
            if not (0 <= x < w and 0 <= y < h) or bg[y, x]:
                continue
            scratch[:] = 0
            try:
                cv2.floodFill(img_bgr, scratch, (int(x), int(y)), 0, (tol,) * 3, (tol,) * 3, flags)
            except cv2.error:
                continue
            bg[scratch[1:-1, 1:-1] > 0] = 1

    subject = (1 - bg) * 255
    return subject.astype(np.uint8)


# ==============================================================================
#  4) Edge Cut (حواف + تجاويف + قناع محدّب)
# ==============================================================================
def mask_edge_cut(img: Image.Image, low: int = 40, high: int = 120, convex: bool = True) -> np.ndarray:
    """
    كشف الحواف ثم استخراج أكبر تجويف مغلق. خيار `convex` يغلّف الجسم بغلاف محدّب
    (مفيد للأجسام ذات التفاصيل الدقيقة التي تكسر التجويف).
    """
    img_rgb = to_rgb_array(img).astype(np.uint8)
    gray = cv2.cvtColor(bgr(img_rgb), cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, int(low), int(high))
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return np.full(gray.shape, 255, np.uint8)

    largest = max(contours, key=cv2.contourArea)
    mask = np.zeros(gray.shape, np.uint8)
    hull = cv2.convexHull(largest) if convex else largest
    cv2.drawContours(mask, [hull], -1, 255, thickness=cv2.FILLED)

    # إزالة أي جزء يلامس حدّ الصورة بالكامل (يعني فشل الكشف)
    if mask.sum() == 0:
        return np.full(gray.shape, 255, np.uint8)
    return mask


# ==============================================================================
#  5) K-Means العام
# ==============================================================================
def mask_kmeans(img: Image.Image, k: int = 4, keep: int = 1) -> np.ndarray:
    """
    تجميع كل بكسلات الصورة، ثم إبقاء العناقيد التي **لا تشبه لون الحدود**.
    معيار التشابه: المسافة إلى أقرب مركز من مراكز عناقيد الحدود؛ العناقيد القريبة
    من الخلفية تُستبعد، ولا يُبقي الدالة سوى العناقيد «المختلفة عن الخلفية».
    """
    img_rgb = to_rgb_array(img).astype(np.uint8)
    h, w = img_rgb.shape[:2]

    # كل الحسابات في فضاء LAB مُعاير (أقرب لإدراك العين من RGB)
    norm_full = _to_space_norm(img_rgb, "lab")

    # 1) نموذج ألوان الخلفية من الحدود
    bg_centers, bg_stds = _kmeans_bg_clusters(norm_full, k=3)

    # 2) تجميع بكسلات الصورة على نسخة مصغّرة (للسرعة)
    small_w = min(w, 320)
    small_h = max(1, int(h * small_w / w))
    pixels = cv2.resize(norm_full, (small_w, small_h), interpolation=cv2.INTER_AREA).reshape(-1, 3)
    pixels = np.ascontiguousarray(pixels, dtype=np.float32)

    k = int(np.clip(k, 2, 8))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 15, 1.0)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)

    # 3) مدى «اختلاف» كل عنقود عن الخلفية (مسافة Mahalanobis مبسّطة)
    diff = np.zeros(k, np.float32)
    for i in range(k):
        d = np.linalg.norm((centers[i] - bg_centers) / bg_stds, axis=1)
        diff[i] = float(d.min())

    # 4) إبقاء كل العناقيد المختلفة عن الخلفية بما يكفي (وليس عنقوداً واحداً فقط)،
    #    مع إمكانية تحديد سقف بعددها عبر `keep` (0 = بلا سقف).
    threshold = 1.5
    order = np.argsort(-diff)
    selected = [int(i) for i in order if diff[i] >= threshold]
    if not selected:
        selected = [int(order[0])]
    if keep and int(keep) > 0:
        selected = selected[: int(keep)]

    sel = np.isin(labels.flatten(), selected).reshape(small_h, small_w)
    mask_small = sel.astype(np.uint8) * 255
    return cv2.resize(mask_small, (w, h), interpolation=cv2.INTER_NEAREST)


# ==============================================================================
#  تقييم الأقنعة (للاختيار التلقائي)
# ==============================================================================
def score_mask(mask: np.ndarray, img_rgb: np.ndarray) -> Dict[str, float]:
    """
    دالة تقييم قناع بلا مرجع (No-Reference):
      • fg_ratio_plausibility : الجسم عادةً 8%–85% من المساحة.
      • border_clean          : نسبة الشفافية عند حدود الصورة (يفترض أن تكون عالية).
      • edge_smoothness       : نعومة محيط القناع (عكس طول المحيط/المساحة).
      • border_contrast       : تباين لون الجسم عن لون الحدود (دليل عزل حقيقي).
    """
    m = np.asarray(mask, dtype=np.float32) / 255.0
    h, w = m.shape
    fg = float(m.mean())

    plaus = 1.0 - min(1.0, abs(fg - 0.42) / 0.42)

    band = max(2, int(min(h, w) * 0.03))
    border_vals = np.concatenate(
        [m[:band, :].ravel(), m[-band:, :].ravel(), m[:, :band].ravel(), m[:, -band:].ravel()]
    )
    border_clean = 1.0 - float(border_vals.mean())

    binary = (m > 0.5).astype(np.uint8)
    area = max(1.0, float(binary.sum()))
    perimeter = float(cv2.arcLength(cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0][0], True)) \
        if binary.any() else 1.0
    compactness = (4 * np.pi * area) / max(1.0, perimeter ** 2)
    edge_smoothness = float(np.clip(compactness, 0, 1))

    bg = np.array(estimate_bg_color(img_rgb), dtype=np.float32)
    inside = binary > 0
    if inside.any():
        fg_mean = img_rgb[inside].mean(axis=0)
        contrast = float(np.clip(np.linalg.norm(fg_mean - bg) / 90.0, 0, 1))
    else:
        contrast = 0.0

    total = (
        0.22 * plaus + 0.34 * border_clean + 0.18 * edge_smoothness + 0.26 * contrast
    )
    return {
        "fg_ratio": round(fg, 4),
        "plausibility": round(plaus, 4),
        "border_clean": round(border_clean, 4),
        "edge_smoothness": round(edge_smoothness, 4),
        "border_contrast": round(contrast, 4),
        "total": round(total, 4),
    }


# ==============================================================================
#  الواجهة الموحّدة
# ==============================================================================
def remove_background(
    img: Image.Image,
    *,
    method: str = "auto",
    rect: Optional[Sequence[float]] = None,
    hint_mask: Optional[np.ndarray] = None,
    seeds: Optional[Sequence[Sequence[float]]] = None,
    iterations: int = 8,
    wand_tolerance: float = 32.0,
    wand_contiguous: bool = True,
    color: Optional[Tuple[int, int, int]] = None,
    tolerance: float = 40.0,
    softness: float = 20.0,
    space: str = "lab",
    auto_sample: bool = True,
    low: int = 40,
    high: int = 120,
    convex: bool = True,
    k: int = 4,
    keep_clusters: int = 0,
    flood_tolerance: Optional[float] = None,
    mask_options: Optional[MaskOptions] = None,
    return_mask: bool = True,
) -> SegmentationResult:
    """
    النقطة الموحّدة لإزالة الخلفية. تُرجع صورة RGBA + القناع + طريقة التنفيذ + درجات التقييم.
    """
    method = (method or "auto").lower()
    if method not in METHODS:
        raise InvalidParameterError(
            f"طريقة إزالة الخلفية «{method}» غير مدعومة.", detail={"supported": list(METHODS)}
        )

    img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
    base_rgb = img.convert("RGB")
    img_rgb = to_rgb_array(base_rgb).astype(np.float32)
    w, h = base_rgb.size
    opts = mask_options or MaskOptions()
    scores: Dict[str, float] = {}

    def run(name: str) -> np.ndarray:
        if name == "grabcut":
            if hint_mask is not None:
                return mask_grabcut_with_hints(base_rgb, hint_mask, rect=rect, iterations=iterations)
            return mask_grabcut(base_rgb, rect=rect, iterations=iterations)
        if name == "wand":
            if not seeds:
                raise InvalidParameterError("طريقة العصا السحرية تتطلب نقاط نقر (seeds).")
            rgb_u8 = to_rgb_array(base_rgb).astype(np.uint8)
            return magic_wand(
                rgb_u8,
                [(int(round(s[0])), int(round(s[1])), int(round(s[2])) if len(s) > 2 else 1) for s in seeds],
                tolerance=wand_tolerance,
                contiguous=wand_contiguous,
                refine=True,
                iterations=iterations,
            )
        if name == "smart":
            # عصا سحرية تلقائية: بذرة الجسم من مركز الكتلة الأكثر اختلافًا عن الحدود
            rgb_u8 = to_rgb_array(base_rgb).astype(np.uint8)
            auto_seeds = _auto_wand_seeds(rgb_u8)
            return magic_wand(rgb_u8, auto_seeds, tolerance=max(24.0, wand_tolerance),
                              contiguous=True, refine=True, iterations=iterations)
        if name == "color_key":
            return mask_color_key(base_rgb, color=color, tolerance=tolerance, softness=softness,
                                  space=space, auto_sample=auto_sample)
        if name == "flood_fill":
            # flood_tolerance=None ⇒ تسامح تكيّفی مشتق من تشتت ألوان الحدود
            return mask_flood_fill(base_rgb, tolerance=flood_tolerance)
        if name == "edge_cut":
            return mask_edge_cut(base_rgb, low=low, high=high, convex=convex)
        if name == "kmeans":
            return mask_kmeans(base_rgb, k=k, keep=keep_clusters)
        raise InvalidParameterError(f"طريقة غير معروفة: {name}")

    if method == "auto":
        # 1) تجربة الطرق السريعة أولاً (كلها أقل من 100 ملّي ثانية عادةً)
        fast_candidates: List[str] = ["flood_fill", "color_key", "kmeans", "edge_cut"]
        trials: List[Tuple[str, np.ndarray, float, float]] = []

        def trial(name: str) -> None:
            started = time.perf_counter()
            try:
                m = run(name)
                elapsed = time.perf_counter() - started
                sc = score_mask(m, img_rgb)
                scores[name] = sc["total"]
                trials.append((name, m, sc["total"], elapsed))
            except Exception:
                return

        for name in fast_candidates:
            trial(name)

        # 2) GrabCut والعصا الذكية دائماً: الأدق للأجسام العامة، وإشراكهما في
        #    المفاضلة يضمن ألا تفوز طريقة سريعة رديئة الحواف بمجرد أن درجتها مقبولة.
        trial("grabcut")
        trial("smart")

        if not trials:
            raise InvalidParameterError("فشلت كل طرق إزالة الخلفية التلقائية على هذه الصورة.")

        # 3) الاختيار: الجودة أولاً؛ لا يُفضَّل الأسرع إلا عند تكافؤ شبه تام (≤ 0.005)
        best_quality = max(t[2] for t in trials)
        near_best = [t for t in trials if t[2] >= best_quality - 0.005]
        chosen = min(near_best, key=lambda t: t[3])   # الأسرع بين المتكافئين تماماً
        raw_mask, used = chosen[1], f"auto:{chosen[0]}"
    else:
        raw_mask, used = run(method), method

    # إزالة تلوّث لون الخلفية عن الحواف
    rgb_arr = to_rgb_array(base_rgb)                       # مجال [0,255]

    # صقل القناع (ثقوب/بقع/تقليص/Matting موجّه/تنعيم) — الصورة دليلٌ للحواف
    refined = refine_mask(raw_mask, (h, w), opts, guide=rgb_arr)
    if opts.decontaminate > 0:
        rgb_arr = decontaminate(rgb_arr, refined, estimate_bg_color(rgb_arr), opts.decontaminate)

    # الدمج النهائي: RGB بمجال [0,255] مع القناع بمجال [0,255] (وليس النسخة المُعايرة)
    rgba = np.dstack([rgb_arr, refined.astype(np.float32)]).astype(np.uint8)
    out_img = from_rgba_array(rgba)
    out_mask = Image.fromarray(refined, "L")

    fg_ratio = float((refined > 127).mean())
    return SegmentationResult(
        image=out_img,
        mask=out_mask if return_mask else None,  # type: ignore[arg-type]
        method=used,
        foreground_ratio=round(fg_ratio, 4),
        scores=scores,
    )


def crop_to_alpha(img: Image.Image, padding: int = 8) -> Image.Image:
    """قصّ الصورة إلى حدود المحتوى غير الشفاف (مفيد بعد إزالة الخلفية)."""
    arr = to_rgba_array(img)
    alpha = arr[..., 3]
    ys, xs = np.where(alpha > 8)
    if len(xs) == 0:
        return img
    x0, x1 = max(0, int(xs.min()) - padding), min(img.width, int(xs.max()) + padding + 1)
    y0, y1 = max(0, int(ys.min()) - padding), min(img.height, int(ys.max()) + padding + 1)
    return img.crop((x0, y0, x1, y1))


def apply_mask(img: Image.Image, mask: Image.Image, invert: bool = False) -> Image.Image:
    """تطبيق قناع خارجي على صورة وإرجاع RGBA."""
    rgba = img.convert("RGBA")
    m = mask.convert("L")
    if m.size != rgba.size:
        m = m.resize(rgba.size, Image.BILINEAR)
    if invert:
        from PIL import ImageChops

        m = ImageChops.invert(m)
    alpha = m.filter(ImageFilter.GaussianBlur(0.5))
    rgba.putalpha(alpha)
    return rgba


__all__ = [
    "METHODS", "MaskOptions", "SegmentationResult", "_channel_scale", "_to_space_norm",
    "apply_mask", "crop_to_alpha",
    "decontaminate", "estimate_bg_color", "grabcut_refine", "guided_filter", "magic_wand",
    "mask_color_key", "mask_edge_cut", "mask_flood_fill", "mask_grabcut",
    "mask_grabcut_with_hints", "mask_kmeans",
    "refine_mask", "remove_background", "score_mask",
]

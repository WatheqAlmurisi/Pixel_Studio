"""
خدمات المعالجة المتخصصة — ترميم الصور القديمة · تنقيح الوجوه · وضع المستندات
===========================================================================
كل الخوارزميات كلاسيكية (OpenCV) بلا أي نموذج ذكاء اصطناعي:
  1. restore_old_photo : كشف الخدوش والغبار (Top-Hat مورفولوجي) + ترميم بالفيضان
                         (Inpainting) + موازنة لونية + CLAHE + تقليل ضوضاء + تحديد.
  2. retouch_faces     : كشف الوجوه (Haar Cascade) + تنعيم البشرة (Bilateral)
                         + إزالة العيوب (Inpainting) + إزالة العين الحمراء.
  3. document_scan     : كشف محيط المستند (أكبر رباعي) + تصحيح منظوري
                         + أعتاب تكيفي (أبيض/أسود) أو تحسين (خلفية بيضاء).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from ..core.exceptions import InvalidParameterError
from ..core.helpers import bgr, from_rgb_array, to_rgb_array


# ==============================================================================
#  1) ترميم الصور القديمة
# ==============================================================================
@dataclass
class RestoreOptions:
    scratches: bool = True        # إزالة الخدوش الرفيعة
    dust: bool = True             # إزالة الغبار والبقع الصغيرة
    recolor: bool = True          # موازنة لونية + CLAHE للبهتان والاصفرار
    denoise: float = 0.5          # قوة تقليل الضوضاء [0..1]
    sharpen: float = 0.4          # قوة التحديد النهائي [0..1]


def _scratch_dust_mask(gray: np.ndarray, scratches: bool, dust: bool) -> np.ndarray:
    """
    كشف عيوب الصور القديمة مورفولوجياً:
      • الخدوش: خطوط رفيعة أكثر سطوعاً/عتمةً من محيطها ⇒ Top-Hat / Black-Hat
        بنوى خطية في اتجاهين + نواة رفيعة عامة.
      • الغبار: بقع نقطية صغيرة ⇒ Top-Hat/Black-Hat بنواة مربعة صغيرة.
    تُجمع الأقنعة وتُعتَّب بمقدار مشتق من تشتّت الصورة (تكيفي).
    """
    h, w = gray.shape
    mask = np.zeros((h, w), np.uint8)
    base = cv2.medianBlur(gray, 3)

    if scratches:
        klen = max(9, int(round(min(h, w) / 24)) | 1)
        for angle in (0, 45, 90, 135):
            k = np.zeros((klen, klen), np.uint8)
            if angle == 0:
                k[klen // 2, :] = 1
            elif angle == 90:
                k[:, klen // 2] = 1
            elif angle == 45:
                np.fill_diagonal(k, 1)
            else:
                np.fill_diagonal(np.fliplr(k), 1)
            th = cv2.morphologyEx(base, cv2.MORPH_TOPHAT, k)
            bh = cv2.morphologyEx(base, cv2.MORPH_BLACKHAT, k)
            mask = cv2.bitwise_or(mask, cv2.add(th, bh))

    if dust:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        th = cv2.morphologyEx(base, cv2.MORPH_TOPHAT, k)
        bh = cv2.morphologyEx(base, cv2.MORPH_BLACKHAT, k)
        mask = cv2.bitwise_or(mask, cv2.add(th, bh))

    if not mask.any():
        return mask

    # عتبة تكيفية: ما فوق وسيط + 3×MAD يُعد عيباً
    med = float(np.median(mask))
    mad = float(np.median(np.abs(mask.astype(np.float32) - med)))
    thr = max(18.0, med + 5.0 * mad)
    mask = (mask > thr).astype(np.uint8) * 255

    # توسيع طفيف ليشمل الترميم حواف العيب كاملة
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    return mask


def _white_balance(img: np.ndarray) -> np.ndarray:
    """موازنة رمادية-العالم (Gray-World) لإزالة الاصفرار/البهتان اللوني."""
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)
    for ch in (1, 2):
        lab[..., ch] -= lab[..., ch].mean()
        lab[..., ch] += 128.0
    lab[..., 0] = np.clip(lab[..., 0], 0, 255)
    out = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    # مزج محافظ: نصف التصحيح حتى لا تتحول الصور أحادية اللون
    return cv2.addWeighted(img, 0.5, out, 0.5, 0)


def restore_old_photo(img: Image.Image, opts: RestoreOptions) -> Tuple[Image.Image, Dict[str, float]]:
    """المرمم الكامل: عيوب ⇒ ترميم ⇒ ألوان ⇒ ضوضاء ⇒ تحديد."""
    rgb_arr = to_rgb_array(img.convert("RGB")).astype(np.uint8)
    h, w = rgb_arr.shape[:2]
    stats: Dict[str, float] = {}

    work = rgb_arr.copy()

    # 1) كشف العيوب وترميمها بالفيضان
    if opts.scratches or opts.dust:
        gray = cv2.cvtColor(bgr(work), cv2.COLOR_BGR2GRAY)
        defect = _scratch_dust_mask(gray, opts.scratches, opts.dust)
        defect_ratio = float((defect > 0).mean())
        stats["defect_pixels"] = int((defect > 0).sum())
        if defect.any() and defect_ratio < 0.25:   # حماية: صورة كلها «عيوب» ⇒ لا ترمم
            work = cv2.inpaint(work, defect, 3, cv2.INPAINT_TELEA)
            stats["inpaint_applied"] = 1.0
        else:
            stats["inpaint_applied"] = 0.0

    # 2) استعادة الألوان والتباين
    if opts.recolor:
        work = _white_balance(work)
        lab = cv2.cvtColor(bgr(work), cv2.COLOR_BGR2LAB)
        clip = max(1.0, 4.0 * (1.0 - 0.0))
        clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
        lab[..., 0] = clahe.apply(lab[..., 0])
        work = cv2.cvtColor(lab, cv2.COLOR_BGR2RGB)

    # 3) تقليل الضوضاء (يحافظ على الحواف)
    if opts.denoise > 0:
        strength = float(np.clip(opts.denoise, 0, 1))
        work = cv2.fastNlMeansDenoisingColored(
            work, None, 3 + 7 * strength, 3 + 7 * strength, 7, 21)

    # 4) تحديد خفيف (Unsharp) لاستعادة الحدة المفقودة
    if opts.sharpen > 0:
        strength = float(np.clip(opts.sharpen, 0, 1))
        blur = cv2.GaussianBlur(work, (0, 0), 2.0)
        work = cv2.addWeighted(work, 1 + 0.8 * strength, blur, -0.8 * strength, 0)

    stats["width"], stats["height"] = w, h
    return from_rgb_array(np.clip(work, 0, 255).astype(np.uint8)), stats


# ==============================================================================
#  2) تنقيح الوجوه
# ==============================================================================
@dataclass
class RetouchOptions:
    smooth: float = 0.6           # قوة تنعيم البشرة [0..1]
    blemish: bool = True          # إزالة العيوب (بقع داكنة) بالترميم
    redeye: bool = True           # إزالة العين الحمراء


def _load_cascade(name: str) -> cv2.CascadeClassifier:
    path = cv2.data.haarcascades + name  # type: ignore[attr-defined]
    cc = cv2.CascadeClassifier(path)
    if cc.empty():
        raise InvalidParameterError(f"تعذّر تحميل كاشف {name}.")
    return cc


def _skin_mask(rgb_face: np.ndarray) -> np.ndarray:
    """قناع البشرة بقاعدة YCbCr الكلاسيكية (تعمل على معظم درجات البشرة)."""
    ycrcb = cv2.cvtColor(bgr(rgb_face), cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    m = ((cr >= 133) & (cr <= 177) & (cb >= 77) & (cb <= 133) & (y > 40)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    return m


def _exclude_features(face_box: Tuple[int, int, int, int], skin: np.ndarray,
                       gray_full: np.ndarray, eyes_cc: cv2.CascadeClassifier) -> np.ndarray:
    """استثناء العينين والفم من قناع البشرة حتى لا تُمسح الملامح."""
    x, y, fw, fh = face_box
    face_gray = gray_full[y:y + fh, x:x + fw]
    ex = skin.copy()
    eyes = eyes_cc.detectMultiScale(face_gray, scaleFactor=1.1, minNeighbors=6,
                                    minSize=(max(8, fw // 12), max(8, fw // 12)))
    for ex_, ey, ew, eh in eyes:
        pad = int(ew * 0.55)
        x0, y0 = max(0, ex_ - pad), max(0, ey - pad)
        x1, y1 = min(skin.shape[1], ex_ + ew + pad), min(skin.shape[0], ey + eh + pad)
        ex[y0:y1, x0:x1] = 0
    # شريط الفم التقريبي (الثلث السفلي الأوسط)
    m_y0 = int(fh * 0.66)
    m_x0, m_x1 = int(fw * 0.28), int(fw * 0.72)
    ex[m_y0:fh, m_x0:m_x1] = 0
    return ex


def _remove_red_eye(rgb_face: np.ndarray, eye_box: Tuple[int, int, int, int]) -> np.ndarray:
    """إزالة العين الحمراء: البكسلات شديدة الحمرة داخل العين تُستبدل برماديها."""
    x, y, ew, eh = eye_box
    h, w = rgb_face.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + ew), min(h, y + eh)
    if x1 <= x0 or y1 <= y0:
        return rgb_face
    roi = rgb_face[y0:y1, x0:x1].astype(np.float32)
    r, g, b = roi[..., 0], roi[..., 1], roi[..., 2]
    red = (r > 90) & (r > g * 1.5) & (r > b * 1.5)
    if not red.any():
        return rgb_face
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    # إطفاء الحمرة: نخفض R إلى مستوى G/B مع تظليل خفيف (حدقة طبيعية أغمق)
    new_r = np.minimum(r, np.maximum(g, b) * 0.9)
    roi[..., 0] = np.where(red, new_r * 0.92, r)
    rgb_face[y0:y1, x0:x1] = np.clip(roi, 0, 255).astype(np.uint8)
    return rgb_face


def retouch_faces(img: Image.Image, opts: RetouchOptions) -> Tuple[Image.Image, Dict[str, int]]:
    """تنقيح كلاسيكي: كشف Haar ⇒ تنعيم بشرة ⇒ عيوب ⇒ عين حمراء."""
    work = to_rgb_array(img.convert("RGB")).astype(np.uint8).copy()
    h, w = work.shape[:2]
    gray = cv2.cvtColor(bgr(work), cv2.COLOR_BGR2GRAY)

    faces_cc = _load_cascade("haarcascade_frontalface_default.xml")
    eyes_cc = _load_cascade("haarcascade_eye.xml")

    min_side = max(48, int(min(h, w) * 0.08))
    faces = faces_cc.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5,
                                      minSize=(min_side, min_side))
    stats = {"faces": int(len(faces)), "eyes_fixed": 0}

    strength = float(np.clip(opts.smooth, 0, 1))
    for (x, y, fw, fh) in faces:
        face = work[y:y + fh, x:x + fw]
        face_gray = gray[y:y + fh, x:x + fw]

        # 1) تنعيم البشرة: Bilateral يحافظ على حواف الملامح
        if strength > 0:
            d = max(5, int(round(min(fw, fh) / 12)) | 1)
            smooth = cv2.bilateralFilter(face, d, 25 + 55 * strength, 25 + 55 * strength)
            skin = _skin_mask(face)
            skin = _exclude_features((x, y, fw, fh), skin, gray, eyes_cc)
            # مزج تدريجي: تنعيم كامل داخل البشرة يتلاشى عند الحواف
            alpha = (cv2.GaussianBlur(skin, (0, 0), max(1.0, min(fw, fh) / 30)) / 255.0)
            alpha = (alpha * strength)[..., None]
            work[y:y + fh, x:x + fw] = np.clip(
                face * (1 - alpha) + smooth * alpha, 0, 255).astype(np.uint8)

        # 2) إزالة العيوب: بقع داكنة صغيرة داخل البشرة ⇒ ترميم
        if opts.blemish:
            skin = _skin_mask(face)
            skin = _exclude_features((x, y, fw, fh), skin, gray, eyes_cc)
            blur = cv2.medianBlur(face_gray, 9)
            dark = cv2.subtract(blur, face_gray)          # ما هو أغمق من محيطه
            spots = cv2.bitwise_and(dark, skin)
            spots = (spots > max(16, 22 - 8 * strength)).astype(np.uint8) * 255
            spots = cv2.morphologyEx(spots, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
            if spots.any() and float((spots > 0).mean()) < 0.12:
                spots = cv2.dilate(spots, np.ones((3, 3), np.uint8))
                work[y:y + fh, x:x + fw] = cv2.inpaint(face, spots, 3, cv2.INPAINT_TELEA)

        # 3) العين الحمراء
        if opts.redeye:
            eyes = eyes_cc.detectMultiScale(face_gray, scaleFactor=1.1, minNeighbors=6,
                                            minSize=(max(8, fw // 12), max(8, fw // 12)))
            for ex, ey, ew, eh in eyes:
                before = work[y:y + fh, x:x + fw].copy()
                fixed = _remove_red_eye(work[y:y + fh, x:x + fw], (ex, ey, ew, eh))
                work[y:y + fh, x:x + fw] = fixed
                if not np.array_equal(before, fixed):
                    stats["eyes_fixed"] += 1

    return from_rgb_array(work), stats


# ==============================================================================
#  3) وضع المستندات
# ==============================================================================
def _order_points(pts: np.ndarray) -> np.ndarray:
    """ترتيب النقاط الأربع: أعلى-يسار، أعلى-يمين، أسفل-يمين، أسفل-يسار."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).flatten()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def _find_paper_quad(gray: np.ndarray) -> Optional[np.ndarray]:
    """أكبر رباعي شبيه بالورقة (حواف قوية + مساحة كبيرة) أو None."""
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 130)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:6]
    img_area = float(h * w)
    for c in contours:
        area = cv2.contourArea(c)
        if area < img_area * 0.12:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return _order_points(approx.reshape(4, 2).astype(np.float32))
    return None


def document_scan(
    img: Image.Image,
    mode: str = "enhance",
    perspective: bool = True,
) -> Tuple[Image.Image, Dict[str, object]]:
    """
    معالجة صورة مستند:
      • perspective: تصحيح منظوري إن وُجد رباعي الورقة.
      • mode:
          - bw      : أبيض/أسود نظيف (أعتاب تكيفي).
          - enhance : خلفية بيضاء مع الحفاظ على لون الحبر (أعتاب قسْمي).
          - color   : تصحيح منظور + توحيد إضاءة فقط.
    """
    if mode not in ("bw", "enhance", "color"):
        raise InvalidParameterError(f"وضع المستند «{mode}» غير مدعوم.",
                                    detail={"supported": ["bw", "enhance", "color"]})
    work = to_rgb_array(img.convert("RGB")).astype(np.uint8)
    gray = cv2.cvtColor(bgr(work), cv2.COLOR_BGR2GRAY)
    warped = False

    if perspective:
        quad = _find_paper_quad(gray)
        if quad is not None:
            (tl, tr, br, bl) = quad
            wa = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
            hb = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
            if wa > 40 and hb > 40:
                dst = np.array([[0, 0], [wa - 1, 0], [wa - 1, hb - 1], [0, hb - 1]], np.float32)
                m = cv2.getPerspectiveTransform(quad, dst)
                work = cv2.warpPerspective(work, m, (wa, hb), flags=cv2.INTER_CUBIC,
                                           borderMode=cv2.BORDER_REPLICATE)
                gray = cv2.cvtColor(bgr(work), cv2.COLOR_BGR2GRAY)
                warped = True

    if mode == "color":
        # توحيد إضاءة: قسمة على نسخة مموّهة بشدة (تزيل الظلال والتدرج)
        bg = cv2.GaussianBlur(gray, (0, 0), max(9, min(gray.shape) // 12))
        norm = cv2.divide(gray.astype(np.float32), bg.astype(np.float32) + 1e-6) * 200.0
        norm = np.clip(norm, 0, 255).astype(np.uint8)
        # إعادة الصبغ: نحتفظ بلون الحبر عبر تطبيق الإضاءة الموحدة على القنوات
        out = work.copy()
        for ch in range(3):
            ratio = norm.astype(np.float32) / (gray.astype(np.float32) + 1e-6)
            out[..., ch] = np.clip(work[..., ch] * ratio, 0, 255).astype(np.uint8)
        work = out
    else:
        # خلفية موحدة أولاً (إزالة الظلال) ثم الأعتاب
        bg = cv2.GaussianBlur(gray, (0, 0), max(9, min(gray.shape) // 12))
        norm = np.clip(cv2.divide(gray.astype(np.float32), bg.astype(np.float32) + 1e-6) * 200.0,
                       0, 255).astype(np.uint8)
        if mode == "bw":
            bw = cv2.adaptiveThreshold(norm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 25, 12)
            work = cv2.cvtColor(bw, cv2.COLOR_GRAY2RGB)
        else:  # enhance — أعتاب قسْمي: خلفية بيضاء والحبر بلونه الأصلي
            paper = np.where(norm > 150, 255, norm).astype(np.float32)
            out = work.copy()
            for ch in range(3):
                div = cv2.divide(work[..., ch].astype(np.float32), paper + 1e-6, scale=255)
                out[..., ch] = np.clip(div, 0, 255).astype(np.uint8)
            # تبييض الخلفية المتبقية
            mask_bg = (norm > 165).astype(np.uint8)[..., None] * 255
            out = np.where(mask_bg > 0, 255, out).astype(np.uint8)
            work = out

    return from_rgb_array(np.clip(work, 0, 255).astype(np.uint8)), {"perspective_applied": warped}


__all__ = [
    "RestoreOptions", "RetouchOptions",
    "restore_old_photo", "retouch_faces", "document_scan",
]

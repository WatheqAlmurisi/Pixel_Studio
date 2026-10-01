"""
مسارات الإصدار الأول من واجهة البرمجة (API v1).
===============================================
كل مجموعة مسارات (Router) مسؤولة عن نطاق وظيفي واحد، وتستدعي طبقة الخدمات فقط.
لا يوجد أي منطق معالجة داخل المسارات.
"""
from __future__ import annotations

import time
import base64
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Query, Response
from PIL import Image

from ...core.exceptions import InvalidParameterError
from ...core.helpers import parse_color
from ...core.image_io import encode_image, load_image
from ...services import (
    analysis,
    backgrounds,
    batch as batch_service,
    composite,
    creative,
    filters,
    geometric,
    pixel_ops,
    restore,
    segmentation,
)
from ...schemas.operations import (
    AdjustRequest, AnalysisRequest, ApplyMaskRequest,
    BackgroundOnlyRequest, BackgroundRequest, BatchItemOut,
    BatchRequest, BlendRequest, BlurRequest,
    BorderRequest, CanvasRequest, ConvertRequest,
    CreativeRequest, CropAspectRequest, CropAutoRequest,
    CropContentRequest, CropRequest, CurvesRequest,
    DenoiseRequest, DoubleExposureRequest, DownloadRequest,
    EdgesRequest, FlipRequest, GenericFilterRequest,
    GlowRequest, GrainRequest, HalftoneRequest,
    ImageRequest, LevelsRequest, MergeRequest,
    OilPaintRequest, PadRequest, PencilRequest,
    PerspectiveRequest, PipRequest, PipelineRequest,
    PixelateRequest, RemoveBgRequest, ResizeRequest,
    RestoreRequest, RetouchRequest, DocumentRequest,
    Rotate90Request, RotateRequest, SeamlessRequest,
    ShadowRequest, SharpenRequest, SketchRequest,
    SurfaceSmoothRequest, ThresholdRequest, TransposeRequest,
    VignetteRequest, WatermarkImageRequest, WatermarkTextRequest,
)
from ...schemas.operations import ImageRequest as ImageRequestOnly
from ._common import prepare, respond, respond_dict

# ==============================================================================
#  1) تحويل الصيغ
# ==============================================================================
convert_router = APIRouter(prefix="/convert", tags=["تحويل الصيغ"])


@convert_router.post("", summary="تحويل الصورة إلى صيغة أخرى")
def convert(req: ConvertRequest) -> Dict[str, Any]:
    """
    يدعم: PNG, JPEG, WEBP, BMP, TIFF, GIF, ICO, AVIF, PPM.
    الصيغ غير الداعمة للشفافية تُدمج على لون `background`.
    """
    started = time.perf_counter()
    img = prepare(req.image, keep_exif=req.keep_exif)
    enc = encode_image(
        img, req.format,
        quality=req.quality,
        optimize=req.optimize,
        background=parse_color(req.background),
        keep_alpha=req.keep_alpha,
        keep_exif=req.keep_exif,
        png_compression=req.png_compression,
    )
    return {
        "image": enc.data,
        "meta": {
            "format": enc.format, "mime": enc.mime, "width": enc.width,
            "height": enc.height, "size_bytes": enc.size_bytes,
            "size_kb": round(enc.size_bytes / 1024, 2),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "operations": [f"convert:{enc.format}"],
        },
    }


@convert_router.get("/formats", summary="الصيغ المدعومة")
def formats() -> Dict[str, Any]:
    from ...core.image_io import FORMATS
    from ...core.settings import settings

    return {
        "input": settings.SUPPORTED_INPUT,
        "output": settings.SUPPORTED_OUTPUT,
        "details": [
            {"key": k, "extension": v["ext"], "mime": v["mime"], "supports_alpha": v["alpha"]}
            for k, v in FORMATS.items()
        ],
    }


# ==============================================================================
#  2) العمليات الهندسية
# ==============================================================================
geometry_router = APIRouter(prefix="/geometry", tags=["العمليات الهندسية"])


@geometry_router.post("/crop", summary="قصّ منطقة محددة")
def crop(req: CropRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(geometric.crop(img, req.box, unit=req.unit), started, operations=["crop"])


@geometry_router.post("/crop-aspect", summary="قصّ إلى نسبة أبعاد")
def crop_aspect(req: CropAspectRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(geometric.crop_aspect(img, req.aspect, req.anchor), started,
                   operations=[f"crop_aspect:{req.aspect}"])


@geometry_router.post("/crop-auto", summary="قصّ تلقائي للحواف المتجانسة")
def crop_auto(req: CropAutoRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(geometric.crop_auto(img, req.tolerance, req.padding), started, operations=["crop_auto"])


@geometry_router.post("/crop-content", summary="قصّ إلى حدود المحتوى غير الشفاف")
def crop_content(req: CropContentRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(geometric.crop_to_content(img, req.padding), started, operations=["crop_content"])


@geometry_router.post("/resize", summary="تغيير الحجم")
def resize(req: ResizeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = geometric.resize(img, req.width, req.height, req.percent, req.mode,
                           req.resample, req.allow_upscale)
    return respond(out, started, operations=[f"resize:{req.mode}"])


@geometry_router.post("/rotate", summary="دوران بزاوية حرة")
def rotate(req: RotateRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = geometric.rotate(img, req.angle, req.expand, req.fill, req.fill_transparent)
    return respond(out, started, operations=[f"rotate:{req.angle}"])


@geometry_router.post("/rotate90", summary="دوران بمضاعفات 90° (بلا فقد جودة)")
def rotate90(req: Rotate90Request) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(geometric.rotate90(img, req.times), started, operations=[f"rotate90:{req.times}"])


@geometry_router.post("/flip", summary="قلب أفقي/رأسي")
def flip(req: FlipRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(geometric.flip(img, req.direction), started, operations=[f"flip:{req.direction}"])


@geometry_router.post("/transpose", summary="تبديل مصفوفي")
def transpose(req: TransposeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(geometric.transpose(img, req.mode), started, operations=[f"transpose:{req.mode}"])


@geometry_router.post("/straighten", summary="تعديل ميل الصورة")
def straighten(req: RotateRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(geometric.straighten(img, req.angle), started, operations=[f"straighten:{req.angle}"])


@geometry_router.post("/deskew", summary="اكتشاف الميل وتصحيحه تلقائياً")
def deskew(req: ImageRequestOnly) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out, angle = geometric.deskew_auto(img)
    return respond(out, started, operations=["deskew"], extra={"detected_angle": round(angle, 3)})


@geometry_router.post("/perspective", summary="تحويل منظوري بأربع نقاط")
def perspective(req: PerspectiveRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = geometric.perspective(img, src=req.src, dst=req.dst, coeffs=req.coeffs)
    return respond(out, started, operations=["perspective"])


@geometry_router.post("/pad", summary="توسيع اللوحة")
def pad(req: PadRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    if req.percent is not None:
        out = geometric.pad_percent(img, req.percent, req.color, req.transparent)
    else:
        out = geometric.pad(img, req.top, req.right, req.bottom, req.left, req.color, req.transparent)
    return respond(out, started, operations=["pad"])


@geometry_router.post("/border", summary="إضافة إطار")
def border(req: BorderRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = geometric.add_border(img, req.width, req.color, req.style, req.inner_gap)
    return respond(out, started, operations=[f"border:{req.style}"])


@geometry_router.post("/shadow", summary="ظل سقوط خلف المحتوى")
def shadow(req: ShadowRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = geometric.add_shadow(img, req.opacity, req.blur_radius, tuple(req.offset), req.color)
    return respond(out, started, operations=["shadow"])


@geometry_router.post("/canvas", summary="ملاءمة الصورة داخل لوحة بمقاس محدد")
def canvas(req: CanvasRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = geometric.fit_to_canvas(img, req.width, req.height, req.mode,
                                  req.background, req.transparent, req.position)
    return respond(out, started, operations=[f"canvas:{req.mode}"])


# ==============================================================================
#  3) تحسينات البكسل
# ==============================================================================
pixel_router = APIRouter(prefix="/pixel", tags=["تحسينات البكسل"])


def _to_adjustments(req: AdjustRequest) -> pixel_ops.PixelAdjustments:
    return pixel_ops.PixelAdjustments(
        exposure=req.exposure, white_balance=req.white_balance, wb_strength=req.wb_strength,
        temperature=req.temperature, tint=req.tint, brightness=req.brightness,
        contrast=req.contrast, levels=req.levels, gamma=req.gamma,
        curves=[tuple(p) for p in req.curves] if req.curves else None,
        curves_channel=req.curves_channel, saturation=req.saturation, vibrance=req.vibrance,
        hue=req.hue, color_balance=req.color_balance, channel_mixer=req.channel_mixer,
        posterize_levels=req.posterize_levels, threshold_value=req.threshold_value,
        threshold_mode=req.threshold_mode, invert=req.invert, grayscale=req.grayscale,
        auto_levels=req.auto_levels, auto_contrast=req.auto_contrast,
    )


@pixel_router.post("/adjust", summary="ضبط شامل (سطوع/تباين/تشبع/تعرض/جاما/حرارة/منحنيات…)")
def adjust(req: AdjustRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    adj = _to_adjustments(req)
    if adj.is_identity():
        raise InvalidParameterError("كل معاملات الضبط في قيمها المحايدة؛ لا يوجد تغيير لتطبيقه.")
    out = pixel_ops.apply_pixel_adjustments(img, adj)
    if req.threshold_value is not None and req.threshold_color:
        out = pixel_ops.threshold(out, req.threshold_value, req.threshold_mode, color=True)
    applied = [k for k, v in adj.__dict__.items() if v not in (0, 0.0, None, False) and not (k == "gamma" and v == 1.0)]
    return respond(out, started, operations=[f"adjust:{k}" for k in applied])


@pixel_router.post("/curves", summary="منحنيات (Curves)")
def curves(req: CurvesRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = pixel_ops.adjust_curves(img, [tuple(p) for p in req.points], req.channel)
    return respond(out, started, operations=[f"curves:{req.channel}"])


@pixel_router.post("/levels", summary="مستويات (Levels)")
def levels(req: LevelsRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = pixel_ops.adjust_levels(img, req.in_black, req.in_white, req.gamma, req.out_black, req.out_white)
    return respond(out, started, operations=["levels"])


@pixel_router.post("/threshold", summary="عتبة (Threshold) بعدة أنماط")
def threshold(req: ThresholdRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = pixel_ops.threshold(img, req.value, req.mode, req.color)
    return respond(out, started, operations=[f"threshold:{req.mode}"])


@pixel_router.post("/auto-levels", summary="تمديد تلقائي للمستويات")
def auto_levels(req: ImageRequestOnly) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(pixel_ops.auto_levels(img), started, operations=["auto_levels"])


@pixel_router.post("/auto-contrast", summary="تباين تلقائي")
def auto_contrast(req: ImageRequestOnly) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(pixel_ops.auto_contrast(img), started, operations=["auto_contrast"])


@pixel_router.post("/white-balance", summary="توازن أبيض تلقائي")
def white_balance(req: AdjustRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = pixel_ops.white_balance(img, req.white_balance or "grayworld", req.wb_strength)
    return respond(out, started, operations=[f"white_balance:{req.white_balance or 'grayworld'}"])


@pixel_router.post("/black-white", summary="أبيض وأسود بخلط قنوات")
def black_white(req: CreativeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    mix = req.params.get("mix") or [0.299, 0.587, 0.114]
    if len(mix) != 3:
        raise InvalidParameterError("mix يجب أن تحتوي 3 قيم (أوزان R, G, B).")
    out = pixel_ops.black_and_white(img, tuple(float(v) for v in mix))
    return respond(out, started, operations=["black_white"])


@pixel_router.post("/split-toning", summary="تلوين منفصل للظلال والإضاءات")
def split_toning(req: CreativeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    p = req.params
    out = pixel_ops.split_toning(
        img, float(p.get("shadow_hue", 210)), float(p.get("highlight_hue", 40)),
        float(p.get("balance", 0)),
    )
    return respond(out, started, operations=["split_toning"])


@pixel_router.post("/selective-color", summary="تعديل انتقائي لنطاق لوني")
def selective_color(req: CreativeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    p = req.params
    out = pixel_ops.selective_color(img, float(p.get("hue", 0)), float(p.get("width", 60)), float(p.get("scale", 0.5)))
    return respond(out, started, operations=["selective_color"])


@pixel_router.post("/posterize", summary="بوسترة")
def posterize(req: CreativeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = pixel_ops.posterize(img, int(req.params.get("levels", 4)))
    return respond(out, started, operations=["posterize"])


@pixel_router.post("/invert", summary="عكس الألوان")
def invert(req: ImageRequestOnly) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(pixel_ops.invert(img), started, operations=["invert"])


@pixel_router.post("/grayscale", summary="تحويل إلى تدرّج رمادي")
def grayscale(req: ImageRequestOnly) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    return respond(pixel_ops.black_and_white(img), started, operations=["grayscale"])


# ==============================================================================
#  4) الفلاتر
# ==============================================================================
filters_router = APIRouter(prefix="/filters", tags=["الفلاتر"])


@filters_router.get("/catalog", summary="قائمة الفلاتر ومعاملاتها")
def filter_catalog() -> Dict[str, Any]:
    return {"filters": filters.FILTER_CATALOG, "blur_modes": list(filters.BLUR_MODES),
            "sharpen_modes": list(filters.SHARPEN_MODES)}


@filters_router.post("/blur", summary="تنعيم بثمانية أنماط")
def blur(req: BlurRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.blur(img, req.mode, req.radius, req.angle, req.strength, tuple(req.center))
    return respond(out, started, operations=[f"blur:{req.mode}"])


@filters_router.post("/surface-smooth", summary="تنعيم أسطح/بشرة مع الحفاظ على التفاصيل")
def surface_smooth(req: SurfaceSmoothRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.surface_smooth(img, req.strength, req.detail)
    return respond(out, started, operations=["surface_smooth"])


@filters_router.post("/sharpen", summary="تحديد بأربعة أنماط")
def sharpen(req: SharpenRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.sharpen(img, req.mode, req.amount, req.radius, req.threshold)
    return respond(out, started, operations=[f"sharpen:{req.mode}"])


@filters_router.post("/denoise", summary="تقليل الضوضاء")
def denoise(req: DenoiseRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.denoise(img, req.strength, req.mode)
    return respond(out, started, operations=[f"denoise:{req.mode}"])


@filters_router.post("/edges", summary="كشف الحواف (Canny)")
def edges(req: EdgesRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.detect_edges(img, req.low, req.high, req.invert_colors)
    return respond(out, started, operations=["edges"])


@filters_router.post("/sobel", summary="تدرّج سوبل")
def sobel(req: CreativeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.sobel_edges(img, float(req.params.get("scale", 1.0)))
    return respond(out, started, operations=["sobel"])


@filters_router.post("/emboss", summary="نحت بارز")
def emboss(req: CreativeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.emboss(img, float(req.params.get("strength", 1.0)))
    return respond(out, started, operations=["emboss"])


@filters_router.post("/oil-paint", summary="رسم زيتي")
def oil_paint(req: OilPaintRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.oil_paint(img, req.radius, req.intensity)
    return respond(out, started, operations=["oil_paint"])


@filters_router.post("/sketch", summary="رسم بالقلم الرصاص")
def sketch(req: SketchRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.sketch(img, req.threshold, req.invert_colors)
    return respond(out, started, operations=["sketch"])


@filters_router.post("/pencil-color", summary="رسم ملوّن بالقلم الرصاص")
def pencil_color(req: PencilRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.pencil_color(img, req.sigma, req.shade)
    return respond(out, started, operations=["pencil_color"])


@filters_router.post("/halftone", summary="نقاط طباعة (Halftone)")
def halftone(req: HalftoneRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.halftone(img, req.dot_size, color=req.color)
    return respond(out, started, operations=["halftone"])


@filters_router.post("/pixelate", summary="فسيفساء/بكسلة")
def pixelate(req: PixelateRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.pixelate(img, req.block)
    return respond(out, started, operations=["pixelate"])


@filters_router.post("/vignette", summary="تظليل الحواف")
def vignette(req: VignetteRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.vignette(img, req.strength, req.radius)
    return respond(out, started, operations=["vignette"])


@filters_router.post("/grain", summary="حبوب فيلم")
def grain(req: GrainRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.grain(img, req.amount, req.seed)
    return respond(out, started, operations=["grain"])


@filters_router.post("/glow", summary="توهّج ناعم")
def glow(req: GlowRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.glow(img, req.amount, req.radius)
    return respond(out, started, operations=["glow"])


@filters_router.post("/hdr", summary="مظهر HDR محلي")
def hdr(req: CreativeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.hdr_look(img, float(req.params.get("strength", 0.6)))
    return respond(out, started, operations=["hdr_look"])


@filters_router.post("/apply", summary="تطبيق فلتر بالاسم (موجّه عام)")
def apply_filter(req: GenericFilterRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = filters.apply_filter(img, req.name, **req.params)
    return respond(out, started, operations=[f"filter:{req.name}"])


# ==============================================================================
#  5) إزالة الخلفية (خوارزميات كلاسيكية — بلا ذكاء اصطناعي)
# ==============================================================================
segmentation_router = APIRouter(prefix="/segmentation", tags=["إزالة الخلفية"])


@segmentation_router.get("/methods", summary="خوارزميات إزالة الخلفية المتاحة")
def methods() -> Dict[str, Any]:
    return {
        "ai_models_used": False,
        "note": "كل الخوارزميات كلاسيكية (OpenCV) — لا توجد أي نماذج ذكاء اصطناعي في المشروع.",
        "methods": [
            {"id": "auto", "name": "تلقائي", "speed": "سريع",
             "desc": "يجرّب الطرق السريعة ويختار الأفضل بدالة تقييم، ويستدعي GrabCut عند الحاجة فقط."},
            {"id": "flood_fill", "name": "تعبئة فيضية", "speed": "فوري",
             "desc": "من الحدود إلى الداخل بتسامح لوني تكيّفي — الأفضل للخلفيات الموحّدة."},
            {"id": "color_key", "name": "عزل لوني", "speed": "سريع",
             "desc": "مسافة لونية في فضاء LAB/HSV عن عناقيد لون الخلفية."},
            {"id": "edge_cut", "name": "قصّ بالحواف", "speed": "فوري",
             "desc": "Canny + تجاويف + غلاف محدّب — للأجسام الحادة الحواف."},
            {"id": "kmeans", "name": "تجميع لوني", "speed": "سريع",
             "desc": "K-Means وإبقاء العناقيد المختلفة عن لون الخلفية."},
            {"id": "grabcut", "name": "GrabCut", "speed": "بطيء (ثوانٍ)",
             "desc": "تقسيم بالرسوم البيانية — الأدق للأجسام العامة، ويدعم التلميحات اليدوية."},
            {"id": "wand", "name": "عصا سحرية", "speed": "سريع",
             "desc": "نقرة على الكائن فيُنتقى بلونه (نمو فيضي في LAB) مع صقل GrabCut للحواف."},
            {"id": "smart", "name": "عصا ذكية", "speed": "سريع",
             "desc": "تختار بذور الجسم تلقائياً (أبعد البكسلات عن نموذج الخلفية) ثم تنمّيها."},
        ],
    }


@segmentation_router.post("/remove-background", summary="إزالة الخلفية")
def remove_background(req: RemoveBgRequest) -> Dict[str, Any]:
    """
    يُرجع صورة RGBA شفافة + القناع + الخوارزمية المستخدمة + درجات التقييم.
    """
    started = time.perf_counter()
    img = prepare(req.image)

    hint = None
    if req.hint_mask:
        hint_img = prepare(req.hint_mask).convert("L")
        hint = np.array(hint_img)

    res = segmentation.remove_background(
        img,
        method=req.method, rect=req.rect, hint_mask=hint,
        seeds=req.seeds, iterations=req.iterations,
        wand_tolerance=req.wand_tolerance, wand_contiguous=req.wand_contiguous,
        tolerance=req.tolerance, softness=req.softness, space=req.space,
        low=req.low, high=req.high, convex=req.convex, k=req.k,
        keep_clusters=req.keep_clusters,
        mask_options=segmentation.MaskOptions(
            feather=req.feather, shrink=req.shrink, despeckle=req.despeckle,
            fill_holes=req.fill_holes, decontaminate=req.decontaminate,
            matte=req.matte,
        ),
        return_mask=req.return_mask,
    )

    out = res.image
    if req.crop_to_content:
        out = geometric.crop_to_content(out, 8)

    extra: Dict[str, Any] = {
        "method": res.method,
        "foreground_ratio": res.foreground_ratio,
        "scores": res.scores,
    }
    if req.return_mask and res.mask is not None:
        extra["mask"] = encode_image(res.mask.convert("L"), "png", keep_alpha=False).data
    return respond_dict(out, started, "png", operations=[f"remove_bg:{res.method}"], extra=extra)


@segmentation_router.post("/mask", summary="تطبيق قناع خارجي على الصورة")
def apply_mask(req: ApplyMaskRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    mask = prepare(req.mask).convert("L")
    out = segmentation.apply_mask(img, mask, req.invert)
    return respond(out, started, operations=["apply_mask"])


@segmentation_router.post("/preview-mask", summary="إرجاع القناع فقط (للمعاينة السريعة)")
def preview_mask(req: RemoveBgRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    hint = None
    if req.hint_mask:
        hint = np.array(prepare(req.hint_mask).convert("L"))
    res = segmentation.remove_background(img, method=req.method, rect=req.rect,
                                         hint_mask=hint, seeds=req.seeds,
                                         iterations=req.iterations,
                                         wand_tolerance=req.wand_tolerance,
                                         wand_contiguous=req.wand_contiguous,
                                         tolerance=req.tolerance, softness=req.softness,
                                         space=req.space, low=req.low, high=req.high,
                                         convex=req.convex, k=req.k, keep_clusters=req.keep_clusters,
                                         mask_options=segmentation.MaskOptions(
                                             feather=0.0, matte=False, despeckle=0,
                                             fill_holes=False, decontaminate=0.0))
    mask_png = encode_image(res.mask.convert("L"), "png", keep_alpha=False)
    return {
        "image": mask_png.data,
        "meta": {
            "format": "png", "mime": "image/png", "width": mask_png.width, "height": mask_png.height,
            "size_bytes": mask_png.size_bytes, "size_kb": round(mask_png.size_bytes / 1024, 2),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "operations": [f"mask:{res.method}"],
        },
        "method": res.method,
        "scores": res.scores,
    }


# ==============================================================================
#  6) الدمج والمزج
# ==============================================================================
composite_router = APIRouter(prefix="/composite", tags=["الدمج والمزج"])


@composite_router.get("/blend-modes", summary="أنماط المزج المدعومة")
def blend_modes() -> Dict[str, Any]:
    return {"modes": sorted(composite.BLEND_MODES), "groups": composite.BLEND_GROUPS}


@composite_router.post("/blend", summary="دمج طبقة فوق صورة بنمط مزج")
def blend(req: BlendRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    base = prepare(req.image)
    layer = prepare(req.second)
    out = composite.blend_images(base, layer, req.mode, req.opacity, req.x, req.y, req.anchor, req.scale)
    return respond(out, started, operations=[f"blend:{req.mode}"])


@composite_router.post("/blend-seamless", summary="مزج هرمي سلس (Laplacian Pyramid)")
def blend_seamless(req: SeamlessRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    base = prepare(req.image)
    layer = prepare(req.second)
    mask = prepare(req.mask).convert("L") if req.mask else None
    out = composite.blend_seamless(base, layer, mask, req.x, req.y, req.anchor, req.levels, req.feather)
    return respond(out, started, operations=[f"blend_seamless:{req.levels}"])


@composite_router.post("/merge", summary="دمج عدة صور في تخطيط واحد")
def merge(req: MergeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    imgs = [load_image(p).image for p in req.images]
    out = composite.merge_images(imgs, req.layout, req.gap, req.background, req.transparent,
                                 req.align, req.radius, req.border, req.border_color)
    return respond(out, started, operations=[f"merge:{req.layout}"])


@composite_router.post("/pip", summary="صورة داخل صورة (PiP)")
def pip(req: PipRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    base = prepare(req.image)
    inset = prepare(req.second)
    out = composite.picture_in_picture(base, inset, req.size, req.anchor, req.margin,
                                       req.border, req.border_color, req.radius, req.shadow)
    return respond(out, started, operations=["pip"])


@composite_router.post("/watermark-text", summary="علامة مائية نصية")
def watermark_text(req: WatermarkTextRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = composite.watermark_text(img, req.text, req.font_size, req.color, req.opacity,
                                   req.position, req.margin, req.tile, req.angle, req.outline)
    return respond(out, started, operations=["watermark_text"])


@composite_router.post("/watermark-image", summary="علامة مائية بشعار")
def watermark_image(req: WatermarkImageRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    logo = prepare(req.second)
    out = composite.watermark_image(img, logo, req.size, req.position, req.margin, req.opacity, req.tile)
    return respond(out, started, operations=["watermark_image"])


# ==============================================================================
#  7) المؤثرات الإبداعية
# ==============================================================================
creative_router = APIRouter(prefix="/creative", tags=["مؤثرات إبداعية"])


@creative_router.get("/catalog", summary="قائمة المؤثرات الإبداعية")
def creative_catalog() -> Dict[str, Any]:
    return {"effects": creative.CREATIVE_CATALOG}


@creative_router.post("/apply", summary="تطبيق مؤثر إبداعي")
def creative_apply(req: CreativeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    out = creative.apply_creative(img, req.name, **req.params)
    return respond(out, started, operations=[f"creative:{req.name}"])


@creative_router.post("/double-exposure", summary="تعريض مزدوج بين صورتين")
def double_exposure(req: DoubleExposureRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    second = prepare(req.second)
    out = creative.double_exposure(img, second, req.amount, req.mode)
    return respond(out, started, operations=["double_exposure"])


# ==============================================================================
#  8) مكتبة الخلفيات
# ==============================================================================
backgrounds_router = APIRouter(prefix="/backgrounds", tags=["مكتبة الخلفيات"])


@backgrounds_router.get("", summary="قائمة خلفيات المنتجات المولّدة برمجياً")
def list_backgrounds(category: Optional[str] = Query(None, description="تصفية حسب الفئة")) -> Dict[str, Any]:
    return {
        "total": len(backgrounds.CATALOG),
        "categories": [{"id": c, "name": backgrounds.CATEGORY_NAMES[c],
                        "count": len(backgrounds.list_backgrounds(c))} for c in backgrounds.CATEGORIES],
        "items": backgrounds.list_backgrounds(category),
        "note": "كل الخلفيات مولّدة بالخوارزميات داخل الخادم — لا توجد صور خارجية.",
    }


@backgrounds_router.get("/preview/{bg_id}", summary="صورة مصغّرة للخلفية")
def background_preview(bg_id: str, size: int = Query(256, ge=64, le=1024)) -> Response:
    img = backgrounds.generate_background(bg_id, size=size)
    enc = encode_image(img, "jpeg", quality=82, keep_alpha=False)
    return Response(content=base64.b64decode(enc.data), media_type="image/jpeg")


@backgrounds_router.post("/generate", summary="توليد خلفية بمقاس محدد")
def generate(req: BackgroundOnlyRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = backgrounds.generate_background(req.background, size=req.size)
    return respond(img, started, "png", keep_alpha=False, operations=[f"background:{req.background}"])


@backgrounds_router.post("/compose", summary="تركيب المنتج على خلفية من المكتبة")
def compose(req: BackgroundRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    product = prepare(req.image)
    bg = backgrounds.generate_background(req.background, size=req.size)
    out = backgrounds.compose_on_background(product, bg, req.scale, req.position,
                                            req.shadow, req.reflection, req.padding_bottom)
    return respond(out, started, "png", keep_alpha=False,
                   operations=[f"compose:{req.background}"])


# ==============================================================================
#  9) التحليل
# ==============================================================================
analysis_router = APIRouter(prefix="/analysis", tags=["تحليل الصورة"])


@analysis_router.post("", summary="تحليل شامل: مدرّج، مقاييس، ألوان سائدة، EXIF، اقتراحات")
def analyze(req: AnalysisRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    data = analysis.full_analysis(img)
    data["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    if req.palette:
        data["palette_image"] = encode_image(analysis.color_palette_image(img, 6), "png", keep_alpha=False).data
        data["histogram_image"] = encode_image(analysis.channel_histogram_image(img), "png", keep_alpha=False).data
    return data


@analysis_router.post("/colors", summary="الألوان السائدة فقط")
def colors(req: CreativeRequest) -> Dict[str, Any]:
    img = prepare(req.image)
    return {"colors": analysis.dominant_colors(img, int(req.params.get("k", 6)))}


@analysis_router.post("/suggestions", summary="اقتراحات تحرير تلقائية")
def suggestions(req: ImageRequestOnly) -> Dict[str, Any]:
    img = prepare(req.image)
    return {"suggestions": analysis.suggest_edits(img)}


# ==============================================================================
#  10) السلاسل والدفعات
# ==============================================================================
pipeline_router = APIRouter(prefix="/pipeline", tags=["السلاسل والدفعات"])


@pipeline_router.get("/operations", summary="خطوات السلسلة المدعومة")
def pipeline_operations() -> Dict[str, Any]:
    return {
        "operations": batch_service.operation_names(),
        "example": {
            "steps": [
                {"op": "remove_bg", "method": "auto"},
                {"op": "adjust", "brightness": 5, "contrast": 12, "saturation": 10},
                {"op": "sharpen", "amount": 0.8},
                {"op": "background", "background": "marble_white", "scale": 0.6},
                {"op": "resize", "width": 1000, "height": 1000, "mode": "fit"},
                {"op": "watermark", "text": "© متجري", "opacity": 0.4},
            ]
        },
    }


@pipeline_router.post("/run", summary="تنفيذ سلسلة عمليات على صورة واحدة")
def pipeline_run(req: PipelineRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    img = prepare(req.image)
    res = batch_service.run_pipeline(img, req.steps, strict=req.strict)
    return respond(
        res.image, started,
        operations=[f"{s.op}:{'ok' if s.ok else 'fail'}" for s in res.steps],
        extra={"steps": [{"index": s.index, "op": s.op, "ok": s.ok, "message": s.message,
                          "width": s.size[0] if s.size else None,
                          "height": s.size[1] if s.size else None} for s in res.steps]},
    )


@pipeline_router.post("/batch", summary="معالجة دفعة صور بنفس السلسلة")
def batch_run(req: BatchRequest) -> Dict[str, Any]:
    imgs = [load_image(p).image for p in req.images]
    names = req.names or [f"image_{i + 1}" for i in range(len(imgs))]
    results = batch_service.process_batch(imgs, req.steps, names=names, strict=False)

    items: List[Dict[str, Any]] = []
    for r in results:
        item: Dict[str, Any] = {
            "index": r.index, "name": r.name, "ok": r.ok, "error": r.error,
            "elapsed_ms": r.elapsed_ms,
        }
        if r.ok and r.image is not None:
            enc = encode_image(r.image, req.format, quality=req.quality)
            item["image"] = enc.data
            item["width"], item["height"] = enc.width, enc.height
        items.append(item)

    return {
        "items": items,
        "total": len(items),
        "succeeded": sum(1 for i in items if i["ok"]),
        "failed": sum(1 for i in items if not i["ok"]),
    }


# ==============================================================================
#  11) النظام والتنزيل
# ==============================================================================
# ==============================================================================
#  9) الترميم والتنقيح والمستندات (خوارزميات كلاسيكية — بلا ذكاء اصطناعي)
# ==============================================================================
restore_router = APIRouter(prefix="/pro", tags=["الترميم والتنقيح والمستندات"])


@restore_router.post("/restore-old-photo", summary="ترميم الصور القديمة")
def restore_old_photo(req: RestoreRequest) -> Dict[str, Any]:
    """
    ترميم كلاسيكي: كشف الخدوش والغبار مورفولوجياً (Top-Hat/Black-Hat) ثم
    ترميمها بالفيضان (Inpainting)، موازنة لونية وCLAHE للبهتان، تقليل ضوضاء
    يحافظ على الحواف، وتحديد خفيف — كله بلا أي نموذج ذكاء اصطناعي.
    """
    started = time.perf_counter()
    img = prepare(req.image)
    out, stats = restore.restore_old_photo(
        img,
        restore.RestoreOptions(
            scratches=req.scratches, dust=req.dust, recolor=req.recolor,
            denoise=req.denoise, sharpen=req.sharpen,
        ),
    )
    return respond_dict(out, started, operations=["restore_old_photo"], extra=stats)


@restore_router.post("/retouch-faces", summary="تنقيح الوجوه")
def retouch_faces(req: RetouchRequest) -> Dict[str, Any]:
    """
    تنقيح كلاسيكي: كشف الوجوه (Haar Cascade) ثم تنعيم البشرة (Bilateral
    بانتقائية قناع البشرة واستثناء الملامح)، إزالة العيوب بالترميم، وإزالة
    العين الحمراء — ويعيد عدد الوجوه المكتشفة.
    """
    started = time.perf_counter()
    img = prepare(req.image)
    out, stats = restore.retouch_faces(
        img,
        restore.RetouchOptions(smooth=req.smooth, blemish=req.blemish, redeye=req.redeye),
    )
    return respond_dict(out, started, operations=["retouch_faces"], extra=stats)


@restore_router.post("/document-scan", summary="وضع المستندات")
def document_scan(req: DocumentRequest) -> Dict[str, Any]:
    """
    معالجة مستند مصوّر: كشف حدود الورقة (أكبر رباعي) وتصحيحها منظوراً، ثم
    أبيض/أسود نظيف (أعتاب تكيفي) أو «تحسين» بخلفية بيضاء مع لون الحبر، أو
    توحيد إضاءة مع الحفاظ على الألوان.
    """
    started = time.perf_counter()
    img = prepare(req.image)
    out, stats = restore.document_scan(img, mode=req.mode, perspective=req.perspective)
    return respond_dict(out, started, operations=[f"document_scan:{req.mode}"],
                        extra={"perspective_applied": bool(stats["perspective_applied"])})


system_router = APIRouter(tags=["النظام"])


@system_router.post("/download", summary="تنزيل الصورة كملف ثنائي")
def download(req: DownloadRequest) -> Response:
    import base64
    from urllib.parse import quote

    img = prepare(req.image)
    fmt = req.format or (req.filename.rsplit(".", 1)[-1] if "." in req.filename else "png")
    enc = encode_image(img, fmt, quality=req.quality)
    name = quote(req.filename if req.filename.lower().endswith(enc.format) or "." in req.filename
                 else f"{req.filename}.{enc.format}")
    return Response(
        content=base64.b64decode(enc.data),
        media_type=enc.mime,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@system_router.get("/health", summary="فحص صحة الخادم وقدراته")
def health() -> Dict[str, Any]:
    import platform

    import cv2
    import numpy
    import PIL
    from fastapi import __version__ as fastapi_version

    from ...core.settings import settings

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "python": platform.python_version(),
        "libraries": {
            "fastapi": fastapi_version,
            "pillow": PIL.__version__,
            "opencv": cv2.__version__,
            "numpy": numpy.__version__,
        },
        "limits": {
            "max_upload_bytes": settings.MAX_UPLOAD_BYTES,
            "max_pixels": settings.MAX_PIXELS,
            "max_batch_images": settings.MAX_BATCH_IMAGES,
        },
        "capabilities": {
            "ai_models_used": False,
            "formats_output": settings.SUPPORTED_OUTPUT,
            "filters": len(filters.FILTER_CATALOG),
            "blend_modes": len(composite.BLEND_MODES),
            "creative_effects": len(creative.CREATIVE_CATALOG),
            "backgrounds": len(backgrounds.CATALOG),
            "segmentation_methods": list(segmentation.METHODS),
            "pipeline_operations": batch_service.operation_names(),
        },
    }


ROUTERS: List[APIRouter] = [
    convert_router, geometry_router, pixel_router, filters_router, segmentation_router,
    composite_router, creative_router, backgrounds_router, analysis_router,
    restore_router, pipeline_router, system_router,
]

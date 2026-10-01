"""
المخططات المشتركة (Pydantic Schemas).
=====================================
نمط موحّد لكل الطلبات والاستجابات:
  الطلب  : { "image": "<base64 أو data URL>", ...معاملات }
  الاستجابة: { "image": "<base64>", "meta": {...} }
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

# ------------------------------------------------------------------------------
#  أساسيات
# ------------------------------------------------------------------------------
class ImageMeta(BaseModel):
    """البيانات الوصفية للصورة الناتجة."""

    format: str = Field(..., description="الصيغة النهائية")
    mime: str = Field(..., description="نوع MIME")
    width: int
    height: int
    size_bytes: int
    size_kb: float
    elapsed_ms: float = Field(0.0, description="زمن المعالجة على الخادم")
    operations: List[str] = Field(default_factory=list, description="العمليات المنفّذة")


class ImageResponse(BaseModel):
    """الاستجابة الموحّدة: صورة Base64 + بيانات وصفية."""

    image: str = Field(..., description="الصورة الناتجة بترميز Base64 (بدون بادئة data:)")
    meta: ImageMeta


class MaskResponse(ImageResponse):
    """استجابة تتضمن قناعاً (تُستخدم في إزالة الخلفية)."""

    mask: Optional[str] = Field(None, description="قناع الألفا بترميز Base64 (صورة رمادية)")
    method: Optional[str] = Field(None, description="الخوارزمية المستخدمة فعلياً")
    foreground_ratio: Optional[float] = None
    scores: Dict[str, float] = Field(default_factory=dict)


class ImageRequest(BaseModel):
    """الطلب الأساسي: صورة واحدة (بعض النقاط تعيد استخدامه حيث لا حاجة لمعاملات)."""

    model_config = ConfigDict(json_schema_extra={
        "examples": [{"image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg..."}]
    })

    image: str = Field(..., description="الصورة بترميز Base64 أو data URL")


class TwoImageRequest(ImageRequest):
    """طلب يتضمن صورتين (الدمج والمزج)."""

    second: str = Field(..., description="الصورة الثانية بترميم Base64 أو data URL")


class ImageListRequest(BaseModel):
    """طلب يتضمن قائمة صور (الدفعات)."""

    images: List[str] = Field(..., min_length=1, description="قائمة صور Base64")
    names: Optional[List[str]] = Field(None, description="أسماء الصور (اختياري)")


# ------------------------------------------------------------------------------
#  تحويل الصيغ
# ------------------------------------------------------------------------------
class ConvertRequest(ImageRequest):
    """تحويل إلى صيغة أخرى مع خيارات الترميز."""

    format: str = Field("png", description="الصيغة الهدف: png, jpeg, webp, bmp, tiff, gif, ico, avif, ppm")
    quality: Optional[int] = Field(None, ge=1, le=100, description="جودة الصيغ الفاقدة (JPEG/WEBP/AVIF)")
    background: str = Field("#ffffff", description="لون دمج الشفافية للصيغ غير الداعمة لها")
    keep_alpha: bool = Field(True, description="الحفاظ على الشفافية إن كانت الصيغة تدعمها")
    keep_exif: bool = Field(False, description="نقل بيانات EXIF")
    png_compression: int = Field(6, ge=0, le=9, description="مستوى ضغط PNG")
    optimize: bool = Field(True, description="تحسين حجم الملف")


# ------------------------------------------------------------------------------
#  العمليات الهندسية
# ------------------------------------------------------------------------------
class CropRequest(ImageRequest):
    box: List[float] = Field(..., min_length=4, max_length=4, description="(x, y, w, h)")
    unit: Literal["px", "ratio"] = "px"


class CropAspectRequest(ImageRequest):
    aspect: str = Field("1:1", description="النسبة: free, 1:1, 4:3, 3:2, 16:9, 9:16, 3:4, 2:3, 21:9, 5:4")
    anchor: Literal["center", "top", "bottom", "left", "right",
                    "top-left", "top-right", "bottom-left", "bottom-right"] = "center"


class CropAutoRequest(ImageRequest):
    tolerance: int = Field(12, ge=0, le=128)
    padding: int = Field(0, ge=0, le=400)


class CropContentRequest(ImageRequest):
    padding: int = Field(0, ge=0, le=400, description="هامش يترك حول المحتوى")


class ResizeRequest(ImageRequest):
    width: Optional[int] = Field(None, ge=1, le=12000)
    height: Optional[int] = Field(None, ge=1, le=12000)
    percent: Optional[float] = Field(None, gt=0, le=2000)
    mode: Literal["fit", "fill", "exact", "longest"] = "fit"
    resample: Literal["lanczos", "bicubic", "bilinear", "nearest", "box"] = "lanczos"
    allow_upscale: bool = True


class RotateRequest(ImageRequest):
    angle: float = Field(..., ge=-360, le=360)
    expand: bool = True
    fill: str = "#ffffff"
    fill_transparent: bool = True


class Rotate90Request(ImageRequest):
    times: int = Field(1, ge=1, le=3, description="عدد دورات 90°")


class FlipRequest(ImageRequest):
    direction: Literal["horizontal", "vertical"] = "horizontal"


class TransposeRequest(ImageRequest):
    mode: Literal["transpose", "transverse", "rotate_90", "rotate_180", "rotate_270"] = "transpose"


class PerspectiveRequest(ImageRequest):
    src: Optional[List[List[float]]] = Field(None, description="4 نقاط مصدر بنسب [0..1]")
    dst: Optional[List[List[float]]] = Field(None, description="4 نقاط هدف بنسب [0..1]")
    coeffs: Optional[List[float]] = Field(None, description="معاملات التحويل الثمانية مباشرة")


class PadRequest(ImageRequest):
    top: int = Field(0, ge=0, le=4000)
    right: int = Field(0, ge=0, le=4000)
    bottom: int = Field(0, ge=0, le=4000)
    left: int = Field(0, ge=0, le=4000)
    percent: Optional[float] = Field(None, ge=0, le=100, description="بديل عن القيم الأربع")
    color: str = "#ffffff"
    transparent: bool = False


class BorderRequest(ImageRequest):
    width: int = Field(10, ge=1, le=400)
    color: str = "#000000"
    style: Literal["solid", "double", "shadow", "polaroid", "rounded"] = "solid"
    inner_gap: int = Field(0, ge=0, le=300)


class ShadowRequest(ImageRequest):
    opacity: float = Field(0.5, ge=0, le=1)
    blur_radius: float = Field(12.0, ge=0, le=120)
    offset: List[int] = Field(default_factory=lambda: [8, 12], min_length=2, max_length=2)
    color: str = "#000000"


class CanvasRequest(ImageRequest):
    width: int = Field(..., ge=1, le=12000)
    height: int = Field(..., ge=1, le=12000)
    mode: Literal["contain", "cover", "stretch"] = "contain"
    background: str = "#ffffff"
    transparent: bool = False
    position: Literal["center", "top", "bottom", "left", "right"] = "center"


# ------------------------------------------------------------------------------
#  ضبط البكسل
# ------------------------------------------------------------------------------
class AdjustRequest(ImageRequest):
    """كل معاملات ضبط البكسل (القيم المحايدة لا تُطبَّق)."""

    exposure: float = Field(0.0, ge=-5, le=5, description="وحدات EV")
    white_balance: Optional[Literal["grayworld", "whitepatch"]] = None
    wb_strength: float = Field(1.0, ge=0, le=1)
    temperature: float = Field(0.0, ge=-100, le=100)
    tint: float = Field(0.0, ge=-100, le=100)
    brightness: float = Field(0.0, ge=-100, le=100)
    contrast: float = Field(0.0, ge=-100, le=100)
    levels: Optional[Dict[str, float]] = Field(
        None, description="{in_black, in_white, gamma, out_black, out_white} بمجال [0..1]")
    gamma: float = Field(1.0, gt=0.05, le=5)
    curves: Optional[List[List[float]]] = Field(None, description="نقاط [مدخل, مخرج] بمجال [0..1]")
    curves_channel: Literal["rgb", "r", "g", "b"] = "rgb"
    saturation: float = Field(0.0, ge=-100, le=100)
    vibrance: float = Field(0.0, ge=-100, le=100)
    hue: float = Field(0.0, ge=-180, le=180)
    color_balance: Optional[Dict[str, List[float]]] = Field(
        None, description="{shadows:[r,g,b], midtones:[...], highlights:[...]} بمجال [-100..100]")
    channel_mixer: Optional[List[List[float]]] = Field(None, description="مصفوفة 3×3")
    posterize_levels: Optional[int] = Field(None, ge=2, le=32)
    threshold_value: Optional[float] = Field(None, ge=0, le=255)
    threshold_mode: Literal["binary", "binary_inv", "otsu", "adaptive", "tozero", "trunc"] = "binary"
    threshold_color: bool = Field(False, description="تطبيق العتبة مع الحفاظ على الألوان")
    invert: bool = False
    grayscale: bool = False
    auto_levels: bool = False
    auto_contrast: bool = False


class CurvesRequest(ImageRequest):
    points: List[List[float]] = Field(..., min_length=2, description="نقاط [مدخل, مخرج] بمجال [0..1]")
    channel: Literal["rgb", "r", "g", "b"] = "rgb"


class LevelsRequest(ImageRequest):
    in_black: float = Field(0.0, ge=0, le=0.99)
    in_white: float = Field(1.0, gt=0.01, le=1)
    gamma: float = Field(1.0, ge=0.1, le=10)
    out_black: float = Field(0.0, ge=0, le=1)
    out_white: float = Field(1.0, ge=0, le=1)


class ThresholdRequest(ImageRequest):
    value: float = Field(128.0, ge=0, le=255)
    mode: Literal["binary", "binary_inv", "otsu", "adaptive", "tozero", "trunc"] = "binary"
    color: bool = False


# ------------------------------------------------------------------------------
#  الفلاتر
# ------------------------------------------------------------------------------
class BlurRequest(ImageRequest):
    mode: Literal["gaussian", "box", "motion", "radial_zoom", "radial_spin",
                  "surface", "bilateral", "nlmeans"] = "gaussian"
    radius: float = Field(3.0, ge=0.1, le=60)
    angle: float = Field(0.0, ge=-180, le=180, description="لنمط motion")
    strength: float = Field(1.0, ge=0, le=5, description="للضباب الشعاعي")
    center: List[float] = Field(default_factory=lambda: [0.5, 0.5], min_length=2, max_length=2)


class SharpenRequest(ImageRequest):
    mode: Literal["unsharp", "highpass", "laplacian", "detail"] = "unsharp"
    amount: float = Field(1.0, ge=0, le=5)
    radius: float = Field(2.0, ge=0.1, le=20)
    threshold: float = Field(0.0, ge=0, le=100)


class DenoiseRequest(ImageRequest):
    mode: Literal["nlmeans", "median", "bilateral"] = "nlmeans"
    strength: float = Field(1.0, ge=0.1, le=5)


class EdgesRequest(ImageRequest):
    low: int = Field(50, ge=0, le=255)
    high: int = Field(150, ge=0, le=255)
    invert_colors: bool = True


class OilPaintRequest(ImageRequest):
    radius: int = Field(4, ge=1, le=15)
    intensity: int = Field(24, ge=1, le=60)


class SketchRequest(ImageRequest):
    threshold: float = Field(8.0, ge=0, le=20)
    invert_colors: bool = False


class PencilRequest(ImageRequest):
    sigma: float = Field(0.06, ge=0.01, le=1)
    shade: float = Field(0.02, ge=0, le=0.15)


class HalftoneRequest(ImageRequest):
    dot_size: int = Field(6, ge=2, le=40)
    color: bool = False


class PixelateRequest(ImageRequest):
    block: int = Field(12, ge=2, le=200)


class VignetteRequest(ImageRequest):
    strength: float = Field(0.6, ge=0, le=1)
    radius: float = Field(0.75, ge=0, le=1)


class GrainRequest(ImageRequest):
    amount: float = Field(0.25, ge=0, le=1)
    seed: int = 7


class GlowRequest(ImageRequest):
    amount: float = Field(0.5, ge=0, le=1)
    radius: float = Field(12.0, ge=0.1, le=60)


class SurfaceSmoothRequest(ImageRequest):
    strength: float = Field(1.0, ge=0, le=3)
    detail: float = Field(0.5, ge=0, le=1)


class GenericFilterRequest(ImageRequest):
    name: str = Field(..., description="اسم الفلتر")
    params: Dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------------------
#  إزالة الخلفية
# ------------------------------------------------------------------------------
class RemoveBgRequest(ImageRequest):
    method: Literal["auto", "grabcut", "color_key", "flood_fill", "edge_cut", "kmeans",
                    "wand", "smart"] = "auto"
    rect: Optional[List[float]] = Field(None, min_length=4, max_length=4,
                                        description="(x, y, w, h) بنسب [0..1] حول الجسم")
    hint_mask: Optional[str] = Field(None, description="قناع تلميحات Base64: أبيض=جسم، أسود=خلفية، رمادي=مجهول")
    seeds: Optional[List[List[float]]] = Field(
        None, description="نقاط العصا السحرية [x, y, kind] بالبكسل — kind: 1 جسم، 0 خلفية")
    iterations: int = Field(8, ge=1, le=20, description="تكرارات GrabCut (كلما زادت تحسّنت الدقة)")
    wand_tolerance: float = Field(32.0, ge=2, le=120, description="تسامح العصا السحرية في فضاء LAB")
    wand_contiguous: bool = Field(True, description="نمو فيضي متصل من البذرة فقط")
    tolerance: float = Field(40.0, ge=1, le=200, description="تسامح العزل اللوني")
    softness: float = Field(20.0, ge=0, le=100)
    space: Literal["lab", "hsv", "rgb"] = "lab"
    low: int = Field(40, ge=0, le=255, description="عتبة Canny الدنيا")
    high: int = Field(120, ge=0, le=255, description="عتبة Canny العليا")
    convex: bool = Field(True, description="تغليف محدّب للجسم في edge_cut")
    k: int = Field(4, ge=2, le=8, description="عدد العناقيد في kmeans")
    keep_clusters: int = Field(0, ge=0, le=8, description="0 = إبقاء كل العناقيد المختلفة")
    feather: float = Field(1.5, ge=0, le=20, description="تنعيم الحافة")
    shrink: float = Field(0.0, ge=0, le=20, description="تقليص القناع لإزالة الهالة")
    despeckle: int = Field(120, ge=0, le=100000, description="حذف البقع الأصغر من هذه المساحة")
    fill_holes: bool = True
    decontaminate: float = Field(0.6, ge=0, le=1, description="إزالة تلوّث لون الخلفية عن الحواف")
    matte: bool = Field(True, description="تحسين الحواف بمرشّح موجّه (Guided-Filter Matting)")
    crop_to_content: bool = Field(False, description="قصّ النتيجة إلى حدود الجسم")
    return_mask: bool = Field(True, description="إرجاع القناع مع النتيجة")


class ApplyMaskRequest(ImageRequest):
    mask: str = Field(..., description="القناع Base64 (صورة رمادية)")
    invert: bool = False


# ------------------------------------------------------------------------------
#  الدمج
# ------------------------------------------------------------------------------
class BlendRequest(TwoImageRequest):
    mode: str = Field("normal", description="نمط المزج (19 نمطاً)")
    opacity: float = Field(1.0, ge=0, le=1)
    x: Optional[float] = Field(None, ge=-1, le=2, description="موضع أفقي نسبي [0..1]")
    y: Optional[float] = Field(None, ge=-1, le=2)
    anchor: Literal["center", "top-left", "top", "top-right", "left", "right",
                    "bottom-left", "bottom", "bottom-right"] = "center"
    scale: float = Field(1.0, gt=0.02, le=10)


class SeamlessRequest(TwoImageRequest):
    mask: Optional[str] = Field(None, description="قناع المزج Base64")
    x: Optional[float] = None
    y: Optional[float] = None
    anchor: str = "center"
    levels: int = Field(5, ge=1, le=8, description="عدد مستويات الهرم")
    feather: float = Field(20.0, ge=0, le=200)


class MergeRequest(ImageListRequest):
    layout: Literal["horizontal", "vertical", "grid", "stacked"] = "horizontal"
    gap: int = Field(0, ge=0, le=200)
    background: str = "#ffffff"
    transparent: bool = False
    align: Literal["center", "top", "bottom", "left", "right"] = "center"
    radius: int = Field(0, ge=0, le=400)
    border: int = Field(0, ge=0, le=60)
    border_color: str = "#dddddd"


class PipRequest(TwoImageRequest):
    size: float = Field(0.28, gt=0.02, le=0.9)
    anchor: Literal["bottom-right", "bottom-left", "top-right", "top-left", "center"] = "bottom-right"
    margin: float = Field(0.04, ge=0, le=0.3)
    border: int = Field(4, ge=0, le=60)
    border_color: str = "#ffffff"
    radius: int = Field(10, ge=0, le=300)
    shadow: bool = True


class WatermarkTextRequest(ImageRequest):
    text: str = Field(..., min_length=1, max_length=200)
    font_size: int = Field(36, ge=6, le=400)
    color: str = "#ffffff"
    opacity: float = Field(0.5, ge=0, le=1)
    position: Literal["bottom-right", "bottom-left", "top-right", "top-left",
                      "center", "bottom", "top"] = "bottom-right"
    margin: int = Field(24, ge=0, le=600)
    tile: bool = Field(False, description="تكرار العلامة على كامل الصورة")
    angle: float = Field(0.0, ge=-180, le=180)
    outline: bool = True


class WatermarkImageRequest(TwoImageRequest):
    size: float = Field(0.18, gt=0.01, le=0.9)
    position: Literal["bottom-right", "bottom-left", "top-right", "top-left", "center"] = "bottom-right"
    margin: float = Field(0.03, ge=0, le=0.3)
    opacity: float = Field(0.85, ge=0, le=1)
    tile: bool = False


# ------------------------------------------------------------------------------
#  المؤثرات الإبداعية
# ------------------------------------------------------------------------------
class CreativeRequest(ImageRequest):
    """
    مخطط عام للمؤثرات وللبعض من نقاط البكسل:
      name   — اسم المؤثر (اختياري؛ بعض النقاط تتجاهله).
      params — معاملات حرّة.
    """

    name: str = Field("", description="اسم المؤثر")
    params: Dict[str, Any] = Field(default_factory=dict)


class DoubleExposureRequest(TwoImageRequest):
    amount: float = Field(0.5, ge=0, le=1)
    mode: str = "screen"


# ------------------------------------------------------------------------------
#  الخلفيات
# ------------------------------------------------------------------------------
class BackgroundRequest(ImageRequest):
    background: str = Field("studio_white", description="معرّف الخلفية من المكتبة")
    size: int = Field(1200, ge=256, le=3000, description="مقاس الخلفية المولّدة")
    scale: float = Field(0.62, gt=0.05, le=0.95, description="حجم المنتج نسبياً")
    position: Literal["center", "bottom", "top"] = "center"
    shadow: bool = True
    reflection: bool = False
    padding_bottom: float = Field(0.06, ge=0, le=0.3)


class BackgroundOnlyRequest(BaseModel):
    background: str = "studio_white"
    size: int = Field(1200, ge=256, le=3000)


# ------------------------------------------------------------------------------
#  السلاسل والدفعات
# ------------------------------------------------------------------------------
class PipelineRequest(ImageRequest):
    steps: List[Dict[str, Any]] = Field(..., min_length=1, max_length=40)
    strict: bool = True


class BatchRequest(BaseModel):
    images: List[str] = Field(..., min_length=1, description="قائمة صور Base64")
    names: Optional[List[str]] = None
    steps: List[Dict[str, Any]] = Field(..., min_length=1, max_length=40)
    format: str = "png"
    quality: Optional[int] = Field(None, ge=1, le=100)


class BatchItemOut(BaseModel):
    index: int
    name: str
    ok: bool
    image: Optional[str] = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    width: Optional[int] = None
    height: Optional[int] = None


class BatchResponse(BaseModel):
    items: List[BatchItemOut]
    total: int
    succeeded: int
    failed: int


# ------------------------------------------------------------------------------
#  التحليل والنظام
# ------------------------------------------------------------------------------
class AnalysisRequest(ImageRequest):
    palette: bool = Field(True, description="إرجاع صورة شريط الألوان السائدة")


class DownloadRequest(BaseModel):
    image: str = Field(..., description="الصورة Base64 المراد تنزيلها")
    filename: str = Field("image.png", max_length=120)
    format: Optional[str] = Field(None, description="تحويل اختياري قبل التنزيل")
    quality: Optional[int] = Field(None, ge=1, le=100)


# ------------------------------------------------------------------------------
#  الترميم والتنقيح والمستندات
# ------------------------------------------------------------------------------
class RestoreRequest(ImageRequest):
    scratches: bool = Field(True, description="إزالة الخدوش الرفيعة")
    dust: bool = Field(True, description="إزالة الغبار والبقع الصغيرة")
    recolor: bool = Field(True, description="موازنة لونية + CLAHE للبهتان")
    denoise: float = Field(0.5, ge=0, le=1, description="قوة تقليل الضوضاء")
    sharpen: float = Field(0.4, ge=0, le=1, description="قوة التحديد النهائي")


class RetouchRequest(ImageRequest):
    smooth: float = Field(0.6, ge=0, le=1, description="قوة تنعيم البشرة")
    blemish: bool = Field(True, description="إزالة العيوب بالترميم")
    redeye: bool = Field(True, description="إزالة العين الحمراء")


class DocumentRequest(ImageRequest):
    mode: Literal["bw", "enhance", "color"] = Field(
        "enhance", description="bw: أبيض/أسود · enhance: خلفية بيضاء بلون الحبر · color: توحيد إضاءة")
    perspective: bool = Field(True, description="تصحيح منظوري تلقائي عند إيجاد حدود الورقة")


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    python: str
    libraries: Dict[str, str]
    limits: Dict[str, int]
    capabilities: Dict[str, Any]


__all__ = [n for n in dir() if n[0].isupper() and not n.startswith("_")]

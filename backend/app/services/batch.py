"""
محرك سير العمليات (Pipeline Engine) + المعالجة بالدفعات.
=======================================================
يصف المستخدم سلسلة خطوات (قائمة dicts)، وتُنفَّذ بالترتيب على كل صورة.
المحرك نفسه يُستخدم في نقطة batch وفي نقطة pipeline للصور المفردة.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from PIL import Image

from ..core.exceptions import AppError, InvalidParameterError
from . import composite, creative, filters, geometric, pixel_ops, segmentation  # noqa: F401
from ..core.settings import settings


# ==============================================================================
#  تعريف الخطوات
# ==============================================================================
def _op_resize(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.resize(
        img,
        width=p.get("width"),
        height=p.get("height"),
        percent=p.get("percent"),
        mode=p.get("mode", "fit"),
        resample=p.get("resample", "lanczos"),
        allow_upscale=bool(p.get("allow_upscale", True)),
    )


def _op_crop(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    box = p.get("box") or [0, 0, 1, 1]
    if len(box) != 4:
        raise InvalidParameterError("box يجب أن تحتوي 4 قيم (x, y, w, h).")
    return geometric.crop(img, box, unit=p.get("unit", "ratio"))


def _op_crop_aspect(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.crop_aspect(img, p.get("aspect", "1:1"), p.get("anchor", "center"))


def _op_crop_auto(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.crop_auto(img, int(p.get("tolerance", 12)), int(p.get("padding", 0)))


def _op_rotate(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.rotate(
        img, float(p.get("angle", 0)), expand=bool(p.get("expand", True)),
        fill=p.get("fill", "#ffffff"), fill_transparent=bool(p.get("fill_transparent", True)),
    )


def _op_rotate90(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.rotate90(img, int(p.get("times", 1)))


def _op_flip(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.flip(img, p.get("direction", "horizontal"))


def _op_transpose(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.transpose(img, p.get("mode", "transpose"))


def _op_perspective(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.perspective(img, src=p.get("src"), dst=p.get("dst"))


def _op_pad(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    if p.get("percent") is not None:
        return geometric.pad_percent(img, float(p["percent"]), p.get("color", "#ffffff"),
                                     bool(p.get("transparent", False)))
    return geometric.pad(img, int(p.get("top", 0)), int(p.get("right", 0)),
                         int(p.get("bottom", 0)), int(p.get("left", 0)),
                         p.get("color", "#ffffff"), bool(p.get("transparent", False)))


def _op_border(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.add_border(img, int(p.get("width", 10)), p.get("color", "#000000"),
                                p.get("style", "solid"), int(p.get("inner_gap", 0)))


def _op_shadow(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.add_shadow(img, float(p.get("opacity", 0.5)), float(p.get("blur_radius", 12)),
                                tuple(p.get("offset", (8, 12))), p.get("color", "#000000"))


def _op_canvas(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return geometric.fit_to_canvas(img, int(p.get("width", 1000)), int(p.get("height", 1000)),
                                   p.get("mode", "contain"), p.get("background", "#ffffff"),
                                   bool(p.get("transparent", False)), p.get("position", "center"))


def _op_adjust(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    adj = pixel_ops.PixelAdjustments(
        exposure=float(p.get("exposure", 0)),
        white_balance=p.get("white_balance"),
        wb_strength=float(p.get("wb_strength", 1.0)),
        temperature=float(p.get("temperature", 0)),
        tint=float(p.get("tint", 0)),
        brightness=float(p.get("brightness", 0)),
        contrast=float(p.get("contrast", 0)),
        levels=p.get("levels"),
        gamma=float(p.get("gamma", 1.0)),
        curves=[tuple(c) for c in p["curves"]] if p.get("curves") else None,
        curves_channel=p.get("curves_channel", "rgb"),
        saturation=float(p.get("saturation", 0)),
        vibrance=float(p.get("vibrance", 0)),
        hue=float(p.get("hue", 0)),
        color_balance=p.get("color_balance"),
        channel_mixer=p.get("channel_mixer"),
        posterize_levels=p.get("posterize_levels"),
        threshold_value=p.get("threshold_value"),
        threshold_mode=p.get("threshold_mode", "binary"),
        invert=bool(p.get("invert", False)),
        grayscale=bool(p.get("grayscale", False)),
        auto_levels=bool(p.get("auto_levels", False)),
        auto_contrast=bool(p.get("auto_contrast", False)),
    )
    return pixel_ops.apply_pixel_adjustments(img, adj)


def _op_filter(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    name = p.get("name") or p.get("filter")
    if not name:
        raise InvalidParameterError("الخطوة filter تتطلب معامل name.")
    params = {k: v for k, v in p.items() if k not in ("name", "filter", "type", "op")}
    nested = params.pop("params", None)
    if isinstance(nested, dict):
        params.update(nested)
    return filters.apply_filter(img, name, **params)


def _op_blur(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return filters.blur(img, mode=p.get("mode", "gaussian"), radius=float(p.get("radius", 3)),
                        angle=float(p.get("angle", 0)), strength=float(p.get("strength", 1)),
                        center=tuple(p.get("center", (0.5, 0.5))))


def _op_sharpen(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return filters.sharpen(img, mode=p.get("mode", "unsharp"), amount=float(p.get("amount", 1.0)),
                           radius=float(p.get("radius", 2.0)), threshold=float(p.get("threshold", 0)))


def _op_remove_bg(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    res = segmentation.remove_background(
        img,
        method=p.get("method", "auto"),
        rect=p.get("rect"),
        iterations=int(p.get("iterations", 5)),
        tolerance=float(p.get("tolerance", 40)),
        softness=float(p.get("softness", 20)),
        space=p.get("space", "lab"),
        low=int(p.get("low", 40)),
        high=int(p.get("high", 120)),
        convex=bool(p.get("convex", True)),
        k=int(p.get("k", 4)),
        keep_clusters=int(p.get("keep_clusters", 0)),
        mask_options=segmentation.MaskOptions(
            feather=float(p.get("feather", 1.5)),
            shrink=float(p.get("shrink", 0.0)),
            despeckle=int(p.get("despeckle", 120)),
            fill_holes=bool(p.get("fill_holes", True)),
            decontaminate=float(p.get("decontaminate", 0.6)),
        ),
    )
    if p.get("crop_to_content"):
        return geometric.crop_to_content(res.image, int(p.get("padding", 8)))
    return res.image


def _op_creative(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    """
    تطبيق مؤثر إبداعي. يقبل شكلين:
      {"op":"creative","name":"vintage","strength":0.8}
      {"op":"creative","name":"vintage","params":{"strength":0.8}}
    """
    name = p.get("name")
    if not name:
        raise InvalidParameterError("الخطوة creative تتطلب معامل name.")
    params = {k: v for k, v in p.items() if k not in ("name", "type", "op")}
    nested = params.pop("params", None)
    if isinstance(nested, dict):
        params.update(nested)
    return creative.apply_creative(img, name, **params)


def _op_watermark_text(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    return composite.watermark_text(
        img, str(p.get("text", "")), int(p.get("font_size", 36)), p.get("color", "#ffffff"),
        float(p.get("opacity", 0.5)), p.get("position", "bottom-right"),
        int(p.get("margin", 24)), bool(p.get("tile", False)), float(p.get("angle", 0)),
        bool(p.get("outline", True)),
    )


def _op_background(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    """تركيب الصورة على خلفية من المكتبة."""
    from . import backgrounds

    bg = backgrounds.generate_background(p.get("background", "studio_white"),
                                         size=int(p.get("size", 1200)))
    return backgrounds.compose_on_background(
        img, bg, float(p.get("scale", 0.62)), p.get("position", "center"),
        bool(p.get("shadow", True)), bool(p.get("reflection", False)),
    )


def _op_deskew(img: Image.Image, p: Dict[str, Any]) -> Image.Image:
    out, _ = geometric.deskew_auto(img)
    return out


OPERATIONS: Dict[str, Callable[[Image.Image, Dict[str, Any]], Image.Image]] = {
    "resize": _op_resize,
    "crop": _op_crop,
    "crop_aspect": _op_crop_aspect,
    "crop_auto": _op_crop_auto,
    "rotate": _op_rotate,
    "rotate90": _op_rotate90,
    "flip": _op_flip,
    "transpose": _op_transpose,
    "perspective": _op_perspective,
    "pad": _op_pad,
    "border": _op_border,
    "shadow": _op_shadow,
    "canvas": _op_canvas,
    "adjust": _op_adjust,
    "filter": _op_filter,
    "blur": _op_blur,
    "sharpen": _op_sharpen,
    "remove_bg": _op_remove_bg,
    "creative": _op_creative,
    "watermark": _op_watermark_text,
    "background": _op_background,
    "deskew": _op_deskew,
}


def operation_names() -> List[str]:
    """أسماء الخطوات المدعومة (تُعرض في التوثيق التلقائي Swagger)."""
    return sorted(OPERATIONS)


# ==============================================================================
#  التنفيذ
# ==============================================================================
@dataclass
class StepResult:
    index: int
    op: str
    ok: bool
    message: str = ""
    size: Optional[tuple] = None


@dataclass
class PipelineResult:
    image: Image.Image
    steps: List[StepResult] = field(default_factory=list)


def run_pipeline(img: Image.Image, steps: Sequence[Dict[str, Any]], *, strict: bool = True) -> PipelineResult:
    """
    تنفيذ سلسلة الخطوات بالترتيب.
    strict=True  ⇒ يتوقّف عند أول خطأ.
    strict=False ⇒ يتخطّى الخطوة الفاشلة ويسجّل السبب.
    """
    if not isinstance(steps, (list, tuple)):
        raise InvalidParameterError("steps يجب أن تكون قائمة من الخطوات.")
    if len(steps) > 40:
        raise InvalidParameterError("الحد الأقصى 40 خطوة في السلسلة الواحدة.")

    current = img
    results: List[StepResult] = []

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise InvalidParameterError(f"الخطوة رقم {i + 1} ليست كائناً صالحاً.")
        op = step.get("op") or step.get("type")
        if not op:
            raise InvalidParameterError(f"الخطوة رقم {i + 1} لا تحتوي معامل op.")
        if op not in OPERATIONS:
            raise InvalidParameterError(
                f"العملية «{op}» غير مدعومة.", detail={"supported": operation_names()}
            )
        # إزالة مفاتيح التوجيه فقط؛ أي مفتاح آخر (بما فيه params) يُمرَّر كما هو
        params = {k: v for k, v in step.items() if k not in ("op", "type")}
        before = current.size          # المقاس قبل الخطوة (يُسجَّل حتى عند الفشل)
        try:
            current = OPERATIONS[op](current, params)
            results.append(StepResult(i, op, True, "تم", current.size))
        except AppError as exc:
            results.append(StepResult(i, op, False, exc.message, before))
            if strict:
                raise
        except Exception as exc:
            results.append(StepResult(i, op, False, f"{type(exc).__name__}: {exc}", before))
            if strict:
                raise InvalidParameterError(f"فشلت الخطوة «{op}» (رقم {i + 1}).", detail=str(exc)) from exc

    return PipelineResult(image=current, steps=results)


# ==============================================================================
#  الدفعات
# ==============================================================================
@dataclass
class BatchItemResult:
    index: int
    name: str
    ok: bool
    image: Optional[Image.Image] = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    steps: List[StepResult] = field(default_factory=list)


def process_batch(
    images: Sequence[Image.Image],
    steps: Sequence[Dict[str, Any]],
    names: Optional[Sequence[str]] = None,
    strict: bool = False,
) -> List[BatchItemResult]:
    """معالجة مجموعة صور بنفس السلسلة، مع عزل أخطاء كل صورة عن الأخرى."""
    import time

    if len(images) > settings.MAX_BATCH_IMAGES:
        raise InvalidParameterError(
            f"الحد الأقصى للدفعة {settings.MAX_BATCH_IMAGES} صورة (المُرسل: {len(images)})."
        )

    names = list(names or [f"image_{i + 1}" for i in range(len(images))])
    results: List[BatchItemResult] = []

    for i, img in enumerate(images):
        started = time.perf_counter()
        try:
            pipe = run_pipeline(img, steps, strict=True)
            results.append(BatchItemResult(
                index=i, name=names[i] if i < len(names) else f"image_{i + 1}",
                ok=True, image=pipe.image,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                steps=pipe.steps,
            ))
        except Exception as exc:
            message = exc.message if isinstance(exc, AppError) else str(exc)
            results.append(BatchItemResult(
                index=i, name=names[i] if i < len(names) else f"image_{i + 1}",
                ok=False, error=message,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
            ))
            if strict:
                raise
    return results


__all__ = [
    "BatchItemResult", "OPERATIONS", "PipelineResult", "StepResult",
    "operation_names", "process_batch", "run_pipeline",
]

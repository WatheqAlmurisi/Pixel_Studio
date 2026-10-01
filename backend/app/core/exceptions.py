"""
نظام استثناءات موحّد.
=====================
كل خطأ متوقع في التطبيق يُرفع كـ AppError (أو أحد أبنائه)، ويحوّله معالج
عام في main.py إلى استجابة JSON بنفس الشكل دائماً:

    {"error": {"code": "...", "message": "...", "detail": "..."}}
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    """الخطأ الأساسي للتطبيق."""

    status_code: int = 400
    code: str = "app_error"
    message: str = "حدث خطأ غير متوقع."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        detail: Any = None,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
    ) -> None:
        self.message = message or self.message
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail is not None:
            payload["detail"] = self.detail
        return {"error": payload}


class ImageDecodeError(AppError):
    status_code = 422
    code = "image_decode_error"
    message = "تعذّر قراءة الصورة. تأكد من أن الملف صورة صالحة وغير تالفة."


class UnsupportedFormatError(AppError):
    status_code = 415
    code = "unsupported_format"
    message = "الصيغة المطلوبة غير مدعومة."


class ImageTooLargeError(AppError):
    status_code = 413
    code = "image_too_large"
    message = "الصورة أكبر من الحد المسموح به."


class InvalidParameterError(AppError):
    status_code = 400
    code = "invalid_parameter"
    message = "قيمة معامل غير صالحة."


class ModelNotAvailableError(AppError):
    status_code = 503
    code = "model_not_available"
    message = "نموذج الذكاء الاصطناعي غير متاح حالياً."


class ProcessingError(AppError):
    status_code = 500
    code = "processing_error"
    message = "فشلت معالجة الصورة."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "العنصر المطلوب غير موجود."

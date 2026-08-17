import numpy as np

from app.core.config import settings
from app.services.face_service import face_service
from app.services.image_utils import blur_score, brightness_score, image_dimensions


class DocumentService:
    """
    Validaciones de calidad y contenido sobre la imagen del documento de identidad
    (DNI, cédula, pasaporte, etc). No hace OCR/lectura de MRZ en esta versión;
    esa es una extensión natural (Tesseract / motor MRZ) para una siguiente fase.
    """

    @staticmethod
    def validate(image: np.ndarray) -> dict:
        checks = {}
        issues = []

        width, height = image_dimensions(image)
        checks["resolution"] = {"width": width, "height": height}
        if width < settings.MIN_DOCUMENT_WIDTH or height < settings.MIN_DOCUMENT_HEIGHT:
            issues.append(
                f"Resolución insuficiente (mínimo {settings.MIN_DOCUMENT_WIDTH}x{settings.MIN_DOCUMENT_HEIGHT})"
            )

        blur = blur_score(image)
        checks["blur_score"] = round(blur, 2)
        if blur < settings.BLUR_LAPLACIAN_THRESHOLD:
            issues.append("La imagen está borrosa, vuelve a capturar el documento")

        brightness = brightness_score(image)
        checks["brightness_score"] = round(brightness, 2)
        if brightness < 40:
            issues.append("La imagen está demasiado oscura")
        elif brightness > 230:
            issues.append("La imagen está sobreexpuesta / con demasiado brillo")

        has_face = face_service.detect_single_face(image)
        checks["face_detected"] = has_face
        if not has_face:
            issues.append("No se detectó un rostro claro en el documento")

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "checks": checks,
        }


document_service = DocumentService()

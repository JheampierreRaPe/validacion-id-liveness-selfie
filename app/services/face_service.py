import logging

import numpy as np
from deepface import DeepFace
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class FaceService:
    """
    Encapsula las operaciones de detección y comparación facial.
    Usa DeepFace (modelo ArcFace + detector RetinaFace por defecto, configurables).
    """

    @staticmethod
    def detect_single_face(image: np.ndarray) -> bool:
        """Retorna True si se detecta exactamente un rostro claro en la imagen."""
        try:
            faces = DeepFace.extract_faces(
                img_path=image,
                detector_backend=settings.FACE_DETECTOR_BACKEND,
                enforce_detection=True,
                align=True,
            )
            return len(faces) >= 1
        except ValueError:
            # DeepFace lanza ValueError cuando no encuentra rostro
            return False
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error detectando rostro")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error interno al procesar el rostro: {exc}",
            )

    @staticmethod
    def compare_faces(image_a: np.ndarray, image_b: np.ndarray) -> dict:
        """
        Compara dos imágenes (p.ej. foto del documento vs selfie) y retorna
        si pertenecen a la misma persona, junto con la distancia/umbral usados.
        """
        try:
            result = DeepFace.verify(
                img1_path=image_a,
                img2_path=image_b,
                model_name=settings.FACE_MODEL_NAME,
                detector_backend=settings.FACE_DETECTOR_BACKEND,
                distance_metric="cosine",
                enforce_detection=True,
                align=True,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No se pudo detectar un rostro válido en una de las imágenes: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error comparando rostros")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error interno al comparar rostros: {exc}",
            )

        distance = float(result["distance"])
        threshold = settings.FACE_MATCH_THRESHOLD
        is_match = distance <= threshold
        # Score de confianza normalizado (0-1), aproximado a partir de la distancia coseno.
        confidence = max(0.0, min(1.0, 1 - (distance / (threshold * 2))))

        return {
            "is_match": is_match,
            "distance": round(distance, 4),
            "threshold": threshold,
            "confidence": round(confidence, 4),
            "model": settings.FACE_MODEL_NAME,
        }


face_service = FaceService()

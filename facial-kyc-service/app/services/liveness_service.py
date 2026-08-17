import logging
from typing import List

import mediapipe as mp
import numpy as np
from scipy.spatial import distance as dist

from app.core.config import settings

logger = logging.getLogger(__name__)

mp_face_mesh = mp.solutions.face_mesh

# Índices de landmarks de MediaPipe FaceMesh para ojo izquierdo y derecho
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]


def _eye_aspect_ratio(landmarks, eye_indices, image_w, image_h) -> float:
    pts = np.array(
        [(landmarks[i].x * image_w, landmarks[i].y * image_h) for i in eye_indices]
    )
    # EAR clásico (Soukupová & Čech): (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    vertical_1 = dist.euclidean(pts[1], pts[5])
    vertical_2 = dist.euclidean(pts[2], pts[4])
    horizontal = dist.euclidean(pts[0], pts[3])
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


class LivenessService:
    """
    Liveness activo por detección de parpadeo sobre una secuencia de frames
    (p.ej. capturados durante ~2-3 segundos desde la cámara frontal en Flutter).
    No es un liveness pasivo anti-deepfake completo; para producción bancaria
    se recomienda combinar esto con: detección de textura/reflectos, análisis
    de profundidad si el dispositivo lo soporta, y/o un proveedor certificado
    (iBeta / ISO 30107-3) para cumplir requerimientos regulatorios.
    """

    def __init__(self) -> None:
        self._face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def analyze_blink_sequence(self, frames: List[np.ndarray]) -> dict:
        if len(frames) < settings.MIN_FRAMES_FOR_LIVENESS:
            return {
                "is_live": False,
                "reason": (
                    f"Se requieren al menos {settings.MIN_FRAMES_FOR_LIVENESS} frames, "
                    f"se recibieron {len(frames)}"
                ),
                "blinks_detected": 0,
                "frames_analyzed": len(frames),
                "ear_series": [],
            }

        ear_series = []
        frames_with_face = 0

        for frame in frames:
            h, w = frame.shape[:2]
            rgb = frame[:, :, ::-1]  # BGR -> RGB
            result = self._face_mesh.process(rgb)
            if not result.multi_face_landmarks:
                ear_series.append(None)
                continue

            frames_with_face += 1
            landmarks = result.multi_face_landmarks[0].landmark
            left_ear = _eye_aspect_ratio(landmarks, LEFT_EYE, w, h)
            right_ear = _eye_aspect_ratio(landmarks, RIGHT_EYE, w, h)
            ear_series.append(round((left_ear + right_ear) / 2.0, 4))

        if frames_with_face < settings.MIN_FRAMES_FOR_LIVENESS // 2:
            return {
                "is_live": False,
                "reason": "No se detectó un rostro consistente a lo largo de la secuencia",
                "blinks_detected": 0,
                "frames_analyzed": len(frames),
                "ear_series": ear_series,
            }

        blinks = self._count_blinks(ear_series)

        return {
            "is_live": blinks >= 1,
            "reason": "Parpadeo detectado" if blinks >= 1 else "No se detectó parpadeo",
            "blinks_detected": blinks,
            "frames_analyzed": len(frames),
            "ear_series": ear_series,
        }

    @staticmethod
    def _count_blinks(ear_series: List[float]) -> int:
        blinks = 0
        consec = 0
        for ear in ear_series:
            if ear is not None and ear < settings.EAR_BLINK_THRESHOLD:
                consec += 1
            else:
                if consec >= settings.EAR_CONSEC_FRAMES:
                    blinks += 1
                consec = 0
        if consec >= settings.EAR_CONSEC_FRAMES:
            blinks += 1
        return blinks


liveness_service = LivenessService()

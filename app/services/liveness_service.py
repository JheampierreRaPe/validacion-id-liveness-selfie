import logging
from typing import List, Optional, Tuple

import mediapipe as mp
import numpy as np
from scipy.spatial import distance as dist

from app.core.config import settings
from app.services.image_utils import blur_score

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
        result, _best_frame, _first_frame = self._process_sequence(frames)
        return result

    def _process_sequence(
        self, frames: List[np.ndarray]
    ) -> Tuple[dict, Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Procesa la secuencia una sola vez: calcula EAR por frame (para el parpadeo)
        y, de paso, rastrea el mejor frame (rostro más grande y nítido) y el primer
        frame con rostro detectado, para poder usarlos como selfie / chequeo de
        consistencia sin volver a recorrer todos los frames.
        """
        if len(frames) < settings.MIN_FRAMES_FOR_LIVENESS:
            result = {
                "is_live": False,
                "reason": (
                    f"Se requieren al menos {settings.MIN_FRAMES_FOR_LIVENESS} frames, "
                    f"se recibieron {len(frames)}"
                ),
                "blinks_detected": 0,
                "frames_analyzed": len(frames),
                "ear_series": [],
            }
            return result, None, None

        ear_series = []
        frames_with_face = 0
        best_frame = None
        best_score = -1.0
        first_frame_with_face = None

        for frame in frames:
            h, w = frame.shape[:2]
            rgb = frame[:, :, ::-1]  # BGR -> RGB
            mesh_result = self._face_mesh.process(rgb)
            if not mesh_result.multi_face_landmarks:
                ear_series.append(None)
                continue

            frames_with_face += 1
            landmarks = mesh_result.multi_face_landmarks[0].landmark
            left_ear = _eye_aspect_ratio(landmarks, LEFT_EYE, w, h)
            right_ear = _eye_aspect_ratio(landmarks, RIGHT_EYE, w, h)
            ear_series.append(round((left_ear + right_ear) / 2.0, 4))

            if first_frame_with_face is None:
                first_frame_with_face = frame

            # Puntaje de calidad: tamaño relativo del rostro (frontalidad/cercanía) * nitidez
            xs = [lm.x for lm in landmarks]
            ys = [lm.y for lm in landmarks]
            face_area_ratio = (max(xs) - min(xs)) * (max(ys) - min(ys))
            quality = face_area_ratio * blur_score(frame)
            if quality > best_score:
                best_score = quality
                best_frame = frame

        if frames_with_face < settings.MIN_FRAMES_FOR_LIVENESS // 2:
            result = {
                "is_live": False,
                "reason": "No se detectó un rostro consistente a lo largo de la secuencia",
                "blinks_detected": 0,
                "frames_analyzed": len(frames),
                "ear_series": ear_series,
            }
            return result, best_frame, first_frame_with_face

        blinks = self._count_blinks(ear_series)

        result = {
            "is_live": blinks >= 1,
            "reason": "Parpadeo detectado" if blinks >= 1 else "No se detectó parpadeo",
            "blinks_detected": blinks,
            "frames_analyzed": len(frames),
            "ear_series": ear_series,
        }
        return result, best_frame, first_frame_with_face

    def analyze_and_extract_selfie(self, frames: List[np.ndarray]) -> dict:
        """
        Procesa la secuencia de liveness y, además del resultado de parpadeo,
        extrae el mejor frame para usarlo como selfie en el match biométrico,
        y valida que la persona sea la misma a lo largo de la secuencia
        (evita ataques donde la cara cambia a mitad del video/ráfaga).
        """
        from app.services.face_service import face_service  # import diferido: evita ciclo de import pesado

        liveness_result, best_frame, first_frame = self._process_sequence(frames)

        consistency = {"checked": False, "is_consistent": True, "distance": None}

        if best_frame is not None and first_frame is not None:
            try:
                same_person_frames = best_frame is first_frame
                if not same_person_frames:
                    match = face_service.compare_faces(first_frame, best_frame)
                    consistency = {
                        "checked": True,
                        "is_consistent": match["is_match"],
                        "distance": match["distance"],
                    }
            except Exception as exc:  # noqa: BLE001
                logger.warning("No se pudo verificar consistencia de identidad en la secuencia: %s", exc)
                consistency = {"checked": False, "is_consistent": True, "distance": None}

        return {
            "liveness": liveness_result,
            "best_frame": best_frame,
            "identity_consistency": consistency,
        }

    # ------------------------------------------------------------------
    # Liveness guiado por pasos (challenge-response con head pose)
    # ------------------------------------------------------------------
    def evaluate_segment(self, step: str, frames: List[np.ndarray]) -> dict:
        """
        Evalúa UN segmento de frames correspondiente a UNA task del desafío.
        - 'parpadeo'  -> conteo de blinks (EAR) sobre el segmento.
        - mover cabeza (arriba/abajo/izquierda/derecha) -> estima head pose
          (yaw/pitch) y verifica la desviación en la dirección pedida.
        Esta evaluación es "liviana" (solo MediaPipe, sin DeepFace) para poder
        dar feedback por task en < 1s. La validación final (DeepFace) ocurre
        en identity/verify-full.
        """
        result: dict = {"passed": False, "reason": "Paso desconocido", "details": {}}

        if len(frames) < settings.MIN_FRAMES_PER_SEGMENT:
            result["reason"] = (
                f"Se requieren al menos {settings.MIN_FRAMES_PER_SEGMENT} frames "
                f"por segmento, se recibieron {len(frames)}"
            )
            return result

        if step == "parpadeo":
            blinks, ear_series = self._blinks_for_segment(frames)
            result["details"] = {
                "blinks_detected": blinks,
                "frames_analyzed": len(frames),
                "ear_series": ear_series,
            }
            result["passed"] = blinks >= 1
            result["reason"] = (
                "Parpadeo detectado" if blinks >= 1 else "No se detectó parpadeo"
            )
            return result

        if step not in ("arriba", "abajo", "izquierda", "derecha"):
            result["reason"] = f"Paso no soportado: {step}"
            return result

        axis_delta = self._head_pose_delta(frames)
        if axis_delta is None:
            result["reason"] = "No se pudo estimar la pose de la cabeza (rostro no consistente)"
            return result

        result["details"] = {
            "pitch_delta": round(axis_delta[0], 6),
            "yaw_delta": round(axis_delta[1], 6),
            "frames_analyzed": len(frames),
        }

        # Eje y signo esperado de la desviación según el paso.
        # "arriba"       -> pitch positivo (la nariz sube => pitch = (mid_y - y_n)/face_h crece)
        # "abajo"        -> pitch negativo
        # "izquierda"    -> yaw positivo (la nariz se aleja del centro horizontal)
        # "derecha"      -> yaw negativo
        expected_sign = {
            "arriba": (0, 1.0),
            "abajo": (0, -1.0),
            "izquierda": (1, 1.0),
            "derecha": (1, -1.0),
        }[step]
        limit = settings.HEAD_POSE_MOVE_THRESHOLD
        observed = axis_delta[expected_sign[0]]
        confirmed = observed * expected_sign[1] > limit

        result["passed"] = confirmed
        result["reason"] = (
            "Movimiento detectado" if confirmed else "Movimiento no detectado correctamente"
        )
        return result

    def analyze_guided_sequence(
        self, steps_frames: dict, required_steps: List[str]
    ) -> dict:
        """
        Versión para el flujo guiado en /identity/verify-full. Recibe los segmentos
        finales por paso (ya validados uno a uno en /liveness/evaluate) y:
        - arma el resumen de liveness por pasos,
        - extrae el mejor frame global como selfie biométrica,
        - valida consistencia de identidad entre el primer rostro y el mejor frame.
        """
        from app.services.face_service import face_service  # import diferido

        all_frames = [
            frame
            for step in required_steps
            for frame in steps_frames.get(step, [])
        ]
        liveness_result, best_frame, first_frame = self._process_sequence(all_frames)

        step_results = {}
        for step in required_steps:
            frames = steps_frames.get(step, [])
            res = self.evaluate_segment(step, frames)
            step_results[step] = {
                "passed": res["passed"],
                "reason": res["reason"],
                "details": res["details"],
            }

        passed_steps = [s for s in required_steps if step_results[s]["passed"]]
        all_passed = len(passed_steps) == len(required_steps)

        liveness_result["steps_total"] = list(required_steps)
        liveness_result["steps_verified"] = passed_steps
        liveness_result["step_results"] = step_results
        liveness_result["is_live"] = all_passed
        liveness_result["reason"] = (
            "Todos los pasos del desafío fueron validados"
            if all_passed
            else "Falló: " + ", ".join(s for s in required_steps if not step_results[s]["passed"])
        )

        consistency = {"checked": False, "is_consistent": True, "distance": None}
        if best_frame is not None and first_frame is not None:
            try:
                same_person_frames = best_frame is first_frame
                if not same_person_frames:
                    match = face_service.compare_faces(first_frame, best_frame)
                    consistency = {
                        "checked": True,
                        "is_consistent": match["is_match"],
                        "distance": match["distance"],
                    }
            except Exception as exc:  # noqa: BLE001
                logger.warning("No se pudo verificar consistencia de identidad: %s", exc)
                consistency = {"checked": False, "is_consistent": True, "distance": None}

        return {
            "liveness": liveness_result,
            "best_frame": best_frame,
            "identity_consistency": consistency,
        }

    def _blinks_for_segment(self, frames: List[np.ndarray]):
        """EAR y conteo de parpadeos para un segmento de la cámara."""
        ear_series: List[Optional[float]] = []
        for frame in frames:
            h, w = frame.shape[:2]
            mesh_result = self._face_mesh.process(frame[:, :, ::-1])
            if not mesh_result.multi_face_landmarks:
                ear_series.append(None)
                continue
            landmarks = mesh_result.multi_face_landmarks[0].landmark
            left_ear = _eye_aspect_ratio(landmarks, LEFT_EYE, w, h)
            right_ear = _eye_aspect_ratio(landmarks, RIGHT_EYE, w, h)
            ear_series.append(round((left_ear + right_ear) / 2.0, 4))
        return self._count_blinks(ear_series), ear_series

    def _head_pose_delta(self, frames: List[np.ndarray]) -> Optional[Tuple[float, float]]:
        """
        Estima la desviación de head pose (pitch, yaw normalizados) del final del
        segmento respecto a su inicio. Retorna None si el rostro no es estable.
        Los primeros frames actúan como línea base (pose neutra).
        """
        baseline_frames = min(settings.HEAD_POSE_BASELINE_FRAMES, len(frames))
        base_pitch, base_yaw = 0.0, 0.0
        base_count = 0
        for frame in frames[:baseline_frames]:
            pose = self._estimate_head_pose(frame)
            if pose is None:
                continue
            base_pitch += pose[0]
            base_yaw += pose[1]
            base_count += 1
        if base_count == 0:
            return None

        base_pitch /= base_count
        base_yaw /= base_count

        recent_frames = frames[-max(1, len(frames) - baseline_frames):]
        end_pitch, end_yaw = 0.0, 0.0
        end_count = 0
        for frame in recent_frames:
            pose = self._estimate_head_pose(frame)
            if pose is None:
                continue
            end_pitch += pose[0]
            end_yaw += pose[1]
            end_count += 1
        if end_count == 0:
            return None

        end_pitch /= end_count
        end_yaw /= end_count
        return (end_pitch - base_pitch, end_yaw - base_yaw)

    @staticmethod
    def _estimate_head_pose(frame: np.ndarray) -> Optional[Tuple[float, float]]:
        """
        Heurística de head pose usando landmarks 2D de FaceMesh (sin solvePnP):
        - pitch: relación vertical nariz (landmark 1) vs. borde de rostro.
        - yaw:   relación horizontal nariz (landmark 1) vs. mentón/barbilla centroid.
        Valores normalizados: >0 hacia arriba/derecha, <0 hacia abajo/izquierda.
        Suficiente para el gate por task del liveness.
        """
        mesh = LivenessService._instance_face_mesh()
        h, w = frame.shape[:2]
        mesh_result = mesh.process(frame[:, :, ::-1])
        if not mesh_result.multi_face_landmarks:
            return None
        landmarks = mesh_result.multi_face_landmarks[0].landmark

        # Referencias típicas de FaceMesh
        nose = landmarks[1]
        x_n, y_n = nose.x, nose.y

        # Mentón (152), frente (10) y mejillas: miden extensión vertical/horizontal.
        chin = landmarks[152]
        forehead = landmarks[10]
        left_cheek = landmarks[234]
        right_cheek = landmarks[454]

        face_h = forehead.y - chin.y
        face_w = right_cheek.x - left_cheek.x
        if abs(face_h) < 1e-6 or abs(face_w) < 1e-6:
            return None

        # pitch: nariz desplazada hacia arriba (+) o abajo (-) del centro vertical.
        mid_y = (forehead.y + chin.y) / 2.0
        pitch = (mid_y - y_n) / face_h

        # yaw: nariz desplazada a la izquierda (+) o derecha (-) del centro horizontal.
        mid_x = (left_cheek.x + right_cheek.x) / 2.0
        yaw = (x_n - mid_x) / face_w

        return pitch, yaw

    @staticmethod
    def _instance_face_mesh():
        """Reutiliza la instancia de FaceMesh del servicio (evita crear otra)."""
        self = liveness_service
        return self._face_mesh

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

import logging
import random
import secrets
import threading
import time
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Pasos activos permitidos (los que el detecto puede confirmar).
VALID_STEPS = ("arriba", "abajo", "izquierda", "derecha", "parpadeo")


class ChallengeStore:
    """
    Tienda en memoria de desafíos de liveness (con TTL y bloqueo por hilo).

    Guarda el orden aleatorio de pasos y el progreso validado por task.
    El back-end define la secuencia, por lo que un atacante no conoce el
    orden antes de capturar frames (protección anti-replay / anti-grabación).

    Stateless respecto a base de datos: solo estado en RAM del proceso.
    En un despliegue multi-instancia llevarlo a Redis/servicio externo.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # token -> {"steps": [...], "done_idx": int, "expires": float}
        self._challenges: dict = {}

    def _available_steps(self) -> List[str]:
        return [s for s in VALID_STEPS if s in settings.LIVENESS_CHALLENGE_STEPS.split(",")]

    def create(self) -> dict:
        """Crea un nuevo desafío con un orden aleatorio de pasos."""
        pool = self._available_steps()
        if not pool:
            pool = list(VALID_STEPS)
        steps = random.sample(
            pool, min(settings.CHALLENGE_MAX_STEPS, len(pool))
        )
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._prune()
            self._challenges[token] = {
                "steps": steps,
                "done_idx": 0,
                "expires": time.time() + settings.CHALLENGE_TOKEN_TTL_SECONDS,
            }
        logger.info("Desafío creado: token=%s steps=%s", token, steps)
        return {"token": token, "steps": steps}

    def _get(self, token: str) -> Optional[dict]:
        entry = self._challenges.get(token)
        if not entry:
            return None
        if time.time() > entry["expires"]:
            del self._challenges[token]
            return None
        return entry

    def get(self, token: str) -> Optional[dict]:
        with self._lock:
            return self._get(token)

    def current_step(self, token: str) -> Optional[str]:
        """Devuelve el paso pendiente (progreso) del desafío, o None si ya terminó."""
        with self._lock:
            entry = self._get(token)
            if not entry:
                return None
            if entry["done_idx"] >= len(entry["steps"]):
                return None
            return entry["steps"][entry["done_idx"]]

    def advance_if_matches(self, token: str, step: str) -> bool:
        """
        Avanza el desafío a la siguiente task solo si 'step' es el pendiente
        y la validación del segmento fue aprobada por el servidor.
        """
        with self._lock:
            entry = self._get(token)
            if not entry:
                return False
            if entry["done_idx"] >= len(entry["steps"]):
                return False
            if entry["steps"][entry["done_idx"]] != step:
                return False
            entry["done_idx"] += 1
            logger.info(
                "Task '%s' validada (%d/%d) para token=%s",
                step,
                entry["done_idx"],
                len(entry["steps"]),
                token,
            )
            return True

    def is_completed(self, token: str) -> bool:
        with self._lock:
            entry = self._get(token)
            return bool(entry) and entry["done_idx"] >= len(entry["steps"])

    def steps_for(self, token: str) -> List[str]:
        with self._lock:
            entry = self._get(token)
            return list(entry["steps"]) if entry else []

    def delete(self, token: str) -> None:
        with self._lock:
            self._challenges.pop(token, None)

    def _prune(self) -> None:
        now = time.time()
        expired = [t for t, e in self._challenges.items() if now > e["expires"]]
        for t in expired:
            del self._challenges[t]


challenge_store = ChallengeStore()
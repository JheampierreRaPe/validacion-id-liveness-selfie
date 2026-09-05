from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.challenges import challenge_store
from app.core.security import verify_api_key
from app.schemas.models import (
    ChallengeResponse,
    EvaluateRequest,
    EvaluateResponse,
    LivenessRequest,
    LivenessResponse,
)
from app.services.image_utils import decode_base64_image
from app.services.liveness_service import liveness_service

router = APIRouter(prefix="/api/v1/liveness", tags=["Liveness"])


@router.post(
    "/verify",
    response_model=LivenessResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Verifica liveness activo mediante detección de parpadeo sobre una secuencia de frames",
)
async def verify_liveness(payload: LivenessRequest):
    frames = [decode_base64_image(f) for f in payload.frames_base64]
    result = liveness_service.analyze_blink_sequence(frames)
    return LivenessResponse(**result)


@router.post(
    "/challenge",
    response_model=ChallengeResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Crea un desafío de liveness: secuencia aleatoria de tareas + token (kernel anti-replay)",
)
async def new_challenge():
    candidate = challenge_store.create()
    return ChallengeResponse(
        token=candidate["token"],
        steps=candidate["steps"],
        expires_in=settings.CHALLENGE_TOKEN_TTL_SECONDS,
    )


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    dependencies=[Depends(verify_api_key)],
    summary=(
        "Evalúa UNA tarea del desafío (solo MediaPipe, sin DeepFace). "
        "Permite desbloquear la siguiente tarea únicamente cuando la anterior "
        "fue validada por el servidor."
    ),
)
async def evaluate_step(payload: EvaluateRequest):
    challenge = challenge_store.get(payload.token)
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de desafío inválido o expirado. Solicita uno nuevo en /liveness/challenge",
        )

    pending_step = challenge_store.current_step(payload.token)
    if pending_step is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El desafío ya fue completado. Inicia uno nuevo o ejecuta /identity/verify-full",
        )
    if pending_step != payload.step:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Se esperaba la tarea '{pending_step}' y se recibió '{payload.step}'. "
                "Las tareas deben completarse en el orden del desafío."
            ),
        )

    frames = [decode_base64_image(f) for f in payload.frames_base64]
    result = liveness_service.evaluate_segment(payload.step, frames)

    if result["passed"]:
        challenge_store.advance_if_matches(payload.token, payload.step)

    return EvaluateResponse(
        step=payload.step,
        passed=result["passed"],
        reason=result["reason"],
        frames_analyzed=result["details"].get("frames_analyzed", len(frames)),
        details=result["details"],
    )

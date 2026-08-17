from fastapi import APIRouter, Depends

from app.core.security import verify_api_key
from app.schemas.models import LivenessRequest, LivenessResponse
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

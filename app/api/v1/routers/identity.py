import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.challenges import challenge_store
from app.core.security import verify_api_key
from app.schemas.models import FullVerificationResponse, IdentityVerifyResponse
from app.services.document_service import document_service
from app.services.face_service import face_service
from app.services.image_utils import decode_base64_image, decode_upload_bytes
from app.services.liveness_service import liveness_service

router = APIRouter(prefix="/api/v1/identity", tags=["Identidad"])


@router.post(
    "/verify",
    response_model=IdentityVerifyResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Compara el rostro del documento contra una selfie",
)
async def verify_identity(
    document_image: UploadFile = File(..., description="Foto del documento de identidad"),
    selfie_image: UploadFile = File(..., description="Selfie del usuario"),
):
    doc_img = decode_upload_bytes(await document_image.read())
    selfie_img = decode_upload_bytes(await selfie_image.read())
    result = face_service.compare_faces(doc_img, selfie_img)
    return IdentityVerifyResponse(**result)


@router.post(
    "/verify-full",
    response_model=FullVerificationResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Flujo completo de onboarding KYC: documento + liveness (con selfie extraída del propio liveness)",
)
async def verify_full(
    document_image: UploadFile = File(..., description="Foto del documento de identidad"),
    liveness_frames: str = Form(
        ...,
        description=(
            'JSON con los frames de liveness. Dos formatos soportados:\n'
            '- Clásico (parpadeo): array de strings base64, ej: ["<b64>", ...].\n'
            '- Guiado (challenge-response): objeto {"token": "<token>", "segments": {"arriba": [...b64], ...}} '
            "con las tareas validadas de a una vía /liveness/evaluate. La selfie del match biométrico se "
            "extrae del mejor frame de toda la secuencia, garantizando que quien hizo el liveness es quien "
            "se compara contra el documento."
        ),
    ),
):
    doc_img = decode_upload_bytes(await document_image.read())

    doc_validation = document_service.validate(doc_img)

    try:
        parsed = json.loads(liveness_frames)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="liveness_frames debe ser un JSON válido (array de base64 o {token, segments})",
        )

    # -------- Retrocompatibilidad: flujo clásico (solo parpadeo) --------
    if isinstance(parsed, list):
        frames = [decode_base64_image(f) for f in parsed]
        liveness_bundle = liveness_service.analyze_and_extract_selfie(frames)

    # -------- Flujo guiado por pasos (challenge-response) --------
    elif isinstance(parsed, dict):
        token = parsed.get("token")
        segments_raw = parsed.get("segments")
        if challenge_store.get(token) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de desafío inválido o expirado. Reinicia el liveness desde /liveness/challenge",
            )
        if not challenge_store.is_completed(token):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "El desafío aún no está completo: cada tarea debe validarse con /liveness/evaluate "
                    "antes de enviar /identity/verify-full"
                ),
            )
        if not isinstance(segments_raw, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El campo 'segments' debe ser un objeto {paso: [frames base64]}",
            )

        steps = challenge_store.steps_for(token)
        missing = [
            s
            for s in steps
            if s not in segments_raw
            or not isinstance(segments_raw[s], list)
            or len(segments_raw[s]) == 0
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Faltan segmentos de frames para: {', '.join(missing)}",
            )

        segments = {
            s: [decode_base64_image(b64) for b64 in segments_raw[s]] for s in steps
        }
        liveness_bundle = liveness_service.analyze_guided_sequence(segments, steps)
        challenge_store.delete(token)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="liveness_frames debe ser un array JSON o un objeto {token, segments}",
        )

    liveness_result = liveness_bundle["liveness"]
    best_frame = liveness_bundle["best_frame"]
    consistency = liveness_bundle["identity_consistency"]

    if best_frame is not None:
        match_result = face_service.compare_faces(doc_img, best_frame)
    else:
        match_result = {
            "is_match": False,
            "distance": 1.0,
            "threshold": 0,
            "confidence": 0.0,
            "model": "n/a",
        }

    overall = (
        doc_validation["is_valid"]
        and liveness_result["is_live"]
        and consistency["is_consistent"]
        and match_result["is_match"]
    )

    if overall:
        reason = "Verificación de identidad exitosa"
    else:
        reasons = []
        if not doc_validation["is_valid"]:
            reasons.append("documento inválido")
        if not liveness_result["is_live"]:
            reasons.append("liveness no superado")
        if not consistency["is_consistent"]:
            reasons.append("identidad inconsistente durante la secuencia de liveness")
        if not match_result["is_match"]:
            reasons.append("el rostro no coincide con el documento")
        reason = "Falló: " + ", ".join(reasons)

    return FullVerificationResponse(
        document_validation=doc_validation,
        liveness=liveness_result,
        identity_consistency=consistency,
        face_match=match_result,
        overall_result=overall,
        overall_reason=reason,
    )
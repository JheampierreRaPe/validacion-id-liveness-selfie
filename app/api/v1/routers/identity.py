import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

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
            'JSON array de strings base64 con los frames de liveness, ej: ["<b64>", "<b64>", ...]. '
            "La selfie para el match biométrico se extrae automáticamente del mejor frame de esta secuencia: "
            "no se recibe una selfie por separado, para garantizar que la persona que hace el liveness "
            "es la misma que se compara contra el documento."
        ),
    ),
):
    doc_img = decode_upload_bytes(await document_image.read())

    doc_validation = document_service.validate(doc_img)

    try:
        frames_b64 = json.loads(liveness_frames)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="liveness_frames debe ser un array JSON válido de strings base64",
        )
    frames = [decode_base64_image(f) for f in frames_b64]

    liveness_bundle = liveness_service.analyze_and_extract_selfie(frames)
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
import json

from fastapi import APIRouter, Depends, File, Form, UploadFile

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
    summary="Flujo completo de onboarding KYC: documento + liveness + match biométrico",
)
async def verify_full(
    document_image: UploadFile = File(..., description="Foto del documento de identidad"),
    selfie_image: UploadFile = File(..., description="Foto principal de la selfie, usada para el match"),
    liveness_frames: str = Form(
        ..., description='JSON array de strings base64 con los frames de liveness, ej: ["<b64>", "<b64>", ...]'
    ),
):
    doc_img = decode_upload_bytes(await document_image.read())
    selfie_img = decode_upload_bytes(await selfie_image.read())

    doc_validation = document_service.validate(doc_img)

    frames_b64 = json.loads(liveness_frames)
    frames = [decode_base64_image(f) for f in frames_b64]
    liveness_result = liveness_service.analyze_blink_sequence(frames)

    match_result = face_service.compare_faces(doc_img, selfie_img)

    overall = doc_validation["is_valid"] and liveness_result["is_live"] and match_result["is_match"]
    if overall:
        reason = "Verificación de identidad exitosa"
    else:
        reasons = []
        if not doc_validation["is_valid"]:
            reasons.append("documento inválido")
        if not liveness_result["is_live"]:
            reasons.append("liveness no superado")
        if not match_result["is_match"]:
            reasons.append("el rostro no coincide con el documento")
        reason = "Falló: " + ", ".join(reasons)

    return FullVerificationResponse(
        document_validation=doc_validation,
        liveness=liveness_result,
        face_match=match_result,
        overall_result=overall,
        overall_reason=reason,
    )

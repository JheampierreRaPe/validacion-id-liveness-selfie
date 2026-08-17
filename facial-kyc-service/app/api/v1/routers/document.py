from fastapi import APIRouter, Depends, File, UploadFile

from app.core.security import verify_api_key
from app.schemas.models import DocumentValidationResponse
from app.services.document_service import document_service
from app.services.image_utils import decode_upload_bytes

router = APIRouter(prefix="/api/v1/document", tags=["Documento de Identidad"])


@router.post(
    "/validate",
    response_model=DocumentValidationResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Valida calidad y presencia de rostro en el documento de identidad",
)
async def validate_document(file: UploadFile = File(...)):
    raw = await file.read()
    image = decode_upload_bytes(raw)
    result = document_service.validate(image)
    return DocumentValidationResponse(**result)

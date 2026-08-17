from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------- Documento ----------------------
class DocumentValidationResponse(BaseModel):
    is_valid: bool
    issues: List[str]
    checks: dict


# ---------------------- Liveness ----------------------
class LivenessRequest(BaseModel):
    frames_base64: List[str] = Field(
        ..., description="Secuencia de frames (base64) capturados desde la cámara, en orden temporal"
    )


class LivenessResponse(BaseModel):
    is_live: bool
    reason: str
    blinks_detected: int
    frames_analyzed: int
    ear_series: List[Optional[float]]


# ---------------------- Identidad (match biométrico) ----------------------
class IdentityVerifyResponse(BaseModel):
    is_match: bool
    distance: float
    threshold: float
    confidence: float
    model: str


# ---------------------- Flujo combinado (recomendado para banca) ----------------------
class FullVerificationResponse(BaseModel):
    document_validation: DocumentValidationResponse
    liveness: LivenessResponse
    face_match: IdentityVerifyResponse
    overall_result: bool
    overall_reason: str

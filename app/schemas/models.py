from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------- Documento ----------------------
class DocumentValidationResponse(BaseModel):
    is_valid: bool
    issues: List[str]
    checks: dict


class DocumentOCRResponse(BaseModel):
    raw_text: str
    avg_confidence: float
    low_confidence: bool
    parsed_fields: dict


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
    # Flujo guiado por pasos (opcional; None en el flujo clásico de solo parpadeo)
    steps_verified: Optional[List[str]] = None
    steps_total: Optional[List[str]] = None
    step_results: Optional[dict] = None


# ---------------------- Liveness guiado (challenge-response) ----------------------
class ChallengeResponse(BaseModel):
    token: str
    steps: List[str] = Field(
        ..., description="Orden aleatorio de tareas que el usuario debe realizar"
    )
    expires_in: int = Field(..., description="Validez del token en segundos")


class EvaluateRequest(BaseModel):
    token: str = Field(..., description="Token del desafío obtenido en /liveness/challenge")
    step: str = Field(
        ..., description="Paso que el usuario acaba de realizar (arriba/abajo/izquierda/derecha/parpadeo)"
    )
    frames_base64: List[str] = Field(
        ..., description="Segmento de frames (base64) capturados durante la ejecución de la task"
    )


class EvaluateResponse(BaseModel):
    step: str
    passed: bool
    reason: str
    frames_analyzed: int
    details: Optional[dict] = None


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
    identity_consistency: dict
    face_match: IdentityVerifyResponse
    overall_result: bool
    overall_reason: str

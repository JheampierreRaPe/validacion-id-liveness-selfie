from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "KYC Facial Recognition Microservice"
    API_KEY: str = "changeme-super-secret-key"  # sobreescribir en .env / docker-compose

    # ---- Umbrales de negocio (ajustables según tolerancia al riesgo) ----
    # Distancia/similaridad de comparación facial. DeepFace + ArcFace: menor score = más parecido.
    FACE_MATCH_THRESHOLD: float = 0.68
    FACE_MODEL_NAME: str = "ArcFace"          # modelo de embeddings faciales
    FACE_DETECTOR_BACKEND: str = "retinaface"  # detector de rostro

    # Liveness (parpadeo) - Eye Aspect Ratio
    EAR_BLINK_THRESHOLD: float = 0.21
    EAR_CONSEC_FRAMES: int = 2
    MIN_FRAMES_FOR_LIVENESS: int = 8

    # Liveness guiado por pasos (challenge-response con head pose)
    # Pool de movimientos disponibles. El backend genera el orden aleatorio del desafío.
    LIVENESS_CHALLENGE_STEPS: str = "arriba,abajo,izquierda,derecha,parpadeo"
    CHALLENGE_MAX_STEPS: int = 5           # pasos máximos por desafío
    CHALLENGE_TOKEN_TTL_SECONDS: int = 180 # validez del token del desafío
    MIN_FRAMES_PER_SEGMENT: int = 5        # frames mínimos por segmento (task)
    HEAD_POSE_BASELINE_FRAMES: int = 3     # frames iniciales usados como línea base de pose
    HEAD_POSE_MOVE_THRESHOLD: float = 0.06 # desviación normalizada mínima para confirmar el movimiento

    # Calidad de imagen de documento
    MIN_DOCUMENT_WIDTH: int = 600
    MIN_DOCUMENT_HEIGHT: int = 400
    BLUR_LAPLACIAN_THRESHOLD: float = 0.55



    # Selección de mejor frame (selfie extraída del liveness) y consistencia de identidad
    IDENTITY_CONSISTENCY_THRESHOLD: float = 0.68  # misma escala que FACE_MATCH_THRESHOLD

    class Config:
        env_file = ".env"


settings = Settings()

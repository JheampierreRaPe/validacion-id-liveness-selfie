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

    # Calidad de imagen de documento
    MIN_DOCUMENT_WIDTH: int = 600
    MIN_DOCUMENT_HEIGHT: int = 400
    BLUR_LAPLACIAN_THRESHOLD: float = 80.0

    class Config:
        env_file = ".env"


settings = Settings()

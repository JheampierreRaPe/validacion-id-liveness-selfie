FROM python:3.10-slim

# Dependencias de sistema requeridas por OpenCV, MediaPipe y TensorFlow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# Directorio donde DeepFace descarga los pesos de los modelos (se cachea en el volumen)
ENV DEEPFACE_HOME=/app/.deepface
RUN mkdir -p /app/.deepface

# Descarga/"calienta" los pesos de los modelos en tiempo de build para que el
# primer request en producción no tenga latencia de descarga.
# Requiere acceso a internet durante el build; si falla, el script avisa
# pero NO tumba el build (los pesos se descargan en el primer request real).
RUN python scripts/warmup_models.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

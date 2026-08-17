# KYC Facial Recognition Microservice

Microservicio de **verificación de identidad** (onboarding KYC) con:

1. **Validación de documento** — calidad de imagen y presencia de rostro en el DNI/cédula.
2. **Liveness activo** — detección de parpadeo (Eye Aspect Ratio) sobre una secuencia de frames, para evitar ataques con foto/video estático.
3. **Verificación de identidad** — comparación biométrica entre el rostro del documento y una selfie.
4. **Flujo completo** (`/verify-full`) que combina los tres pasos en una sola llamada.

Pensado como servicio independiente que luego consumirá tu app **Flutter** durante el registro de cuenta bancaria.

## Stack

- **FastAPI** (Python) — API REST + documentación automática (Swagger).
- **DeepFace + ArcFace + RetinaFace** — embeddings y comparación facial.
- **MediaPipe FaceMesh** — landmarks faciales para liveness (parpadeo).
- **OpenCV** — procesamiento y métricas de calidad de imagen.
- **Docker / docker-compose** — despliegue portable en cualquier dispositivo/servidor.

## Estructura del proyecto

```
facial-kyc-service/
├── app/
│   ├── main.py                     # App FastAPI, CORS, health check
│   ├── core/
│   │   ├── config.py                # Configuración y umbrales (env vars)
│   │   └── security.py              # Autenticación por API Key
│   ├── services/
│   │   ├── image_utils.py           # Decodificación y métricas de calidad de imagen
│   │   ├── document_service.py      # Validación del documento
│   │   ├── face_service.py          # Comparación biométrica (DeepFace)
│   │   └── liveness_service.py      # Liveness por parpadeo (MediaPipe)
│   ├── schemas/models.py            # Contratos Pydantic de la API
│   └── api/v1/routers/
│       ├── document.py
│       ├── liveness.py
│       └── identity.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Cómo correrlo

```bash
cp .env.example .env
# editar .env y poner una API_KEY real

docker compose up --build
```

El servicio queda disponible en `http://localhost:8000`.
Documentación interactiva (Swagger): `http://localhost:8000/docs`

> **Nota:** el build de la imagen descarga los pesos del modelo ArcFace (requiere internet la primera vez). Se cachean en el volumen `deepface_models`, así que no se vuelven a descargar en reinicios.

## Endpoints

Todos (excepto `/health`) requieren el header `X-API-Key`.

### 1. `POST /api/v1/document/validate`
`multipart/form-data`, campo `file` (imagen del documento).

Respuesta:
```json
{
  "is_valid": true,
  "issues": [],
  "checks": {
    "resolution": {"width": 1280, "height": 800},
    "blur_score": 145.32,
    "brightness_score": 128.5,
    "face_detected": true
  }
}
```

### 2. `POST /api/v1/liveness/verify`
`application/json`:
```json
{ "frames_base64": ["<b64_frame_1>", "<b64_frame_2>", "..."] }
```
Se recomienda capturar ~10-20 frames en ~2-3 segundos desde la cámara frontal, pidiendo al usuario que parpadee de forma natural.

Respuesta:
```json
{
  "is_live": true,
  "reason": "Parpadeo detectado",
  "blinks_detected": 1,
  "frames_analyzed": 15,
  "ear_series": [0.31, 0.29, 0.18, 0.15, 0.30, "..."]
}
```

### 3. `POST /api/v1/identity/verify`
`multipart/form-data`, campos `document_image` y `selfie_image`.

Respuesta:
```json
{
  "is_match": true,
  "distance": 0.42,
  "threshold": 0.68,
  "confidence": 0.69,
  "model": "ArcFace"
}
```

### 4. `POST /api/v1/identity/verify-full` (recomendado para el flujo de onboarding)
`multipart/form-data`:
- `document_image` (archivo)
- `selfie_image` (archivo, el mejor frame para el match)
- `liveness_frames` (string JSON con el array de frames base64)

Respuesta: combina los tres resultados anteriores + `overall_result` (bool) y `overall_reason`.

## Ejemplo con curl

```bash
curl -X POST http://localhost:8000/api/v1/document/validate \
  -H "X-API-Key: tu-api-key" \
  -F "file=@documento.jpg"
```


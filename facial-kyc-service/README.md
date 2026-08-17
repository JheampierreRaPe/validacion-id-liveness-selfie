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

## Integración futura con Flutter

Flujo sugerido en la app:
1. Cámara para capturar el documento → `POST /document/validate`.
2. Cámara frontal grabando ~2-3s (o ráfaga de fotos) pidiendo al usuario parpadear → convertir frames a base64 → `POST /liveness/verify` (o incluirlo directo en `/verify-full`).
3. Selfie final nítida.
4. Enviar todo junto a `POST /identity/verify-full`.
5. Tu backend bancario recibe `overall_result` y decide si aprueba la apertura de cuenta o la marca para revisión manual.

En Flutter, esto se puede hacer con el paquete `dio` (multipart requests) y `camera` / `image_picker` para capturar documento y selfie.

## Consideraciones para producción bancaria

Este microservicio es una base sólida, pero antes de producción real en un banco conviene reforzar:

- **Liveness**: el parpadeo es liveness activo básico. Para cumplir estándares antifraude (ISO/IEC 30107-3, certificación iBeta) se recomienda sumar detección de textura/reflejos, o integrar un SDK certificado de liveness.
- **OCR / MRZ**: agregar lectura del documento (Tesseract, o motor MRZ) para validar datos contra el rostro y detectar documentos falsos/alterados.
- **Persistencia y auditoría**: hoy el servicio es *stateless* (no guarda imágenes ni resultados). Para KYC regulado normalmente se requiere guardar evidencia cifrada con retención definida y trazabilidad.
- **Autenticación**: el API Key actual es simple; en producción usar mTLS entre microservicios o JWT firmado por tu backend bancario, nunca exponer este servicio directo a internet.
- **Cifrado en tránsito**: servir detrás de TLS (reverse proxy con HTTPS, ej. Traefik/Nginx).
- **Rate limiting / anti-abuso** en el gateway.
- **Cumplimiento normativo local** (en Perú: SBS, protección de datos personales - Ley N.º 29733) para el tratamiento de datos biométricos.

## Próximo paso

Cuando quieras, seguimos con la integración: backend intermedio (Node/Python) que reciba las llamadas desde Flutter, use este microservicio para el KYC, y solo si `overall_result = true` proceda a crear la cuenta bancaria.

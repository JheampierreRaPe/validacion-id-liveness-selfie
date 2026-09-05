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

> **Acceso desde otros dispositivos (red local):** el servicio y la demo web están configurados para ser accesibles desde cualquier dispositivo de la red. Ver [RED_LOCAL.md](RED_LOCAL.md).

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

---

## Mejora añadida: Liveness guiado por pasos (challenge-response + head pose)

> Sección adicionada sin eliminar lo anterior. Describe el nuevo flujo de liveness
> "por tareas" cuyo trabajo pesado (MediaPipe + DeepFace) ocurre **100% en el servidor**,
> de modo que el frontend (Flutter/app web) solo captura frames y obtiene feedback por tarea.

### Motivo del cambio

El flujo clásico `liveness` solo pedía parpadear sobre una ráfaga de frames. Para una app de
banca se requiere seguir una **secuencia de pasos** (mover la cabeza arriba/abajo/izquierda/
derecha y parpadeo) y que **cada tarea se desbloquee únicamente cuando el servidor la valida**.
La secuencia es generada aleatoriamente por el backend (token anti-replay), así un atacante no
conoce el orden antes de grabar.

### Nuevos endpoints

| Endpoint | Método | Qué hace |
|---|---|---|
| `/api/v1/liveness/challenge` | `POST` | Genera un desafío: `{token, steps:[...]}` en orden aleatorio + TTL. |
| `/api/v1/liveness/evaluate` | `POST` | Evalúa **una** tarea (solo MediaPipe: parpadeo con EAR, o head pose con yaw/pitch). Devuelve `{passed:true/false}` y avanza el desafío si pasó. Es liviano (<1s). |
| `/api/v1/identity/verify-full` | `POST` | Ahora acepta `{token, segments}` con los frames por tarea; valida consistencia de identidad + match DeepFace (lo pesado, una sola vez al final). |

### Flujo recomendado (el dispositivo nunca corre modelos de IA)

```
Cliente                               Servidor (computadora)
1. POST /liveness/challenge    ───►   genera {token, steps aleatorios}
   ◄── token + steps
2. Muestra "mueve la cabeza arriba",
   captura ~8-10 frames
   POST /liveness/evaluate     ───►   valida la task (MediaPipe)
   ◄── passed: true/false   (si falla, reintentar la misma task)
3. Cuando todas las tareas pasaron:
   POST /identity/verify-full ───►   DeepFace: consistencia + match con el documento
   ◄── resultado KYC completo
```

- La tarea N+1 solo se habilita cuando el servidor respondió `passed:true` para la tarea N.
- Si un `evaluate` falla, el cliente reintenta la misma tarea (sin avanzar).
- El token tiene TTL configurable y se consume (borra) al ejecutar `verify-full`.

### Contrato de `/api/v1/liveness/evaluate`

```json
{
  "token": "<token del challenge>",
  "step": "arriba",
  "frames_base64": ["<b64_frame_1>", "<b64_frame_2>", ...]
}
```

Respuesta:
```json
{
  "step": "arriba",
  "passed": true,
  "reason": "Movimiento detectado",
  "frames_analyzed": 10,
  "details": { "pitch_delta": 0.081, "yaw_delta": 0.012, "frames_analyzed": 10 }
}
```

### Contrato de `/api/v1/identity/verify-full` (formato nuevo)

`multipart/form-data` con `document_image` (archivo) y `liveness_frames` (JSON string):

```json
{
  "token": "<token del challenge>",
  "segments": {
    "arriba": ["<b64>", ...],
    "abajo":  ["<b64>", ...],
    "parpadeo": ["<b64>", ...]
  }
}
```

> **Retrocompatibilidad:** `liveness_frames` también sigue aceptando el formato clásico
> (un array plano de strings base64), que se procesa con el flujo de solo-parpadeo.

### Pasos soportados

`arriba`, `abajo`, `izquierda`, `derecha`, `parpadeo` (configurable vía `LIVENESS_CHALLENGE_STEPS`).

### Nuevas variables de entorno (opcionales, con defaults)

```bash
LIVENESS_CHALLENGE_STEPS=arriba,abajo,izquierda,derecha,parpadeo
CHALLENGE_MAX_STEPS=5
CHALLENGE_TOKEN_TTL_SECONDS=180
MIN_FRAMES_PER_SEGMENT=5
HEAD_POSE_BASELINE_FRAMES=3
HEAD_POSE_MOVE_THRESHOLD=0.06
```

### Notas técnicas

- La head pose usa una heurística con los landmarks 2D de MediaPipe FaceMesh (nariz vs.
  centro del rostro), sin `solvePnP` ni calibración de cámara: suficiente para el gate por tarea.
- El estado del desafío (token → pasos → progreso) vive en memoria del proceso
  (`app/core/challenges.py`), con TTL. Para multi-instancia, migrar a Redis.
- La demo web (`web-demo/index.html`) ya ejercita este flujo y puede usarse como referencia
  para implementar el cliente Flutter.


# Integración Flutter: Flujo KYC guiado por pasos (`INTEGRACION_FLUTTER.md`)

> Documento de referencia para el agente/desarrollador que implementará el **frontend Flutter**
> de onboarding KYC consumiendo el microservicio **Facial KYC Service**.
>
> **Principio clave:** el dispositivo móvil **NO ejecuta modelos de IA**. Solo captura ráfagas
> de frames (base64) y consulta al servicio. Todo lo pesado (MediaPipe + DeepFace) corre en el
> servidor (una computadora/backend). Funciona en cualquier celular, incluso de gama baja.

---

## 1. Contexto del servicio (lo que ya existe)

- Backend FastAPI, protegido con header `X-API-Key`.
- Flujo nuevo implementado (fechas: ver git log):
  1. `POST /api/v1/liveness/challenge` → genera orden aleatorio de tareas + token.
  2. `POST /api/v1/liveness/evaluate` → valida UNA tarea; la siguiente se desbloquea solo con `passed:true`.
  3. `POST /api/v1/identity/verify-full` → verificación completa (consistencia + match con el documento).
- Formatos antiguos (solo parpadeo) siguen soportados (retrocompatibilidad), pero el flujo nuevo es el recomendado.

---

## 2. Ciclo de vida del flujo en Flutter

```
[1] Solicitar desafío
      POST /liveness/challenge
      <- { token, steps: ["abajo","izquierda","parpadeo",...] , expires_in: 180 }

[2] Por cada paso en orden:
      Mostrar al usuario la instrucción del paso actual
      Capturar ~8-10 frames (ráfaga corta) de la cámara frontal
      POST /liveness/evaluate  { token, step, frames_base64 }
      <- { passed, reason, details }

      Si passed == false  -> mostrar reintento, NO avanzar
      Si passed == true   -> guardar segmento y avanzar al siguiente paso

[3] Cuando todas las tareas pasaron:
      Enviar documento + POST /identity/verify-full
      <- resultado KYC completo (documento + liveness + consistencia + match biométrico)
```

**Regla de seguridad:** el orden de los pasos es impuesto por el servidor. Si el cliente envía
un paso distinto al pendiente, el backend responde `400` "se esperaba la tarea X".

---

## 3. Contratos de la API

### 3.1 `POST {BASE}/api/v1/liveness/challenge`
- Headers: `X-API-Key: <API_KEY>`
- Body: vacío.
- Respuesta `200`:
```json
{
  "token": "w9xQ...",
  "steps": ["abajo", "izquierda", "parpadeo", "arriba", "derecha"],
  "expires_in": 180
}
```
- El `token` debe conservarse durante todo el flujo; al expirar, el backend responde `400` y
  el cliente debe solicitar un desafío nuevo.

### 3.2 `POST {BASE}/api/v1/liveness/evaluate`
- Headers: `X-API-Key`.
- Body (JSON):
```json
{
  "token": "w9xQ...",
  "step": "abajo",
  "frames_base64": ["<b64>", "<b64>", "..."]
}
```
- Respuesta `200`:
```json
{
  "step": "abajo",
  "passed": true,
  "reason": "Movimiento detectado",
  "frames_analyzed": 10,
  "details": { "pitch_delta": 0.081, "yaw_delta": 0.012, "frames_analyzed": 10 }
}
```
- Para el paso `"parpadeo"`, `details` contendrá `blinks_detected`.
- Errores `400` (manejar en Flutter):
  - `"Token de desafío inválido o expirado..."` → reiniciar el flujo.
  - `"Se esperaba la tarea 'X'..."` → el cliente envió el paso fuera de orden; corregir lógica.
  - `"El desafío ya fue completado..."` → pasar directo a `verify-full`.
- `passed:false` NO es error HTTP (200 con `passed:false`) → el cliente reintenta la misma tarea.

### 3.3 `POST {BASE}/api/v1/identity/verify-full`
- Headers: `X-API-Key`.
- Body: `multipart/form-data`
  - `document_image`: archivo (foto del documento/DNI).
  - `liveness_frames`: string JSON
```json
{
  "token": "w9xQ...",
  "segments": {
    "arriba": ["<b64>", "..."],
    "abajo":  ["<b64>", "..."],
    "izquierda": ["<b64>", "..."],
    "derecha": ["<b64>", "..."],
    "parpadeo": ["<b64>", "..."]
  }
}
```
  `segments` debe contener **todos** los pasos del desafío, usando la ráfaga final que fue
  validada con `passed:true` en el paso 2.
- Respuesta `200` (el `overall_result` decide aprobación):
```json
{
  "document_validation": { "is_valid": true, "issues": [], "checks": { ... } },
  "liveness": {
    "is_live": true,
    "reason": "Todos los pasos del desafío fueron validados",
    "blinks_detected": 2,
    "frames_analyzed": 50,
    "ear_series": [ ... ],
    "steps_total": ["abajo", "izquierda", "parpadeo", "arriba", "derecha"],
    "steps_verified": ["abajo", "izquierda", "parpadeo", "arriba", "derecha"],
    "step_results": { "abajo": { "passed": true, "reason": "...", "details": {...} } }
  },
  "identity_consistency": { "checked": true, "is_consistent": true, "distance": 0.42 },
  "face_match": { "is_match": true, "distance": 0.55, "threshold": 0.68, "confidence": 0.6, "model": "ArcFace" },
  "overall_result": true,
  "overall_reason": "Verificación de identidad exitosa"
}
```

---

## 4. Guía de implementación en Flutter

### 4.1 Dependencias sugeridas
- Cámara: `camera` (plugin oficial) con `ResolutionPreset.low`/`medium` para no saturar memoria.
- HTTP: `http` o `dio` (con headers `X-API-Key`).
- Conversión frame → base64: capturar `CameraController.takePicture()` no es ideal para ráfagas;
  usar **stream de frames** vía `camera` con `ImageStream` o el paquete `camera_web`/`camera_android_camerax`,
  o `yield` un cuadro del `CameraPreview` con `RepaintBoundary`. En gama alta: `camera` da
  `takePicture()` por frame (más lento). Alternativa recomendada: interop con `CameraX`/`ML Kit`
  SOLO para captura, nunca para análisis.

### 4.2 Captura por pasos (ráfaga)
- Al mostrar la instrucción del paso (p. ej. "mueve la cabeza hacia arriba"), iniciar una ráfaga
  de **8-10 frames en ~1.5s** (150 ms entre frame).
- El frame debe codificarse a **JPEG base64 sin `data:` prefix** (solo el payload base64).
  El backend acepta también con `data:image/jpeg;base64,...`, pero es más liviano sin prefijo.
- Recomendación de UX (heredada de la web-demo):
  - Mostrar un overlay con la instrucción del paso actual.
  - Mostrar progreso de pasos (hecho / actual / pendiente).
  - Si `passed:false` → botón "Reintentar tarea" (capturar de nuevo el mismo paso).
  - Cuando todos pasaron → habilitar el botón "Verificar identidad".

### 4.3 Manejo de errores
| Condición | Acción |
|---|---|
| `401` | API Key inválida → fallar flujo, revisar configuración |
| `400` token inválido/expirado | Reiniciar flujo (nuevo `/challenge`) |
| `400` paso fuera de orden | Bug de lógica: nunca debería ocurrir si se sigue el orden recibido |
| `400` desafío completado | Saltar a `verify-full` |
| `passed:false` (200) | Reintentar la misma tarea |
| Sin conexión / timeout | Mantener el desafío y reintentar (el token TTL es 180s) |

### 4.4 Consideraciones de UX para banca
- Mostrar avisos: iluminación adecuada, mirar a la cámara, movimientos lentos y sostenidos.
- No avanzar nunca de forma automática por tiempo: exigir `passed:true` del servidor.
- Guardar el token del desafío en memoria de sesión; descartarlo al terminar (o al expirar).
- No almacenar frames base64 en disco (datos biométricos sensibles).

---

## 5. Qué NO debe hacer el frontend
- NO ejecutar MediaPipe/TensorFlow en el dispositivo (es el motivo del diseño).
- NO generar su propia secuencia de pasos (debe usar la del `/challenge`).
- NO marcar una tarea como aprobada sin respuesta `passed:true` del servidor.

---

## 6. Notas de configuración del servicio
- URL base y `X-API-Key` configurados en el backend (servidor/PC). Desde emulador Android
  usar `10.0.2.2` y desde dispositivo físico la IP del PC en la red local.
- El endpoint de prueba web se sirve con `web-demo/servidor_demo.py` (`http://<ip>:8080`).
- Documentación interactiva Swagger: `http://<ip>:8000/docs`.
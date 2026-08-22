# Documentación del Servicio: Facial KYC Service (`SERVICE.md`)

---

## 1. Propósito
El **Facial KYC Service** es un microservicio backend desarrollado en **FastAPI** diseñado para automatizar y asegurar el proceso de verificación de identidad digital (Onboarding KYC - *Know Your Customer*). Su función principal es validar la autenticidad de un documento de identidad, comprobar la vitalidad del usuario en tiempo real mediante liveness activo (detección de parpadeo) y realizar un emparejamiento biométrico facial (*face matching*) entre el rostro del documento y la selfie del usuario obtenida de forma segura durante la secuencia de liveness.

---

## 2. Responsabilidades
- **Validación de Documentos:** Analizar la calidad de la imagen del documento de identidad mediante métricas de nitidez (Laplaciano) y detección de características básicas.
- **Liveness Activo:** Procesar una secuencia de fotogramas (frames en base64) de la cámara frontal del usuario para medir el Ratio de Aspecto Ocular (EAR) y verificar que se trata de una persona real parpadeando.
- **Extracción Automática de Selfie:** Identificar y extraer de forma inteligente el fotograma más nítido y frontal dentro de la secuencia de liveness para utilizarlo como selfie biométrica oficial, evitando suplantaciones o uso de fotos estáticas secundarias.
- **Consistencia de Identidad:** Validar que el rostro al inicio de la captura de liveness coincida con el mejor fotograma seleccionado, asegurando que la misma persona realizó toda la prueba.
- **Match Biométrico:** Comparar el rostro extraído del documento contra la selfie obtenida mediante modelos avanzados de reconocimiento facial (DeepFace / RetinaFace).
- **Seguridad perimetral básica:** Protección de endpoints mediante autenticación por clave de API (`x-api-key`).

---

## 3. Tecnologías
- **Framework Web:** FastAPI (Python 3.10+) con soporte asíncrono y documentación automática OpenAPI (Swagger/ReDoc).
- **Servidor ASGI:** Uvicorn.
- **Procesamiento de Imágenes y Visión Artificial:** 
  - **OpenCV (`opencv-python-headless`)**: Manipulación de matrices de imagen, decodificación y cálculo de métricas de nitidez.
  - **MediaPipe (`mediapipe`)**: Detección de malla facial (*Face Mesh*) y cálculo de puntos clave para el parpadeo (EAR).
  - **DeepFace & RetinaFace**: Motores de deep learning para extracción de embeddings y verificación/match biométrico de rostros.
- **Cálculo Numérico y Científico:** NumPy y SciPy.
- **Contenedorización:** Docker y Docker Compose con volúmenes persistentes para caché de modelos de IA.

---

## 4. Estructura de archivos
```text
facial-kyc-service/
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── routers/
│   │           ├── document.py      # Endpoints de validación de documentos
│   │           ├── identity.py      # Endpoints del flujo completo de onboarding (verify-full)
│   │           └── liveness.py      # Endpoints de verificación de liveness activo
│   ├── core/
│   │   ├── config.py                # Configuración global mediante pydantic-settings
│   │   └── security.py              # Validación de API Key
│   ├── schemas/
│   │   └── models.py                # Esquemas de Pydantic para request/response
│   ├── services/
│   │   ├── document_service.py      # Lógica de análisis de documentos
│   │   ├── face_service.py          # Lógica de comparación facial (DeepFace)
│   │   ├── image_utils.py           # Utilidades de imagen (blur, decode)
│   │   └── liveness_service.py      # Detección de parpadeo y extracción de mejor frame
│   └── main.py                      # Inicialización de la aplicación FastAPI y CORS
├── scripts/
│   └── warmup_models.py             # Script de precarga de pesos de modelos de IA
├── Dockerfile                       # Definición de imagen Docker optimizada
├── docker-compose.yml               # Orquestación de servicios y volúmenes
├── requirements.txt                 # Dependencias de Python
├── .env.example                     # Plantilla de variables de entorno
└── README.md                        # Documentación general y guía rápida
```

---

## 5. Endpoints
Todos los endpoints principales se encuentran bajo el prefijo `/api/v1`.

### 🏥 Health Check
- `GET /health`
  - **Descripción:** Verifica el estado operativo del microservicio.
  - **Respuesta:** `{"status": "ok", "service": "Facial KYC Service"}`

### 📄 Documento (`/api/v1/document`)
- `POST /api/v1/document/validate`
  - **Descripción:** Valida la calidad y nitidez de la imagen del documento de identidad.
  - **Parámetros:** `file` (UploadFile).
  - **Seguridad:** Requiere header `x-api-key`.

### 👁️ Liveness (`/api/v1/liveness`)
- `POST /api/v1/liveness/verify`
  - **Descripción:** Analiza una secuencia de frames en base64 para detectar parpadeo activo.
  - **Parámetros:** JSON body (`LivenessRequest` con `frames_base64`).
  - **Seguridad:** Requiere header `x-api-key`.

### 🧬 Identidad / Onboarding Completo (`/api/v1/identity`)
- `POST /api/v1/identity/verify-full`
  - **Descripción:** Flujo KYC completo en una sola llamada. Recibe la foto del documento y los frames de liveness. Extrae automáticamente la mejor selfie del liveness, valida la consistencia de identidad a lo largo del video y realiza el match biométrico contra el documento.
  - **Parámetros (Multipart Form):**
    - `document_image`: Archivo de imagen del documento.
    - `liveness_frames`: String JSON con array de imágenes en base64.
  - **Seguridad:** Requiere header `x-api-key`.

---

## 6. Dependencias
Definidas en `requirements.txt`:
- `fastapi==0.111.0`
- `uvicorn==0.29.0`
- `pydantic==2.7.1`
- `pydantic-settings==2.2.1`
- `python-multipart==0.0.9`
- `opencv-python-headless==4.10.0.84`
- `deepface==0.0.93`
- `tensorflow==2.16.1`
- `tf-keras==2.16.0`
- `mediapipe==0.10.14`
- `retina-face==0.0.17`
- `scipy==1.13.0`
- `numpy==1.26.4`

---

## 7. Variables de entorno
Configurables a través de `.env` (basado en `.env.example`):
- `APP_NAME`: Nombre del microservicio (por defecto: `"Facial KYC Service"`).
- `API_KEY`: Clave secreta para autenticación de llamadas a los endpoints protegidos.
- `MIN_FRAMES_FOR_LIVENESS`: Cantidad mínima de fotogramas requeridos para validar el liveness (por defecto: `10`).
- `FACE_MATCH_THRESHOLD`: Umbral de distancia para determinar si dos rostros coinciden en DeepFace.
- `BLUR_LAPLACIAN_THRESHOLD`: Umbral de varianza Laplaciana para considerar una imagen nítida (por defecto: `0.55`).
- `IDENTITY_CONSISTENCY_THRESHOLD`: Umbral de similitud para validar que la persona es la misma entre el primer frame y el mejor frame del liveness (por defecto: `0.68`).

---

## 8. Estado actual
- **Fase:** Versión 1.0.0 estable / Lista para integración con frontend (Flutter/React Native).
- **Características operativas:**
  - Stateless (sin persistencia propia en base de datos; devuelve resultados estructurados para que el backend orquestador los almacene o procese).
  - Contenedorizado con Docker listo para despliegue en nube o servidores locales.
  - Extracción automática de selfie desde liveness implementada y probada, eliminando fricción al usuario final al no requerir captura de selfie adicional por separado.

---

## 9. Problemas conocidos
- **Carga inicial de modelos:** La primera petición a los servicios de DeepFace / MediaPipe puede demorar unos segundos mientras los pesos neuronales se cargan en memoria RAM/VRAM. (Mitigado parcialmente mediante el script `warmup_models.py` durante el arranque del contenedor).
- **Uso de CPU/Memoria:** TensorFlow y DeepFace consumen recursos considerables de CPU cuando no se dispone de aceleración por GPU, por lo que se recomienda dimensionar adecuadamente la infraestructura (mínimo 2GB - 4GB de RAM).
- **Iluminación extrema:** Ambientes con muy baja luz o contraluz severo pueden dificultar la detección de la malla facial por MediaPipe o bajar la confianza del match biométrico.

---

## 10. Reglas específicas
- **Seguridad de Endpoints:** Ningún endpoint de negocio (`/document`, `/liveness`, `/identity`) debe exponerse públicamente sin validación previa de la cabecera `x-api-key`.
- **Integridad de Datos:** Los frames enviados para liveness deben estar codificados correctamente en formato base64 y pertenecer a una secuencia de video continua de la misma sesión de captura del usuario.
- **Manejo de Excepciones:** Los fallos en la decodificación de imágenes o JSONs malformados devuelven errores HTTP 400 descriptivos para facilitar el debugging desde el cliente móvil.
- **Evolución del Servicio:** No se deben introducir librerías de IA pesadas adicionales sin verificar el impacto en el tamaño de la imagen Docker y los tiempos de arranque en frío.

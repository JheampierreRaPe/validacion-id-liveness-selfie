import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routers import document, identity, liveness
from app.core.config import settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Microservicio de verificación de identidad: validación de documento, "
        "liveness activo (parpadeo) y comparación biométrica facial. "
        "Diseñado para integrarse como paso de onboarding en una app bancaria (Flutter)."
    ),
    version="1.0.0",
)

# CORS abierto por defecto para facilitar pruebas desde apps móviles / web.
# En producción restringir 'allow_origins' al dominio real del frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(document.router)
app.include_router(liveness.router)
app.include_router(identity.router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": settings.APP_NAME}

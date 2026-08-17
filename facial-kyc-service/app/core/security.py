from fastapi import Header, HTTPException, status
from app.core.config import settings


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    """
    Dependencia simple de autenticación por API Key.
    En producción reemplazar por JWT / OAuth2 / mTLS entre microservicios,
    o validar contra un servicio de identidad interno (Vault, IAM, etc).
    """
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida o ausente",
        )

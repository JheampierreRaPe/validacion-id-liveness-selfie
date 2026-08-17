import base64
import binascii

import cv2
import numpy as np
from fastapi import HTTPException, status


def decode_base64_image(b64_string: str) -> np.ndarray:
    """Decodifica un string base64 (con o sin prefijo data URI) a imagen OpenCV (BGR)."""
    try:
        if "," in b64_string and b64_string.strip().startswith("data:"):
            b64_string = b64_string.split(",", 1)[1]
        img_bytes = base64.b64decode(b64_string, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo decodificar la imagen base64 proporcionada",
        )

    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El contenido decodificado no es una imagen válida",
        )
    return img


def decode_upload_bytes(raw_bytes: bytes) -> np.ndarray:
    """Decodifica bytes crudos (de un UploadFile) a imagen OpenCV (BGR)."""
    np_arr = np.frombuffer(raw_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo enviado no es una imagen válida",
        )
    return img


def blur_score(image: np.ndarray) -> float:
    """Varianza del Laplaciano: valores bajos indican imagen borrosa."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def brightness_score(image: np.ndarray) -> float:
    """Brillo promedio (0-255) del canal de luminancia."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def image_dimensions(image: np.ndarray) -> tuple[int, int]:
    h, w = image.shape[:2]
    return w, h

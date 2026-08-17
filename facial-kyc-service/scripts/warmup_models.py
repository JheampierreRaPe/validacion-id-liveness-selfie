"""
Script ejecutado durante el build de Docker para pre-descargar los pesos
del modelo de reconocimiento facial, evitando latencia en el primer request
real en producción.

Si no hay acceso a internet durante el build, el script no falla el build:
solo avisa, y los pesos se descargarán en el primer request real (siempre
que el contenedor en ejecución sí tenga acceso a internet).
"""

import sys


def main() -> None:
    try:
        from deepface import DeepFace

        print("Descargando/preparando modelo ArcFace...")
        DeepFace.build_model("ArcFace")
        print("Modelo ArcFace listo.")
    except Exception as exc:  # noqa: BLE001
        print(f"Aviso: no se pudo pre-descargar el modelo en build time: {exc}")
        print("Los pesos se descargarán en el primer request si hay internet disponible en runtime.")
        # No usamos sys.exit(1) a propósito: no queremos que esto tumbe el build.
        sys.exit(0)


if __name__ == "__main__":
    main()

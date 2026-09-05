# Acceso por Red Local (`RED_LOCAL.md`)

> **Registro de cambio:** Este proyecto fue modificado para que tanto el **microservicio API** como la **demo web** sean accesibles desde otros dispositivos de la red local (móvil, otra PC, emuladores, etc.), y no solo desde `localhost` en el equipo donde corre.

---

## 1. Resumen del cambio

| Archivo | Antes | Después |
|---|---|---|
| `web-demo/servidor_demo.py` | Escuchaba en `127.0.0.1:8080` (solo local) | Escucha en `0.0.0.0:8080` (todas las interfaces) e imprime las IPs de la LAN al arrancar |
| `web-demo/index.html` | URL del servicio fija a `http://localhost:8000` | Autocompleta `http://<IP-del-host>:8000` cuando se abre desde otro dispositivo |
| `Dockerfile` / `docker-compose.yml` | Ya publicaban `0.0.0.0:8000:8000` | Sin cambios (ya era accesible por LAN vía Docker) |

---

## 2. Cómo levantar el servicio para acceso por red local

### Opción A — Con Docker (recomendada)

```bash
docker compose up --build
```

El contenedor ya publica el puerto en todas las interfaces (`0.0.0.0:8000:8000`), por lo que es automáticamente accesible desde la red local.

### Opción B — Sin Docker (uvicorn directo)

Es importante pasar `--host 0.0.0.0`:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Demo web

```bash
python web-demo/servidor_demo.py
```

Al arrancar muestra algo como:

```text
Demo KYC disponible en:      http://localhost:8080
Acceso desde la red local:   http://192.168.1.50:8080
Presiona Ctrl+C para detener
```

---

## 3. Conocer la IP del equipo servidor

En Windows:

```powershell
ipconfig    # buscar "Dirección IPv4" del adaptador Wi-Fi o Ethernet activo
```

En Linux/macOS:

```bash
hostname -I          # Linux
ipconfig getifaddr en0   # macOS
```

Ejemplo: si tu IP es `192.168.1.50`, los demás dispositivos acceden a:

- **API:** `http://192.168.1.50:8000` (Swagger en `/docs`)
- **Demo web:** `http://192.168.1.50:8080`

La demo web autodetecta esta IP: si abres la página desde el móvil, el campo *"URL del servicio"* se completa solo con la IP del host que sirve la página.

---

## 4. Firewall (Windows)

Para permitir conexiones entrantes en los puertos 8000 y 8080, ejecutar en PowerShell **como Administrador**:

```powershell
New-NetFirewallRule -DisplayName "KYC Facial API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "KYC Facial Demo 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private
```

Con Docker Desktop esto normalmente ya funciona; si no, verificar que la red esté marcada como **Privada** en Windows.

---

## 5. Advertencia importante: cámara en la demo web

Los navegadores solo permiten acceder a la cámara (`getUserMedia`) en **contextos seguros**: `https://` o `http://localhost`.

Al abrir la demo desde otro dispositivo con `http://192.168.x.x:8080`, la cámara estará bloqueada por el navegador. Soluciones:

1. **Chrome (PC/Android):** abrir `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, agregar `http://192.168.1.50:8080`, marcar *Enabled* y reiniciar el navegador.
2. **Probar todo en localhost** y usar la red local solo para consumir la API desde una app nativa (Flutter/Android), que no tiene esa restricción.
3. Servir la demo por HTTPS con un certificado autofirmado (no cubierto en esta guía).

> Nota: Android exige HTTPS por defecto incluso para apps nativas; si la app Flutter consume `http://192.168.x.x`, configurar `usesCleartextTraffic` / network security config.

---

## 6. Seguridad

Este modo expone el servicio a toda la red local. Recordar:

- Los endpoints de negocio siguen protegidos por el header `X-API-Key` (configurar una clave real en `.env`).
- No exponer estos puertos al internet público sin un reverse proxy + TLS.
- Al terminar las pruebas, detener los servicios o revertir `HOST = "0.0.0.0"` a `"127.0.0.1"` en `web-demo/servidor_demo.py`.

import http.server
import os
import socket
import socketserver

PORT = 8080
HOST = "0.0.0.0"  # Escucha en todas las interfaces => accesible desde la red local
os.chdir(os.path.dirname(os.path.abspath(__file__)))


def obtener_ips_locales():
    """Devuelve las direcciones IPv4 de este equipo en la(s) red(es) local(es)."""
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with Server((HOST, PORT), Handler) as httpd:
        print(f"Demo KYC disponible en:      http://localhost:{PORT}")
        for ip in obtener_ips_locales():
            print(f"Acceso desde la red local:   http://{ip}:{PORT}")
        print("Presiona Ctrl+C para detener")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido")

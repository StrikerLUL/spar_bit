"""Kopfzeilen, die dem Browser sagen, was er nicht tun soll.

Die Docker-Variante setzte drei davon in nginx. Der lokale Start liefert
die Oberflaeche aber direkt aus dem Backend aus - dort gab es sie also
gar nicht. Und eine Content-Security-Policy fehlte auf beiden Wegen:
ohne sie darf jedes eingeschleuste Skript nachladen, wohin es will.

Ausgenommen ist die API-Dokumentation unter /api/docs: die laedt Swagger
von einem CDN und braucht Inline-Styles. Sie mit einer Policy zu
erschlagen, die sie nicht erfuellen kann, haette nur eine kaputte Seite
ergeben.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Erlaubt ist, was die Oberflaeche wirklich braucht:
#  - Skripte und Stile nur von hier (Vite baut ein Bundle, kein Inline-Skript)
#  - 'unsafe-inline' allein fuer Stile: React setzt style-Attribute
#  - Bilder auch von fremden https-Adressen: Deal-Bilder kommen vom Haendler,
#    solange der Bild-Zwischenspeicher aus ist
#  - keine Einbettung in fremde Seiten, kein <object>, kein <base>-Umbiegen
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' https: data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
])

OHNE_CSP = ("/api/docs", "/api/redoc", "/api/openapi.json")

BASIS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # Beim Klick auf einen Deal soll der Shop nicht erfahren, unter welcher
    # Adresse die eigene SparBit-Installation laeuft.
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SicherheitsHeader(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        antwort = await call_next(request)
        for name, wert in BASIS.items():
            antwort.headers.setdefault(name, wert)

        if not request.url.path.startswith(OHNE_CSP):
            antwort.headers.setdefault("Content-Security-Policy", CSP)

        # HSTS nur, wenn wirklich ueber https gesprochen wird. Auf einem
        # lokalen http-Start waere die Kopfzeile wirkungslos - hinter einem
        # Proxy, der sie zu frueh setzt, dagegen ein Selbstschuss.
        weiterleitung = request.headers.get("x-forwarded-proto", "")
        if request.url.scheme == "https" or weiterleitung == "https":
            antwort.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return antwort

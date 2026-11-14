"""Límite de peticiones por IP (ventana fija) para que nadie agote la cuota de Gemini/Groq ni llene la base de datos.

Usa la caché de Django (LocMem por defecto: vale para un solo proceso; con varios procesos configura Redis en CACHES).
"""
import functools
import time

from decouple import config
from django.core.cache import cache
from django.http import JsonResponse

ENABLED = config("RATELIMIT_ENABLED", default=True, cast=bool)
# Detrás de un proxy de confianza (nginx, cloudflared) la IP real llega en X-Forwarded-For.
# Solo se lee si lo activas: si no, cualquiera podría falsificar esa cabecera para saltarse el límite.
TRUST_FORWARDED = config("RATELIMIT_TRUST_X_FORWARDED_FOR", default=False, cast=bool)


def client_ip(request) -> str:
    if TRUST_FORWARDED:
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "?"


def ratelimit(name: str, limit: int, window: int = 60):
    """Máximo `limit` peticiones cada `window` segundos por IP para la vista `name`."""
    def decorator(view):
        @functools.wraps(view)
        async def wrapper(request, *args, **kwargs):
            if ENABLED:
                bucket = int(time.time() // window)
                key = f"rl:{name}:{client_ip(request)}:{bucket}"
                added = await cache.aadd(key, 1, timeout=window + 5)
                try:
                    count = 1 if added else await cache.aincr(key)
                except ValueError:  # la clave caducó justo entre add e incr
                    await cache.aset(key, 1, timeout=window + 5)
                    count = 1
                if count > limit:
                    resp = JsonResponse({"error": "Vas muy rápido. Espera un momento y vuelve a intentarlo."}, status=429)
                    resp["Retry-After"] = str(window - int(time.time() % window))
                    return resp
            return await view(request, *args, **kwargs)
        return wrapper
    return decorator

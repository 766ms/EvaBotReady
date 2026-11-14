"""Texto a voz con Groq: convierte un trozo de la respuesta de Eva en audio WAV.

Límites del modelo que hay que tener presentes (Groq, Orpheus):
- Solo inglés (`canopylabs/orpheus-v1-english`). El español se lee con fonética inglesa: funciona, pero suena raro.
  Cuando Groq publique una voz en español, basta con cambiar GROQ_TTS_MODEL y GROQ_TTS_VOICE en .env.
- Máximo 200 caracteres por petición: la respuesta se parte en trozos en el navegador.
"""
import asyncio
import logging

import httpx
from decouple import config

logger = logging.getLogger(__name__)

GROQ_TTS_URL = "https://api.groq.com/openai/v1/audio/speech"
TTS_MODEL = config("GROQ_TTS_MODEL", default="canopylabs/orpheus-v1-english")
TTS_VOICE = config("GROQ_TTS_VOICE", default="diana")  # voces de Orpheus: autumn, diana, hannah, austin, daniel, troy
MAX_CHARS = 200  # límite por petición de Orpheus
_client: httpx.AsyncClient | None = None


class TTSError(RuntimeError):
    """La voz no está disponible ahora mismo (sin clave, sin conexión o Groq respondió con error)."""


def available() -> bool:
    return bool(config("GROQ_API_KEY", default="").strip())


def _get_client() -> httpx.AsyncClient:
    global _client
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    client_loop = getattr(_client, "_custom_loop", None)
    if _client is None or _client.is_closed or client_loop is not current_loop:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=8),
            limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=120),
        )
        _client._custom_loop = current_loop
    return _client


async def synthesize(text: str) -> bytes:
    """Devuelve el audio WAV de `text` (un trozo de hasta MAX_CHARS caracteres)."""
    key = config("GROQ_API_KEY", default="").strip()
    if not key:
        raise TTSError("Falta GROQ_API_KEY")
    if not text or len(text) > MAX_CHARS:
        raise TTSError("Fragmento fuera de los límites de Groq")
    body = {"model": TTS_MODEL, "input": text, "voice": TTS_VOICE, "response_format": "wav"}
    try:
        resp = await _get_client().post(GROQ_TTS_URL, json=body, headers={"Authorization": f"Bearer {key}"})
    except (httpx.HTTPError, RuntimeError) as exc:
        raise TTSError("Sin conexión con Groq TTS") from exc
    if resp.status_code != 200:
        logger.warning("Groq TTS respondió %s: %s", resp.status_code, resp.text[:300])
        raise TTSError(f"Groq TTS respondió {resp.status_code}")
    return resp.content

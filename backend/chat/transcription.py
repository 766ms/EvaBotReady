"""Voz a texto. Groq Whisper (rápido, en la nube) con respaldo en Whisper local (faster-whisper).

STT_PROVIDER en .env:
  auto  (por defecto) -> Groq si hay GROQ_API_KEY; si falla o no hay clave, Whisper local.
  groq                -> solo Groq (con respaldo local si Groq falla y faster-whisper está instalado).
  local               -> solo Whisper local, el audio nunca sale de tu equipo.
"""
import asyncio
import io
import logging
import threading

import httpx
from decouple import Csv, config

from . import groq_client

logger = logging.getLogger(__name__)

STT_PROVIDER = config("STT_PROVIDER", default="auto").strip().lower()
STT_MODEL = config("STT_MODEL", default="whisper-large-v3-turbo")  # o whisper-large-v3 (más preciso, más lento)
STT_LANGUAGES = config("STT_LANGUAGES", default="es,en", cast=Csv())
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL_SIZE = config("WHISPER_MODEL", default="base")  # local: tiny, base, small, medium

# Frases que Whisper "inventa" cuando el audio es silencio o ruido.
_ALUCINACIONES = ("amara.org", "subtítulos realizados por", "subtitulos realizados por")

_EXT = {
    "audio/webm": "webm", "video/webm": "webm", "audio/ogg": "ogg", "audio/opus": "ogg",
    "audio/mp4": "mp4", "audio/x-m4a": "m4a", "audio/m4a": "m4a", "audio/aac": "m4a",
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/flac": "flac",
}

_model = None
_lock = threading.Lock()
_client: httpx.AsyncClient | None = None


class TranscriptionError(RuntimeError):
    """El dictado no está disponible ahora mismo (ni Groq ni el Whisper local pudieron)."""


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


def _clean(text: str) -> str:
    text = (text or "").strip()
    if any(p in text.lower() for p in _ALUCINACIONES):
        return ""
    return text


_LANG_NAMES = {
    "es": {"es", "spanish", "español"},
    "en": {"en", "english", "ingles", "inglés"},
}


# ---------- Groq ----------
async def _run_groq(audio: bytes, content_type: str) -> str:
    key = config("GROQ_API_KEY", default="").strip()
    ctype = (content_type or "audio/webm").split(";")[0].strip().lower()
    ext = _EXT.get(ctype, "webm")
    multi = len(STT_LANGUAGES) > 1
    data = {"model": STT_MODEL, "response_format": "verbose_json" if multi else "json", "temperature": "0"}
    if not multi:
        data["language"] = STT_LANGUAGES[0] if STT_LANGUAGES else "es"

    resp = await _get_client().post(
        GROQ_STT_URL,
        headers={"Authorization": f"Bearer {key}"},
        files={"file": (f"audio.{ext}", audio, ctype)},
        data=data,
    )
    if resp.status_code != 200:
        raise TranscriptionError(f"Groq STT respondió {resp.status_code}: {resp.text[:300]}")

    payload = resp.json()
    if multi:
        detected = (payload.get("language") or "").lower()
        allowed = set()
        for lang in STT_LANGUAGES:
            allowed.update(_LANG_NAMES.get(lang.lower(), {lang.lower()}))
        if detected and detected not in allowed:
            data_retry = {"model": STT_MODEL, "language": "es", "response_format": "json", "temperature": "0"}
            resp_retry = await _get_client().post(
                GROQ_STT_URL,
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (f"audio.{ext}", audio, ctype)},
                data=data_retry,
            )
            if resp_retry.status_code == 200:
                return _clean(resp_retry.json().get("text", ""))
    return _clean(payload.get("text", ""))


# ---------- Whisper local ----------
def _load():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel  # import diferido: solo se necesita si se usa el modo local
            logger.info("Cargando Whisper '%s' (la primera vez descarga el modelo)", MODEL_SIZE)
            _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def _run_local(audio: bytes) -> str:
    multi = len(STT_LANGUAGES) > 1
    if multi:
        segments, info = _load().transcribe(io.BytesIO(audio), language=None, beam_size=1, vad_filter=True)
        detected = (getattr(info, "language", "") or "").lower()
        allowed = set()
        for lang in STT_LANGUAGES:
            allowed.update(_LANG_NAMES.get(lang.lower(), {lang.lower()}))
        if detected and detected not in allowed:
            segments, _ = _load().transcribe(io.BytesIO(audio), language="es", beam_size=1, vad_filter=True)
    else:
        lang = STT_LANGUAGES[0] if STT_LANGUAGES else "es"
        segments, _ = _load().transcribe(io.BytesIO(audio), language=lang, beam_size=1, vad_filter=True)
    return _clean(" ".join(s.text.strip() for s in segments))


# ---------- API pública ----------
async def transcribe(audio: bytes, content_type: str = "") -> str:
    """Transcribe el audio. Lanza ImportError si solo hay modo local y falta faster-whisper."""
    use_groq = STT_PROVIDER != "local" and groq_client.available()
    if use_groq:
        try:
            return await _run_groq(audio, content_type)
        except (httpx.HTTPError, TranscriptionError, ValueError) as exc:
            logger.warning("Groq STT falló (%s). Se intenta con Whisper local.", exc)
            try:
                return await asyncio.to_thread(_run_local, audio)
            except ImportError:
                raise TranscriptionError("El dictado no está disponible ahora mismo.") from exc
    return await asyncio.to_thread(_run_local, audio)

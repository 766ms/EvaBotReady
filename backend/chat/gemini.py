"""Cliente de Google Gemini (Free Tier) con selección automática del modelo más rápido.

Cómo elige el modelo (sin gastar cuota en pruebas previas):
  1. Descubre los modelos Flash que admiten streaming (lista cacheada 1 h).
  2. Ordena por calidad (Flash > Flash-Lite, estables antes que preview, versión más nueva).
  3. Mide el tiempo hasta el primer token de cada modelo y prioriza los más rápidos.
  4. Si un modelo da 429 (cuota), 404, 5xx o tarda demasiado en empezar, se enfría
     durante un tiempo y se usa el siguiente, sin que el usuario lo note.
"""
import asyncio
import json
import logging
import re
import time

import httpx
from decouple import Csv, config

from .prompts import build_contents, build_system

logger = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
CATALOG_TTL = 3600           # s: refrescar la lista de modelos
MAX_OUTPUT_TOKENS = config("MAX_REPLY_TOKENS", default=300, cast=int)  # tope duro; la longitud real la marca el prompt
FIRST_TOKEN_TIMEOUT = config("FIRST_TOKEN_TIMEOUT", default=3, cast=float)  # s por modelo para empezar
MAX_ATTEMPTS = config("GEMINI_MAX_ATTEMPTS", default=5, cast=int)            # modelos a probar como máximo
MANUAL_ORDER = config("GEMINI_MODELS", default="", cast=Csv())
# Gemini 3.x piensa en nivel "high" por defecto: son varios segundos antes del primer token.
# "minimal" (o "low" si el modelo no acepta minimal) lo reduce a casi cero.
THINKING_LEVEL = config("GEMINI_THINKING_LEVEL", default="minimal")
_LEVEL_DOWN = {"minimal": "low", "low": None}
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]
_SKIP = ("image", "tts", "live", "audio", "embedding", "computer", "robotics")
_FLASH = re.compile(r"gemini-(\d+(?:\.\d+)?)-flash(-lite)?(?:-|$)")
# Filtro de seguridad de Google: bloquea según el umbral en cada categoría.
SAFETY_SETTINGS = [
    {"category": c, "threshold": "BLOCK_LOW_AND_ABOVE"}
    for c in ("HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
              "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")
]

_catalog = {"models": [], "at": 0.0}
_cooldown: dict[str, float] = {}   # modelo -> instante (monotonic) hasta el que se evita
_ttft: dict[str, float] = {}       # modelo -> tiempo medio hasta el primer token (s)
_thinking_level: dict[str, str | None] = {}   # modelo -> nivel de pensamiento que Google aceptó
_lock = asyncio.Lock()
_client: httpx.AsyncClient | None = None


class LLMError(RuntimeError):
    """Error que se muestra al usuario tal cual (en español y sin detalles técnicos)."""


class LLMUnavailable(LLMError):
    """Proveedor saturado o sin conexión: aquí sí se puede probar un respaldo."""


class _Retry(Exception):
    """Reintentar el mismo modelo con otra configuración (p. ej. otro nivel de pensamiento)."""


class _Skip(Exception):
    """Este modelo no sirvió ahora; probar el siguiente."""

    def __init__(self, network: bool = False):
        super().__init__()
        self.network = network


def _get_client() -> httpx.AsyncClient:
    """Un solo cliente para todo el proceso: reutiliza la conexión TLS y evita ~0.3-0.8 s por mensaje."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10, read=60),
            limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=120),
        )
    return _client


def _has_backup() -> bool:
    return bool(config("GROQ_API_KEY", default="").strip())


def _gen_config(model: str) -> dict:
    cfg = {"maxOutputTokens": MAX_OUTPUT_TOKENS, "temperature": 0.6}
    m = _FLASH.match(model)
    if "gemini-2.5" in model:
        cfg["thinkingConfig"] = {"thinkingBudget": 0}
    elif m and float(m.group(1)) >= 3:
        level = _thinking_level.get(model, THINKING_LEVEL)
        if level:
            cfg["thinkingConfig"] = {"thinkingLevel": level}
    return cfg


def _headers() -> dict:
    key = config("GEMINI_API_KEY", default="").strip()
    if not key:
        raise LLMUnavailable("Falta GEMINI_API_KEY en el archivo .env.")
    return {"x-goog-api-key": key, "content-type": "application/json"}


def _rank(name: str):
    m = _FLASH.match(name)
    return (bool(m.group(2)), "preview" in name, -float(m.group(1)), name)


async def _discover(client: httpx.AsyncClient, headers: dict) -> list[str]:
    resp = await client.get(f"{API_BASE}/models", params={"pageSize": 200}, headers=headers)
    resp.raise_for_status()
    found = []
    for m in resp.json().get("models", []):
        name = m.get("name", "").removeprefix("models/")
        if ("streamGenerateContent" in m.get("supportedGenerationMethods", [])
                and _FLASH.match(name) and not any(k in name for k in _SKIP)):
            found.append(name)
    return sorted(found, key=_rank)


async def _candidates(client: httpx.AsyncClient, headers: dict) -> list[str]:
    now = time.monotonic()
    async with _lock:
        if MANUAL_ORDER:
            _catalog["models"] = list(MANUAL_ORDER)  # sin llamada extra a /models
        elif not _catalog["models"] or now - _catalog["at"] > CATALOG_TTL:
            try:
                _catalog["models"] = await _discover(client, headers) or FALLBACK_MODELS
            except (httpx.HTTPError, ValueError):
                _catalog["models"] = _catalog["models"] or FALLBACK_MODELS
            _catalog["at"] = now
    order = list(MANUAL_ORDER) or _catalog["models"]
    ready = [m for m in order if _cooldown.get(m, 0) <= now]
    fast = [m for m in ready if _ttft.get(m, 0) <= FIRST_TOKEN_TIMEOUT * 0.6]
    return fast + [m for m in ready if m not in fast]  # los lentos pasan al final


def _cool(model: str, seconds: float):
    _cooldown[model] = time.monotonic() + seconds


def _http_error(model: str, code: int, detail: str) -> Exception:
    logger.warning("Gemini %s respondió %s: %s", model, code, detail[:400])
    if code == 429:  # saturado o sin cuota: se pasa de una vez al respaldo
        _cool(model, 6 * 3600 if ("PerDay" in detail or "limit: 0" in detail) else 60)
        return LLMUnavailable("Eva está muy solicitada ahora mismo. Inténtalo de nuevo en un minuto.")
    if code == 404:  # modelo retirado: probar el siguiente de Gemini
        _cool(model, 24 * 3600)
        return _Skip()
    if code >= 500:  # saturación de Google: se pasa de una vez al respaldo
        _cool(model, 30)
        return LLMUnavailable("Eva está muy solicitada ahora mismo. Inténtalo de nuevo en un minuto.")
    if code == 400 and "thinking" in detail.lower():
        nxt = _LEVEL_DOWN.get(_thinking_level.get(model, THINKING_LEVEL))
        _thinking_level[model] = nxt
        logger.warning("Gemini %s rechazó el nivel de pensamiento; se reintenta con %s", model, nxt or "ninguno")
        return _Retry()
    if code in (401, 403):
        return LLMError("La clave de Gemini no es válida o no tiene permiso. Revisa tu .env.")
    return LLMError("Eva no pudo procesar esa solicitud. Prueba con otro mensaje o archivo.")


def _blocked(candidate: dict) -> bool:
    return candidate.get("finishReason") in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"}


async def _stream_one(client: httpx.AsyncClient, headers: dict, model: str, body: dict, patient: bool = False):
    t0 = time.monotonic()
    got_text = False
    url = f"{API_BASE}/models/{model}:streamGenerateContent"
    try:
        req = client.build_request("POST", url, params={"alt": "sse"}, json=body, headers=headers)
        # Google a veces retiene las cabeceras HTTP hasta tener el primer token: el plazo debe
        # cubrir también esa espera, no solo las líneas posteriores.
        wait0 = 60 if patient else max(0.5, FIRST_TOKEN_TIMEOUT)
        try:
            resp = await asyncio.wait_for(client.send(req, stream=True), wait0)
        except asyncio.TimeoutError:
            logger.info("Gemini %s no respondió en %.1f s (cabeceras)", model, wait0)
            _cool(model, 60)
            raise _Skip()
        try:
            if resp.status_code != 200:
                detail = (await resp.aread()).decode("utf-8", "ignore")
                raise _http_error(model, resp.status_code, detail)

            lines = resp.aiter_lines()
            while True:
                # Antes del primer texto se exige rapidez, salvo en el último intento (patient) que espera más.
                if got_text or patient:
                    wait = 60
                else:
                    wait = max(0.5, FIRST_TOKEN_TIMEOUT - (time.monotonic() - t0))
                try:
                    line = await asyncio.wait_for(anext(lines), wait)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    _cool(model, 60)
                    raise _Skip()
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except ValueError:
                    continue
                candidates = event.get("candidates") or []
                if not candidates:
                    if event.get("promptFeedback", {}).get("blockReason"):
                        raise LLMError("Eva no puede responder a eso. Probemos con una pregunta de estudio.")
                    continue
                cand = candidates[0]
                for part in cand.get("content", {}).get("parts", []):
                    if part.get("text") and not part.get("thought"):
                        if not got_text:
                            ttft = time.monotonic() - t0
                            _ttft[model] = 0.7 * _ttft.get(model, ttft) + 0.3 * ttft
                            got_text = True
                        yield part["text"]
                if _blocked(cand) and not got_text:
                    raise LLMError("Eva no puede responder a eso. Probemos con una pregunta de estudio.")
        finally:
            await resp.aclose()
    except httpx.HTTPError:
        _cool(model, 20)
        if got_text:
            raise LLMError("La respuesta se interrumpió. Inténtalo de nuevo.")
        raise _Skip(network=True)
    if not got_text:
        _cool(model, 30)
        raise _Skip()


async def stream_reply(conv, history: list[dict]):
    """Genera los trozos de texto de Eva. Lanza LLMError si ningún modelo puede responder."""
    headers = _headers()
    base = {
        "systemInstruction": {"parts": [{"text": build_system(conv)}]},
        "contents": build_contents(conv, history),
        "safetySettings": SAFETY_SETTINGS,
    }
    client = _get_client()
    all_network = True
    models = (await _candidates(client, headers))[:MAX_ATTEMPTS]
    for i, model in enumerate(models):
        # Solo se espera "con paciencia" si no hay respaldo (Groq); con respaldo, el timeout es estricto.
        patient = i == len(models) - 1 and not _has_backup()
        for _ in range(3):  # reintentos del mismo modelo si rechaza el nivel de pensamiento
            sent = False
            try:
                body = {**base, "generationConfig": _gen_config(model)}
                async for chunk in _stream_one(client, headers, model, body, patient=patient):
                    sent = True
                    yield chunk
                logger.info("Gemini respondió con %s", model)
                return
            except _Retry:
                continue
            except _Skip as exc:
                if sent:
                    raise LLMError("La respuesta se interrumpió. Inténtalo de nuevo.")
                all_network = all_network and exc.network
                logger.info("Gemini: %s no disponible, probando el siguiente", model)
                break
    if all_network and models:
        raise LLMUnavailable("No pude conectar con Gemini. Revisa tu conexión a internet.")
    raise LLMUnavailable("Eva está muy solicitada ahora mismo. Inténtalo de nuevo en un minuto.")

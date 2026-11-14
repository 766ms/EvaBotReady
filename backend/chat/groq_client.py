"""Respaldo de chat con Groq (API compatible con OpenAI). Solo texto: los adjuntos ya llegan como texto."""
import asyncio
import json
import logging

import httpx
from decouple import config

from .gemini import LLMUnavailable
from .prompts import build_system

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# llama-3.3-70b-versatile fue retirado por Groq el 16-ago-2026. Sustituto oficial: openai/gpt-oss-120b
# (más calidad) u openai/gpt-oss-20b (más rápido). Lista vigente: https://api.groq.com/openai/v1/models
GROQ_MODEL = config("GROQ_MODEL", default="openai/gpt-oss-120b")
REASONING_EFFORT = config("GROQ_REASONING_EFFORT", default="low")  # los gpt-oss "piensan": en low casi no tardan
MAX_TOKENS = config("MAX_REPLY_TOKENS", default=300, cast=int)  # tope duro; la longitud real la marca el prompt
_client: httpx.AsyncClient | None = None


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
            timeout=httpx.Timeout(10, read=60),
            limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=120),
        )
        _client._custom_loop = current_loop
    return _client


async def stream_reply(conv, history: list[dict]):
    key = config("GROQ_API_KEY", default="").strip()
    if not key:
        raise LLMUnavailable("Eva está muy solicitada ahora mismo. Inténtalo de nuevo en un minuto.")
    if conv.image_b64:
        logger.info("Groq no analiza imágenes: se responde sin la imagen adjunta")
    messages = [{"role": "system", "content": build_system(conv)}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    body = {"model": GROQ_MODEL, "messages": messages, "stream": True,
            "temperature": 0.6, "max_tokens": MAX_TOKENS}
    if GROQ_MODEL.startswith("openai/gpt-oss") and REASONING_EFFORT:
        body["reasoning_effort"] = REASONING_EFFORT
        body["max_tokens"] = MAX_TOKENS + 600  # el razonamiento también consume tokens de salida
    try:
        client = _get_client()
        async with client.stream("POST", GROQ_URL, json=body,
                                 headers={"Authorization": f"Bearer {key}"}) as resp:
            if resp.status_code != 200:
                detail = (await resp.aread()).decode("utf-8", "ignore")
                logger.warning("Groq respondió %s: %s", resp.status_code, detail[:400])
                raise LLMUnavailable("Eva está muy solicitada ahora mismo. Inténtalo de nuevo en un minuto.")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                choices = event.get("choices") or [{}]
                text = choices[0].get("delta", {}).get("content")
                if text:
                    yield text
    except httpx.HTTPError:
        raise LLMUnavailable("No pude conectar con el respaldo de Eva. Revisa tu conexión a internet.")

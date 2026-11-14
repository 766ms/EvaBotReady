"""Orquestador de chat: Gemini primero; si no da la primera palabra a tiempo, Groq entra en carrera.

- Gemini arranca solo. Si en HEDGE_AFTER segundos no hay texto, se lanza Groq en paralelo.
- Gana quien emita primero; el otro se cancela. Si Gemini falla antes, Groq arranca de inmediato.
- Con imagen adjunta no se compite (Groq no ve imágenes): Gemini va solo y Groq queda de respaldo.
"""
import asyncio
import logging
import time

from decouple import config

from . import gemini, groq_client
from .gemini import LLMError, LLMUnavailable

logger = logging.getLogger(__name__)

__all__ = ["stream_reply", "LLMError"]

HEDGE_AFTER = config("HEDGE_AFTER", default=1.5, cast=float)  # s sin texto de Gemini antes de lanzar Groq


async def _timed(name: str, agen, t0: float):
    """Deja en la terminal cuánto tarda la primera palabra y la respuesta completa."""
    first = True
    async for chunk in agen:
        if first:
            logger.info("%s: primera palabra a los %.2f s", name, time.monotonic() - t0)
            first = False
        yield chunk
    logger.info("%s: respuesta completa en %.2f s", name, time.monotonic() - t0)


async def _anext(it):
    return await it.__anext__()


async def _cancel(tasks, iters):
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    for it in iters:
        try:
            await it.aclose()
        except Exception:  # noqa: BLE001 - limpieza best-effort
            pass


async def _sequential(conv, history, t0):
    """Gemini solo, con Groq de respaldo si Gemini está saturado o sin conexión."""
    sent = False
    try:
        async for chunk in _timed("Gemini", gemini.stream_reply(conv, history), t0):
            sent = True
            yield chunk
        return
    except LLMUnavailable as exc:
        if sent:  # ya se mostró texto: no se cambia de proveedor a mitad de respuesta
            raise LLMError(str(exc)) from exc
        logger.warning("Gemini saturado o sin conexión (%s). Usando Groq.", exc)
    async for chunk in _timed("Groq", groq_client.stream_reply(conv, history), time.monotonic()):
        yield chunk


async def _race(conv, history, t0):
    live = {}  # tarea -> (nombre, iterador)

    def start(name, agen):
        it = _timed(name, agen, t0).__aiter__()
        live[asyncio.ensure_future(_anext(it))] = (name, it)

    start("Gemini", gemini.stream_reply(conv, history))
    groq_started = False
    last_exc: Exception | None = None
    winner = None
    try:
        while winner is None:
            timeout = None
            if not groq_started:
                timeout = max(0.0, HEDGE_AFTER - (time.monotonic() - t0))
            done, _ = await asyncio.wait(set(live), timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if not done:  # Gemini no dio texto a tiempo: entra Groq
                logger.info("Gemini sin texto tras %.1f s: se lanza Groq en paralelo", HEDGE_AFTER)
                start("Groq", groq_client.stream_reply(conv, history))
                groq_started = True
                continue
            for task in done:
                name, it = live.pop(task)
                try:
                    first = task.result()
                except StopAsyncIteration:
                    continue
                except LLMUnavailable as exc:  # saturado / sin conexión: el otro proveedor puede cubrirlo
                    last_exc = exc
                    logger.warning("%s falló antes de responder: %s", name, exc)
                    continue
                # Cualquier otro LLMError (p. ej. bloqueo de seguridad de Gemini) NO se reenvía a Groq:
                # el finally cancela lo que esté en curso y el error llega al usuario.
                winner = (name, it, first)
                break
            if winner is None and not live:
                if not groq_started:  # Gemini murió sin texto: Groq de inmediato
                    start("Groq", groq_client.stream_reply(conv, history))
                    groq_started = True
                else:
                    raise last_exc or LLMUnavailable("Eva está muy solicitada ahora mismo. Inténtalo de nuevo en un minuto.")
        name, it, first = winner
        await _cancel(list(live), [v[1] for v in live.values()])
        live.clear()
        logger.info("Responde %s", name)
        yield first
        async for chunk in it:
            yield chunk
    finally:  # también si el usuario cierra la página a mitad de respuesta
        if live:
            await _cancel(list(live), [v[1] for v in live.values()])
        if winner:
            try:
                await winner[1].aclose()
            except Exception:  # noqa: BLE001
                pass


async def stream_reply(conv, history: list[dict]):
    t0 = time.monotonic()
    if groq_client.available() and not conv.image_b64:
        gen = _race(conv, history, t0)
    else:
        gen = _sequential(conv, history, t0)
    async for chunk in gen:
        yield chunk

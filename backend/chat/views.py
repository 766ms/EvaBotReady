import asyncio
import json
import logging
import random
from datetime import timedelta

from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

import httpx

from . import attachments, guardrails, live, llm, transcription, tts
from .models import Conversation, Message
from .ratelimit import ratelimit

HISTORY_LIMIT = 12  # últimos mensajes que Eva recuerda en la sesión
MAX_MESSAGES_PER_CONVERSATION = 400  # tope para que una sesión no pueda llenar la base de datos
CONVERSATION_TTL = timedelta(hours=12)
MAX_AUDIO_BYTES = 5 * 1024 * 1024  # ~60 s de audio comprimido
LIVE_FILE_CHARS = 12_000  # extracto del archivo que se le pasa a Eva si se añade en plena llamada
LIVE_SAVE_TURNS = 40      # máximo de turnos hablados que se guardan al pasar del live al chat
logger = logging.getLogger(__name__)


def _sse(data) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stream(gen):
    resp = StreamingHttpResponse(gen, content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


async def _current(request):
    cid = await request.session.aget("cid")
    return await Conversation.objects.filter(pk=cid).afirst() if cid else None


async def _drop_current(request):
    cid = await request.session.aget("cid")
    if cid:
        await Conversation.objects.filter(pk=cid).adelete()
        await request.session.aset("cid", None)


async def _maybe_purge():
    # Privacidad: se borran las conversaciones viejas; probabilístico para no ralentizar cada carga
    if random.random() < 0.1:
        await Conversation.objects.filter(created_at__lt=timezone.now() - CONVERSATION_TTL).adelete()


async def _conversation_full(conv) -> bool:
    return await Message.objects.filter(conversation=conv).acount() >= MAX_MESSAGES_PER_CONVERSATION


def _too_big(upload) -> bool:
    # Django no limita el tamaño de los archivos subidos (DATA_UPLOAD_MAX_MEMORY_SIZE no los cuenta):
    # se revisa el tamaño declarado ANTES de leerlo a memoria.
    return upload.size > attachments.MAX_FILE_BYTES


TOO_BIG = {"error": "El archivo supera el límite de 8 MB."}


@require_GET
async def index(request):
    # Privacidad: recargar = chat nuevo
    await _drop_current(request)
    await _maybe_purge()
    return render(request, "chat/index.html")


@require_GET
@ratelimit("csrf", 60)
@ensure_csrf_cookie
async def csrf(request):
    """Para el frontend de React: deja la cookie `csrftoken` y empieza un chat nuevo (como recargar la plantilla)."""
    await _drop_current(request)
    await _maybe_purge()  # la app de React nunca pasa por index(): sin esto las conversaciones viejas no se borrarían
    return JsonResponse({"ok": True})


@require_POST
@ratelimit("setup", 20)
async def setup(request):
    subject = request.POST.get("subject", "").strip()[:120]
    topic = request.POST.get("topic", "").strip()[:120]
    ctx, file_name = {}, ""
    upload = request.FILES.get("file")
    if upload:
        if _too_big(upload):
            return JsonResponse(TOO_BIG, status=413)
        file_name = upload.name[:255]
        data = await asyncio.to_thread(upload.read)
        try:
            ctx = await asyncio.to_thread(attachments.extract_attachment, upload.name, data)
        except attachments.AttachmentError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
    await _drop_current(request)
    conv = await Conversation.objects.acreate(
        subject=subject, topic=topic, file_name=file_name,
        context_text=ctx.get("text", ""), image_b64=ctx.get("data", ""), image_type=ctx.get("media_type", ""),
    )
    await request.session.aset("cid", conv.pk)
    return JsonResponse({"ok": True})


@require_POST
@ratelimit("upload", 15)
async def upload_file(request):
    upload = request.FILES.get("file")
    if not upload:
        return JsonResponse({"error": "No se recibió ningún archivo."}, status=400)
    if _too_big(upload):
        return JsonResponse(TOO_BIG, status=413)
    file_name = upload.name[:255]
    data = await asyncio.to_thread(upload.read)
    try:
        ctx = await asyncio.to_thread(attachments.extract_attachment, upload.name, data)
    except attachments.AttachmentError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    conv = await _current(request)
    if conv is None:
        conv = await Conversation.objects.acreate(
            file_name=file_name,
            context_text=ctx.get("text", ""),
            image_b64=ctx.get("data", ""),
            image_type=ctx.get("media_type", ""),
        )
        await request.session.aset("cid", conv.pk)
    else:
        conv.file_name = file_name
        conv.context_text = ctx.get("text", "")
        conv.image_b64 = ctx.get("data", "")
        conv.image_type = ctx.get("media_type", "")
        await conv.asave(update_fields=["file_name", "context_text", "image_b64", "image_type"])

    # `text`: extracto para que el modo live pueda usar un archivo añadido en plena llamada
    return JsonResponse({"ok": True, "file_name": file_name, "kind": ctx.get("kind"),
                         "text": ctx.get("text", "")[:LIVE_FILE_CHARS]})


@require_POST
@ratelimit("chat", 30)
async def chat(request):
    try:
        message = json.loads(request.body)["message"].strip()
    except (ValueError, KeyError, AttributeError):
        return JsonResponse({"error": "Mensaje inválido."}, status=400)
    if not message or len(message) > 4000:
        return JsonResponse({"error": "El mensaje está vacío o es demasiado largo."}, status=400)

    category = guardrails.classify(message)
    if category:  # se corta aquí: no se guarda ni se envía al modelo
        async def refusal():
            yield _sse({"t": guardrails.refusal(category, message)})
            yield "data: [DONE]\n\n"
        return _stream(refusal())

    conv = await _current(request)
    if conv is None:
        conv = await Conversation.objects.acreate()
        await request.session.aset("cid", conv.pk)
    elif await _conversation_full(conv):
        return JsonResponse({"error": "Esta conversación ya es muy larga. Empieza un chat nuevo."}, status=400)
    await Message.objects.acreate(conversation=conv, role="user", content=message)

    async def events():
        rows = [m async for m in Message.objects.filter(conversation=conv).order_by("-id")[:HISTORY_LIMIT]]
        history = [{"role": m.role, "content": m.content} for m in reversed(rows)]
        parts = []
        try:
            async for chunk in llm.stream_reply(conv, history):
                parts.append(chunk)
                yield _sse({"t": chunk})
        except llm.LLMError as exc:
            yield _sse({"error": str(exc)})
               # Si la conversación se borró mientras respondía (recargar o "Nuevo chat"), no se guarda nada.
        if parts and await Conversation.objects.filter(pk=conv.pk).aexists():
            await Message.objects.acreate(conversation=conv, role="assistant", content="".join(parts))
        yield "data: [DONE]\n\n"

    return _stream(events())


@require_POST
async def reset(request):
    await _drop_current(request)
    return JsonResponse({"ok": True})


@require_POST
@ratelimit("transcribe", 15)
async def transcribe(request):
    audio = request.body
    if not audio:
        return JsonResponse({"error": "No recibí audio."}, status=400)
    if len(audio) > MAX_AUDIO_BYTES:
        return JsonResponse({"error": "La grabación es demasiado larga."}, status=413)
    try:
        text = await transcription.transcribe(audio, request.content_type)
    except transcription.TranscriptionError:
        logger.exception("Dictado no disponible")
        return JsonResponse({"error": "El dictado no está disponible ahora mismo. Escribe tu pregunta."}, status=503)
    except ImportError:
        return JsonResponse({"error": "El dictado no está instalado. Ejecuta: pip install faster-whisper"}, status=503)
    except Exception:
        logger.exception("Error al transcribir el audio")
        return JsonResponse({"error": "No pude transcribir el audio. Intenta de nuevo."}, status=500)
    return JsonResponse({"text": text})


@require_POST
@ratelimit("tts", 60)  # una respuesta larga se lee en varios trozos de 190 caracteres
async def speak(request):
    """Lee en voz alta un trozo de la respuesta de Eva (Groq TTS). El navegador pide los trozos uno a uno."""
    try:
        text = " ".join(str(json.loads(request.body)["text"]).split())
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"error": "Texto inválido."}, status=400)
    if not text or len(text) > tts.MAX_CHARS:
        return JsonResponse({"error": f"El texto debe tener entre 1 y {tts.MAX_CHARS} caracteres."}, status=400)
    if not tts.available():
        return JsonResponse({"error": "La voz no está disponible ahora mismo."}, status=503)
    try:
        audio = await tts.synthesize(text)
    except tts.TTSError as exc:
        logger.warning("Voz no disponible: %s", exc)
        return JsonResponse({"error": "No pude generar el audio. Intenta de nuevo."}, status=503)
    resp = HttpResponse(audio, content_type="audio/wav")
    resp["Cache-Control"] = "no-store"
    return resp


@require_POST
@ratelimit("live_token", 6)
async def live_token(request):
    """Entrega al navegador un token de un solo uso y la configuración del modo live."""
    conv = await _current(request)
    history = []
    if conv is not None:  # Eva sigue hablando donde quedó el chat de texto
        rows = [m async for m in Message.objects.filter(conversation=conv).order_by("-id")[:HISTORY_LIMIT]]
        history = [{"role": m.role, "content": m.content} for m in reversed(rows)]
    setup = live.build_setup(conv, history)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5)) as client:
            token = await live.create_token(client, setup)  # la configuración queda sellada en el token
    except live.LiveError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    return JsonResponse({
        "token": token,
        "ws_url": live.LIVE_WS_URL,
        "setup": setup,
        "patterns": guardrails.js_patterns(),
        "closed": guardrails.LIVE_CLOSED,
        "closed_help": guardrails.LIVE_CLOSED_HELP,
    })


@require_POST
@ratelimit("live_save", 20)
async def live_save(request):
    """Guarda lo hablado en el modo live para poder seguir en el chat de texto con el mismo contexto.

    Solo se aceptan turnos de usuario y de Eva. Lo del estudiante pasa por el mismo filtro local
    que el chat; el resto se recorta a un tamaño razonable.
    """
    try:
        turns = json.loads(request.body)["turns"]
        if not isinstance(turns, list):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"error": "Datos inválidos."}, status=400)

    clean = []
    for t in turns[-LIVE_SAVE_TURNS:]:
        if not isinstance(t, dict):
            continue
        role, content = t.get("role"), str(t.get("content", "")).strip()[:4000]
        if role not in ("user", "assistant") or not content:
            continue
        if role == "user" and guardrails.classify(content):
            continue
        clean.append((role, content))
    if not clean:
        return JsonResponse({"ok": True, "saved": 0})

    conv = await _current(request)
    if conv is None:
        conv = await Conversation.objects.acreate()
        await request.session.aset("cid", conv.pk)
    elif await _conversation_full(conv):
        return JsonResponse({"ok": True, "saved": 0})
    await Message.objects.abulk_create([Message(conversation=conv, role=r, content=c) for r, c in clean])
    return JsonResponse({"ok": True, "saved": len(clean)})

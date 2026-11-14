"""Filtro local de entrada: primera barrera, barata y determinista. Español e inglés.

Capas de seguridad (de fuera hacia dentro):
  1. Este filtro: bloquea antes de llamar al modelo (no se guarda ni se envía).
  2. System Prompt: reglas de comportamiento para el modelo.
  3. safetySettings de Gemini: filtro propio de Google sobre la respuesta.
"""
import re
import unicodedata

# Autolesiones: solo intención en primera persona (un tema educativo como "causas del suicidio" NO se bloquea).
SELF_HARM = re.compile(
    r"\b("
    r"quiero\s+(morirme|matarme|suicidarme|dejar\s+de\s+existir)|"
    r"me\s+quiero\s+(morir|matar)|"
    r"voy\s+a\s+(matarme|suicidarme|quitarme\s+la\s+vida)|"
    r"me\s+voy\s+a\s+(matar|suicidar)|"
    r"(como|quiero)\s+(me\s+)?suicid\w*|"
    r"acabar\s+con\s+mi\s+vida|quitarme\s+la\s+vida|"
    r"cortarme\s+(las\s+venas|me)|hacerme\s+dano|autolesionarme"
    r")\b"
)

# Groserías, insultos, obscenidades (texto ya normalizado: minúsculas y sin tildes).
ABUSE = re.compile(
    r"\b("
    r"hijueputa\w*|hijoputa\w*|hijo\s+de\s+(la\s+)?puta|hpt[ao]\w*|hdlgp|hdp|malparid[oa]s?|gonorrea\w*|"
    r"mierda\w*|carajo\w*|joder\w*|puta\w*|puto\w*|pendej\w*|cabron\w*|culer\w*|verga\w*|"
    r"marica\w*|maricon\w*|chingad\w*|chingar\w*|idiota\w*|imbecil\w*|estupid[oa]s?|"
    r"porn\w*|xxx"
    r")\b"
)

# Violencia explícita dirigida a personas (no temas históricos ni científicos).
VIOLENCE = re.compile(
    r"\b("
    r"voy\s+a\s+matar\w*|te\s+voy\s+a\s+(matar|golpear|pegar|violar)|"
    r"violar\s+a\s+(una|un|mi|tu|alguien)|torturar\s+a\s+(alguien|una|un|mi)|"
    r"hacer\s+una\s+bomba|fabricar\s+(una\s+|un\s+)?(bomba|explosivo|arma)"
    r")\b"
)

# ---------- Inglés ----------
# Autolesiones en primera persona (temas educativos como "causes of suicide" NO se bloquean).
SELF_HARM_EN = re.compile(
    r"\b("
    r"i\s+(?:want|wanna|need)\s+to\s+(?:die|kill\s+myself|end\s+(?:it\s+all|my\s+life)|commit\s+suicide)|"
    r"i\s*(?:am|'?m)\s+(?:going\s+to|gonna)\s+(?:kill\s+myself|commit\s+suicide|end\s+(?:it\s+all|my\s+life)|hurt\s+myself)|"
    r"i\s*(?:will|'ll)\s+(?:kill\s+myself|end\s+my\s+life)|"
    r"kill\s+myself|end\s+my\s+life|take\s+my\s+(?:own\s+)?life|"
    r"how\s+(?:do\s+i|can\s+i|to)\s+commit\s+suicide|"
    r"(?:want\s+to|wanna|going\s+to|gonna)\s+(?:hurt|harm|cut)\s+myself|"
    r"i\s+(?:cut|hurt|harm)\s+myself"
    r")\b"
)

# Groserías e insultos. Se evitan palabras ambiguas (dick, ass, bastard, cock...) para no bloquear
# "Moby Dick", "William the Bastard" o biología. "moron" no usa \w* para no bloquear "Moroni".
ABUSE_EN = re.compile(
    r"\b("
    r"fuck\w*|motherfuck\w*|bullshit\w*|shit(?:s|ty|head)?|bitch(?:es|y)?|asshole\w*|dickhead\w*|dumbass\w*|"
    r"cunt\w*|whore\w*|slut\w*|wanker\w*|twat\w*|faggot\w*|nigger\w*|nigga\w*|retarded|"
    r"idiot\w*|moron(?:s|ic)?|porn\w*|"
    r"you\s*(?:are|'re|re)\s+(?:an?\s+)?(?:stupid|dumb|useless|worthless|pathetic)|"
    r"shut\s+up|screw\s+you|go\s+to\s+hell"
    r")\b"
)

# Violencia explícita dirigida a personas.
VIOLENCE_EN = re.compile(
    r"\b("
    r"i\s*(?:am|'?m)\s+(?:going\s+to|gonna)\s+(?:kill|shoot|stab|beat|rape|hurt)\s+(?:you|him|her|them|someone|somebody|everyone|everybody)|"
    r"i\s*(?:will|'ll)\s+(?:kill|shoot|stab|beat|rape|hurt)\s+(?:you|him|her|them|someone|somebody)|"
    r"i\s+(?:want|wanna)\s+to\s+(?:kill|shoot|stab|rape|hurt)\s+(?:you|him|her|them|someone|somebody|everyone|everybody)|"
    r"rape\s+(?:a|an|my|your|her|him|someone|somebody)|torture\s+(?:someone|somebody|a|an|my)|"
    r"(?:make|build|create|construct)\s+(?:a|an)\s+(?:bomb|explosive|weapon)|"
    r"how\s+to\s+(?:make|build)\s+(?:a\s+)?(?:bomb|explosives?)"
    r")\b"
)

# Palabras muy frecuentes para adivinar el idioma del mensaje (solo sirve para elegir el idioma del aviso).
_EN_WORDS = {"the", "is", "are", "what", "how", "why", "you", "your", "my", "this", "that", "with", "for", "and",
             "of", "to", "can", "do", "does", "please", "i", "it", "was", "have", "has", "not", "from", "about",
             "when", "where", "which", "who", "im", "i'm", "am", "want", "going"}
_ES_WORDS = {"el", "la", "los", "las", "es", "son", "que", "como", "por", "para", "de", "un", "una", "y", "en",
             "mi", "te", "tu", "yo", "con", "se", "lo", "al", "del", "su", "pero", "esto", "eso", "muy", "porque",
             "cuando", "donde", "quien", "cual", "quiero", "voy", "eres"}

REFUSAL_EN = {
    "self_harm": (
        "I'm sorry you're going through something so hard. You don't have to carry it alone: talk to someone "
        "you trust right now or call Línea 106 (free psychological support, Colombia). If it's an emergency, call 123. "
        "When you feel calmer, we can keep studying together."
    ),
    "violence": (
        "I can't help with that. If something worries you or you feel in danger, talk to someone you trust "
        "or call 123. Whenever you want, we can get back to studying."
    ),
    "abuse": (
        "I'd rather we keep the language respectful. Tell me your study question and I'll gladly help."
    ),
}

REFUSAL = {
    "self_harm": (
        "Lamento que estés pasando por algo tan difícil. No tienes que cargarlo solo: habla ahora con alguien "
        "de confianza o llama a la Línea 106 (orientación psicológica gratuita, Colombia). Si es una emergencia, llama al 123. "
        "Cuando te sientas más tranquilo, podemos seguir estudiando juntos."
    ),
    "violence": (
        "No puedo ayudarte con eso. Si algo te preocupa o te sientes en peligro, habla con alguien de "
        "confianza o llama al 123. Cuando quieras, retomamos el estudio."
    ),
    "abuse": (
        "Prefiero que sigamos con un lenguaje respetuoso. Cuéntame tu duda de estudio y te ayudo con gusto."
    ),
}


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("\u2019", "'"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


_PATTERNS = (
    ("self_harm", SELF_HARM, SELF_HARM_EN),
    ("violence", VIOLENCE, VIOLENCE_EN),
    ("abuse", ABUSE, ABUSE_EN),
)


def classify(text: str) -> str | None:
    """Devuelve la categoría bloqueada ('self_harm', 'violence', 'abuse') o None si el texto es seguro."""
    norm = _normalize(text)
    for category, es_rx, en_rx in _PATTERNS:
        if es_rx.search(norm) or en_rx.search(norm):
            return category
    return None


def guess_language(text: str) -> str:
    """'en' o 'es' según las palabras más comunes del mensaje; en caso de empate, 'es'."""
    words = re.findall(r"[a-z']+", _normalize(text))
    en = sum(w in _EN_WORDS for w in words)
    es = sum(w in _ES_WORDS for w in words)
    return "en" if en > es else "es"


def refusal(category: str, text: str = "") -> str:
    """Aviso de bloqueo en el idioma del estudiante (español o inglés)."""
    norm = _normalize(text)
    _, es_rx, en_rx = next(p for p in _PATTERNS if p[0] == category)
    es_hit, en_hit = bool(es_rx.search(norm)), bool(en_rx.search(norm))
    if en_hit and not es_hit:
        lang = "en"
    elif es_hit and not en_hit:
        lang = "es"
    else:
        lang = guess_language(text)
    return (REFUSAL_EN if lang == "en" else REFUSAL)[category]


def js_patterns() -> dict:
    """Mismas expresiones regulares para el navegador (modo live), así hay una sola fuente de verdad.

    El navegador debe normalizar igual: minúsculas, NFKD y sin tildes (ver normalize() en index.html).
    """
    return {cat: [es_rx.pattern, en_rx.pattern] for cat, es_rx, en_rx in _PATTERNS}


# Mensajes que muestra el modo live al cerrar la sesión.
LIVE_CLOSED = "Eva finalizó la sesión del modo live por seguridad."
LIVE_CLOSED_HELP = (
    " Si estás pasando por un momento difícil, puedes llamar gratis a la Línea 106 "
    "(orientación psicológica y primeros auxilios emocionales). Si es una emergencia, llama al 123."
)

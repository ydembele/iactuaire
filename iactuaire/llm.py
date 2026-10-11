"""Accès aux modèles d'IA : Claude (Anthropic) ou ChatGPT (OpenAI), avec la clé de l'utilisateur.

Le reste du code n'appelle que les fonctions de ce module (`ask`, `ask_json`, `web_search`,
`ask_with_images`) : il ignore quel fournisseur est utilisé.
"""
import json
import os
import re
import threading

from . import config, runtime


class MissingAPIKey(RuntimeError):
    pass


_clients: dict = {}
_lock = threading.Lock()


def _key(rt: runtime.Runtime) -> str:
    key = (rt.api_key or "").strip().strip('"').strip("'")
    if not key and config.LOCAL and rt.provider == "anthropic":   # jamais en public : chacun sa clé
        key = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
    if not key and config.LOCAL and rt.provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip().strip('"').strip("'")
    return key


def has_key() -> bool:
    rt = runtime.get()
    k = _key(rt)
    return bool(k) and k.startswith(runtime.PROVIDERS[rt.provider]["cle"]) and "..." not in k


def client(rt: runtime.Runtime | None = None):
    rt = rt or runtime.get()
    key = _key(rt)
    if not key:
        raise MissingAPIKey(f"Renseignez votre clé API {runtime.PROVIDERS[rt.provider]['nom']} dans les paramètres.")
    with _lock:
        c = _clients.get((rt.provider, key))
        if c is None:
            if rt.provider == "openai":
                import openai
                c = openai.OpenAI(api_key=key, timeout=900, max_retries=3)
            else:
                import anthropic
                c = anthropic.Anthropic(api_key=key, max_retries=3)
            _clients[(rt.provider, key)] = c
    return c


def _is_openai() -> bool:
    return runtime.get().provider == "openai"


def _flat(system) -> str:
    return system if isinstance(system, str) else "\n\n".join(b["text"] for b in system)


def text_of(response) -> str:
    return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")


# --------------------------------------------------------------------------- texte

def ask(model: str, system, user: str, max_tokens: int = 4000) -> str:
    """`system` : chaîne, ou liste de blocs (contexte mis en cache chez Claude ; automatique chez OpenAI).
    Une réponse coupée faute de place est relancée avec une limite plus large (jusqu'à 32 000 jetons)."""
    if _is_openai():
        budget = max_tokens * 2   # les modèles OpenAI à raisonnement comptent aussi leur réflexion
        while True:
            r = client().responses.create(model=model, instructions=_flat(system), input=user,
                                          max_output_tokens=budget)
            reason = getattr(getattr(r, "incomplete_details", None), "reason", None)
            if getattr(r, "status", "completed") != "incomplete" or reason != "max_output_tokens":
                return r.output_text or ""
            if budget >= 64000:
                raise RuntimeError(f"Réponse tronquée même avec {budget} jetons.")
            budget = min(64000, budget * 3)
    while True:
        with client().messages.stream(model=model, max_tokens=max_tokens, system=system,
                                      messages=[{"role": "user", "content": user}]) as stream:
            r = stream.get_final_message()
        if r.stop_reason != "max_tokens":
            return text_of(r)
        if max_tokens >= 32000:
            raise RuntimeError(f"Réponse tronquée même avec max_tokens={max_tokens}.")
        max_tokens = min(32000, max_tokens * 3)


def cached_system(instructions: str, context: str) -> list[dict]:
    """Instructions + gros contexte (les sources), mis en cache : les appels suivants qui
    réutilisent le même contexte coûtent beaucoup moins cher."""
    return [
        {"type": "text", "text": instructions},
        {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
    ]


def parse_json(text: str):
    """Extrait le premier objet/tableau JSON d'une réponse (tolère ```json ...```)."""
    text = re.sub(r"```(?:json)?", "", text)
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError(f"Pas de JSON dans la réponse : {text[:300]}")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start: end + 1])


JSON_RULE = "\nRéponds UNIQUEMENT avec du JSON valide, sans texte autour."


def ask_json(model: str, system, user: str, max_tokens: int = 4000):
    if isinstance(system, str):
        system = system + JSON_RULE
    else:
        system = [{**system[0], "text": system[0]["text"] + JSON_RULE}, *system[1:]]
    out = ask(model, system, user, max_tokens)
    try:
        return parse_json(out)
    except (ValueError, json.JSONDecodeError):
        fixed = ask(model, "Corrige ce texte pour qu'il soit du JSON valide. Réponds uniquement en JSON.",
                    out, max_tokens)
        return parse_json(fixed)


# --------------------------------------------------------------------------- recherche web

def web_search(system: str, user: str, domains: list[str] | None, max_uses: int = 6,
               log=print) -> tuple[str, dict[str, str]]:
    """Recherche web pilotée par le modèle, limitée aux `domains`.
    Renvoie (réponse finale du modèle, {url consultée: titre}). Seules ces URL font foi."""
    model = config.MODEL_SMART
    seen: dict[str, str] = {}
    if _is_openai():
        tool = {"type": "web_search"}
        if domains:
            tool["filters"] = {"allowed_domains": domains}
        r = client().responses.create(model=model, instructions=system, input=user, tools=[tool],
                                      include=["web_search_call.action.sources"])
        for item in r.output:
            if item.type == "web_search_call":
                action = getattr(item, "action", None)
                if getattr(action, "type", "") == "search" and getattr(action, "query", None):
                    log(f"🔎 Recherche : {action.query}")
                for src in getattr(action, "sources", None) or []:
                    url = getattr(src, "url", None)
                    if url:
                        seen.setdefault(url, getattr(src, "title", "") or "")
            elif item.type == "message":
                for part in item.content or []:
                    for ann in getattr(part, "annotations", None) or []:
                        if getattr(ann, "type", "") == "url_citation":
                            seen[ann.url] = getattr(ann, "title", "") or seen.get(ann.url, "")
        return r.output_text or "", seen

    tool = {"type": config.WEB_SEARCH_TOOL, "name": "web_search", "max_uses": max_uses,
            "allowed_callers": ["direct"]}
    if domains:
        tool["allowed_domains"] = domains
    messages = [{"role": "user", "content": user}]
    r = None
    for _ in range(4):   # gère les pauses (stop_reason == "pause_turn")
        r = client().messages.create(model=model, max_tokens=4000, system=system, messages=messages, tools=[tool])
        for b in r.content:
            if b.type == "server_tool_use":
                log(f"🔎 Recherche : {b.input.get('query')}")
            if b.type == "web_search_tool_result" and isinstance(b.content, list):
                for res in b.content:
                    seen.setdefault(res.url, res.title)
        if r.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": r.content})
    return text_of(r), seen


# --------------------------------------------------------------------------- images

def ask_with_images(system: str, parts: list[tuple[str, str]], max_tokens: int = 2000) -> str:
    """`parts` : [("text", "...") | ("image", png_en_base64), ...]."""
    model = config.MODEL_SMART
    if _is_openai():
        content = [{"type": "input_text", "text": v} if k == "text"
                   else {"type": "input_image", "image_url": f"data:image/png;base64,{v}"} for k, v in parts]
        r = client().responses.create(model=model, instructions=system, max_output_tokens=max_tokens * 2,
                                      input=[{"role": "user", "content": content}])
        return r.output_text or ""
    content = [{"type": "text", "text": v} if k == "text"
               else {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": v}}
               for k, v in parts]
    r = client().messages.create(model=model, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": content}])
    return text_of(r)


# --------------------------------------------------------------------------- clé et modèles

_EXCLUDE = re.compile(r"audio|realtime|tts|transcribe|image|embedding|moderation|search|whisper|dall|davinci|"
                      r"babbage|instruct|codex|computer|preview|chatgpt", re.I)


def list_models(provider: str, api_key: str) -> list[str]:
    """Modèles de texte accessibles avec cette clé (lève une exception si la clé est refusée)."""
    c = client(runtime.Runtime(provider=provider, api_key=api_key, out_dir=config.OUTPUT_BASE))
    if provider == "openai":
        ids = [m.id for m in c.models.list() if m.id.startswith(("gpt-", "o")) and not _EXCLUDE.search(m.id)]
        return sorted(set(ids), reverse=True)
    return [m.id for m in c.models.list(limit=100)]


def default_models(provider: str, models: list[str]) -> tuple[str, str]:
    """Choix par défaut : un modèle fort pour rédiger, un modèle rapide pour lire."""
    d = runtime.DEFAULT_MODELS[provider]
    if not models:
        return d["smart"], d["fast"]
    pick = lambda pred, fallback: next((m for m in models if pred(m)), fallback)
    if provider == "openai":
        smart = d["smart"] if d["smart"] in models else pick(
            lambda m: m.startswith("gpt-") and not re.search("mini|nano", m), models[0])
        fast = pick(lambda m: m.startswith("gpt-") and "mini" in m, smart)
    else:
        smart = d["smart"] if d["smart"] in models else pick(lambda m: "sonnet" in m, models[0])
        fast = d["fast"] if d["fast"] in models else pick(lambda m: "haiku" in m, smart)
    return smart, fast

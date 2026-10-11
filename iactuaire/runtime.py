"""Contexte d'exécution propre à chaque utilisateur.

Dans l'application publique, plusieurs personnes utilisent le même serveur en même temps.
Leur clé API, leurs modèles et leurs fichiers ne doivent jamais se mélanger : tout ce qui
est propre à un utilisateur vit dans un `Runtime`, activé au début de chaque exécution de sa
session (variable de contexte, donc invisible des autres sessions).
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from . import config

PROVIDERS = {
    "anthropic": {"nom": "Claude (Anthropic)", "cle": "sk-ant-",
                  "obtenir": "https://console.anthropic.com/settings/keys"},
    "openai": {"nom": "ChatGPT (OpenAI)", "cle": "sk-",
               "obtenir": "https://platform.openai.com/api-keys"},
}

# Modèles proposés tant que la liste n'a pas été lue avec la clé de l'utilisateur
DEFAULT_MODELS = {
    "anthropic": {"smart": "claude-sonnet-5-5", "fast": "claude-haiku-5-5"},
    "openai": {"smart": "gpt-5.5", "fast": "gpt-5.5-mini"},
}


@dataclass
class Runtime:
    provider: str = "anthropic"
    api_key: str = ""
    model_smart: str = DEFAULT_MODELS["anthropic"]["smart"]
    model_fast: str = DEFAULT_MODELS["anthropic"]["fast"]
    min_relevance: int = 6
    out_dir: Path = field(default_factory=lambda: config.OUTPUT_BASE)
    auteur: str = ""

    def __post_init__(self):
        Path(self.out_dir).mkdir(parents=True, exist_ok=True)


_CURRENT: ContextVar["Runtime | None"] = ContextVar("iactuaire_runtime", default=None)
_FALLBACK = None   # ligne de commande et usage local uniquement


def activate(rt: Runtime) -> Runtime:
    _CURRENT.set(rt)
    return rt


def get() -> Runtime:
    rt = _CURRENT.get()
    if rt is not None:
        return rt
    global _FALLBACK
    if _FALLBACK is None:
        _FALLBACK = Runtime()
    return _FALLBACK

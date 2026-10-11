"""Paramètres techniques.

Les réglages propres à un utilisateur (clé API, modèles, seuil, dossier de sortie) ne sont PAS
ici mais dans `runtime.py` : `config.MODEL_SMART`, `config.MODEL_FAST`, `config.MIN_RELEVANCE`
et `config.OUTPUT_DIR` renvoient la valeur de l'utilisateur courant.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
# .env à la racine du projet (usage local). Sous Windows, l'Explorateur crée parfois « .env.txt ».
for _env in (ROOT / ".env", ROOT / ".env.txt"):
    if _env.exists():
        load_dotenv(_env, override=True)
        break

# Usage local (ton ordinateur) : clé lue dans .env, réglages enregistrés, bibliothèque complète,
# équipe d'experts. Sans IACTUAIRE_LOCAL=1 (déploiement public), rien de tout cela.
LOCAL = os.getenv("IACTUAIRE_LOCAL", "").strip() == "1"

DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
PDF_DIR = DATA_DIR / "pdfs"               # cache commun des sources téléchargées
OUTPUT_BASE = DATA_DIR / "outputs"        # cours produits (un sous-dossier par session en public)
DB_PATH = DATA_DIR / "memoires.db"        # fiches des mémoires déjà lus (cache commun)
for d in (DATA_DIR, PDF_DIR, OUTPUT_BASE):
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_TOP_N = 8

# Recherche web côté Claude, restreinte aux sites des mémoires
WEB_SEARCH_TOOL = "web_search_20260318"
SEARCH_DOMAINS = ["ressources-actuarielles.net", "institutdesactuaires.com"]

# Politesse envers les sites sources
HTTP_DELAY_S = 2.0
USER_AGENT = "IActuaire/1.0 (formation actuarielle)"

_DYNAMIC = {"MODEL_SMART": "model_smart", "MODEL_FAST": "model_fast",
            "MIN_RELEVANCE": "min_relevance", "OUTPUT_DIR": "out_dir"}


def __getattr__(name):
    """Valeurs propres à l'utilisateur courant (voir runtime.py)."""
    if name in _DYNAMIC:
        from . import runtime
        return getattr(runtime.get(), _DYNAMIC[name])
    raise AttributeError(name)

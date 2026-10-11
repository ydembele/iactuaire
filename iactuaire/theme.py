"""Charte graphique des livrables (PowerPoint + PDF).

Par défaut : style Generali (rouge, blanc, gris). Pour ajuster sans toucher au code,
crée `templates/theme.json` avec les clés à remplacer, par exemple :
    {"auteur": "Ton nom", "red": "C21B17", "font": "Arial"}
Pour le logo : dépose le fichier officiel de ton entreprise dans `templates/logo.png`
(et éventuellement `templates/logo_blanc.png` pour les fonds rouges).
"""
import json

from . import config
from .config import ROOT

TEMPLATES = ROOT / "templates"

DEFAULT = {
    "auteur": "",           # nom par défaut sur la couverture (usage local : via templates/theme.json)
    "red": "C21B17",        # rouge principal
    "red_dark": "8E1410",   # rouge profond (ombres, survols)
    "ink": "1F1F1F",        # texte principal
    "grey": "6E6E6E",       # texte secondaire
    "line": "D9D6D4",       # filets
    "panel": "F4F2F1",      # fonds de cartes
    "soft": "FBEAE8",       # fond « À retenir »
    "dark": "2B2B2B",       # intercalaires de section (sombres)
    "white": "FFFFFF",
    "font": "Arial",
    "mono": "Consolas",
}


def load() -> dict:
    t = dict(DEFAULT)
    f = TEMPLATES / "theme.json"
    if f.exists():
        try:
            t.update(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    from . import runtime
    t["auteur"] = runtime.get().auteur or (t["auteur"] if config.LOCAL else "")
    t["credit"] = "IActuaire — conçu par Youssouf Dembélé"
    t["logo"] = next((str(p) for p in (TEMPLATES / "logo.png", TEMPLATES / "logo.jpg") if p.exists()), None)
    t["logo_white"] = next(
        (str(p) for p in (TEMPLATES / "logo_blanc.png", TEMPLATES / "logo_white.png") if p.exists()), None
    )
    return t

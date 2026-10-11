"""Étape 1 — Trouver des mémoires candidats sur un thème.

L'agent lance lui-même plusieurs recherches web (outil serveur `web_search` de
l'API Claude) limitées aux domaines où les mémoires sont publiés. On récupère
directement les URL des résultats : pas besoin de connaître la structure HTML
du site.
"""
from urllib.parse import urlparse

from . import config
from .llm import parse_json, web_search

SYSTEM = """Tu es un documentaliste expert en actuariat (France).
Ta mission : trouver le plus de MÉMOIRES D'ACTUARIAT pertinents possible sur le thème donné,
publiés sur les sites autorisés (PDF de mémoires de l'ISFA, Dauphine, CNAM, ENSAE, EURIA,
ISUP, CEA, IRM… diffusés via ressources-actuarielles.net ou institutdesactuaires.com).

Méthode :
- Lance plusieurs recherches variées : synonymes français ET anglais, méthodes associées,
  cadre réglementaire (Solvabilité II, IFRS 17…), branches (vie, non-vie, santé, prévoyance).
- Ajoute « mémoire » ou « mémoire actuariat » à certaines requêtes.
- Ignore ce qui n'est pas un mémoire (offres d'emploi, pages d'actualité, programmes de cours).

À la fin, réponds avec un tableau JSON :
[{"url": "...", "titre": "...", "pourquoi": "une phrase"}]"""


def _is_allowed(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in config.SEARCH_DOMAINS)


def find_candidates(theme: str, max_candidates: int, log=print, exclude: list[str] | None = None) -> list[dict]:
    user = (f"Thème : {theme}\nTrouve jusqu'à {max_candidates} mémoires pertinents."
            + (("\nDéjà trouvés (cherche AUTRE CHOSE, avec d'autres mots-clés et angles) :\n- "
                + "\n- ".join(exclude[:40])) if exclude else ""))
    final, seen = web_search(SYSTEM, user, config.SEARCH_DOMAINS, max_uses=8, log=log)
    found = {u: {"url": u, "titre": t, "pourquoi": ""} for u, t in seen.items() if _is_allowed(u)}

    # La liste choisie par le modèle passe en premier (elle est déjà filtrée).
    ranked: list[dict] = []
    try:
        for item in parse_json(final):
            url = item.get("url", "")
            if _is_allowed(url):
                ranked.append({**found.get(url, {}), **item})
    except Exception:
        log("⚠️ Pas de liste JSON finale, on garde tous les résultats bruts.")
    seen = {c["url"] for c in ranked}
    ranked += [c for u, c in found.items() if u not in seen]

    log(f"📚 {len(ranked)} candidats trouvés")
    return ranked[:max_candidates]

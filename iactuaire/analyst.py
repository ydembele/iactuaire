"""Étape 3 — Lire un mémoire, en faire une fiche et juger sa pertinence."""
import json

from . import config
from .db import normalize_fiche
from .llm import ask_json

FICHE_SYSTEM = """Tu es actuaire senior et tu lis des mémoires d'actuariat.
À partir des extraits fournis (page de garde, résumé/note de synthèse, conclusion),
produis une fiche factuelle. N'invente rien : si une info est absente, mets null.

Format JSON :
{
 "titre": str, "auteur": str|null, "annee": int|null,
 "ecole": str|null (sigle court : ISFA, ENSAE, Dauphine, CNAM, ISUP, EURIA, CEA, IRM…), "entreprise": str|null,
 "branche": "vie"|"non-vie"|"santé/prévoyance"|"finance/ALM"|"transverse"|null,
 "problematique": str,
 "methodes": [str] (noms courts et standard, ≤ 5 mots chacun : « Chain Ladder », « GLM », « GSE », « Flexing »…),
 "donnees": str|null,
 "cadre_reglementaire": [str] (noms courts : « Solvabilité II », « IFRS 17 », « ORSA »…),
 "resultats_cles": [str],
 "limites": [str],
 "mots_cles": [str],
 "pertinence": int (0-10, pertinence pour le THÈME donné),
 "justification": str (une phrase)
}"""

SCORE_SYSTEM = """Tu es actuaire senior. Évalue la pertinence d'un mémoire (décrit par sa fiche)
pour le thème donné. JSON : {"pertinence": int 0-10, "justification": str}"""


def make_fiche(theme: str, extraits: dict) -> dict:
    user = (
        f"THÈME RECHERCHÉ : {theme}\n\n"
        f"=== PAGE DE GARDE ===\n{extraits['cover']}\n\n"
        f"=== RÉSUMÉ / NOTE DE SYNTHÈSE ===\n{extraits['resume']}\n\n"
        f"=== CONCLUSION ===\n{extraits['conclusion']}"
    )
    return normalize_fiche(ask_json(config.MODEL_FAST, FICHE_SYSTEM, user, max_tokens=4000))


def score_existing(theme: str, fiche: dict) -> dict:
    """Mémoire déjà lu pour un autre thème : on ne re-télécharge rien."""
    light = {k: v for k, v in fiche.items() if k not in ("pertinence", "justification")}
    return ask_json(
        config.MODEL_FAST, SCORE_SYSTEM,
        f"THÈME : {theme}\n\nFICHE :\n{json.dumps(light, ensure_ascii=False)}",
        max_tokens=1500,
    )


PRERANK_SYSTEM = """Tu es actuaire senior et documentaliste. On te donne une liste de mémoires d'actuariat
candidats (titre, et selon le cas un extrait, une problématique, des méthodes). Estime pour chacun la
probabilité qu'il soit utile pour apprendre le THÈME, en tenant compte des synonymes français et anglais
et des notions voisines. Note 0 à 10 (10 = cœur du sujet ; 0 = hors sujet).
JSON : [{"id": int, "note": int}] — un élément par candidat, dans n'importe quel ordre."""


def prerank(theme: str, objectifs: str, candidates: list[dict]) -> dict[int, int]:
    """Pré-classement rapide, AVANT tout téléchargement : un seul appel pour tous les candidats.
    Renvoie {indice du candidat: note estimée}. En cas d'échec, note neutre (5) pour tous."""
    if not candidates:
        return {}
    lines = []
    for i, c in enumerate(candidates):
        f = c.get("fiche") or {}
        desc = f.get("problematique") or c.get("pourquoi") or ""
        meth = ", ".join((f.get("methodes") or [])[:5])
        lines.append(f"{i}. {c.get('titre') or f.get('titre') or c['url']}"
                     + (f" — {desc[:220]}" if desc else "") + (f" [méthodes : {meth}]" if meth else ""))
    try:
        out = ask_json(config.MODEL_FAST, PRERANK_SYSTEM,
                       f"THÈME : {theme}\n" + (f"NOTIONS VISÉES : {objectifs[:400]}\n" if objectifs else "")
                       + "\nCANDIDATS :\n" + "\n".join(lines), max_tokens=3000)
        notes = {int(x["id"]): int(x.get("note") or 0) for x in out if isinstance(x, dict) and "id" in x}
    except Exception:
        notes = {}
    return {i: notes.get(i, 5) for i in range(len(candidates))}

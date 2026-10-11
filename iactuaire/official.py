"""Sources officielles (EIOPA, ACPR, EUR-Lex, Légifrance…) lues en entier.

1. Recherche web restreinte aux domaines officiels choisis dans les réglages.
2. On ne garde que des URL réellement présentes dans les résultats (rien d'inventé).
3. Téléchargement (PDF de préférence), extraction page par page.
4. Notation de la pertinence ; les meilleurs documents deviennent O1, O2… et sont cités « O1 p.N ».
"""
from urllib.parse import urlparse

from . import config, reader
from .llm import ask_json, parse_json, web_search

SEARCH_SYSTEM = """Tu es documentaliste réglementaire en assurance. Trouve les DOCUMENTS OFFICIELS les plus utiles
pour apprendre le sujet : orientations (guidelines), documentation technique, rapports, avis, Q&A,
notices et instructions ACPR, textes réglementaires (règlement délégué 2015/35, directive Solvabilité II…).
Privilégie les documents de fond (PDF) aux pages d'actualité. Cherche en anglais pour l'EIOPA,
en français pour l'ACPR.

Réponds à la fin avec un tableau JSON :
[{"url": str, "titre": str, "editeur": "EIOPA"|"ACPR"|"Commission européenne"|"Légifrance"|str,
  "type": str (orientations, rapport, notice, règlement…), "annee": str|null, "pourquoi": str}]
Au maximum 8 documents."""

SCORE_SYSTEM = """Tu évalues l'utilité d'un document officiel pour un cours d'actuariat sur un thème donné.
JSON : {"pertinence": int 0-10, "justification": str (une phrase), "resume": str (2 phrases)}"""


def _editeur(url: str) -> str:
    host = urlparse(url).netloc
    for key, name in (("eiopa", "EIOPA"), ("acpr", "ACPR"), ("eur-lex", "EUR-Lex"), ("legifrance", "Légifrance"),
                      ("institutdesactuaires", "Institut des actuaires")):
        if key in host:
            return name
    return host


def find_official_docs(theme: str, objectifs: str, domains: list[str], max_docs: int, seuil: int,
                       log=print) -> list[dict]:
    if not domains or max_docs <= 0:
        return []
    final, seen = web_search(SEARCH_SYSTEM, f"THÈME : {theme}\nNOTIONS À APPRENDRE : {objectifs or theme}",
                             domains, max_uses=6,
                             log=lambda m: log(m.replace("🔎 Recherche", "🏛️ Recherche officielle")))
    try:
        proposed = [d for d in parse_json(final) if d.get("url") in seen]
    except Exception:
        proposed = []
    if not proposed:   # à défaut, les résultats bruts de la recherche
        proposed = [{"url": u, "titre": t} for u, t in seen.items()]

    docs = []
    for d in proposed[: max_docs * 2]:
        try:
            got = reader.fetch_document(d["url"])
        except Exception as e:
            log(f"⛔ Document officiel inaccessible ({e}) : {d.get('titre', d['url'])[:70]}")
            continue
        text = "\n".join(got["pages"])
        if len(text) < 1500:
            continue
        try:
            sc = ask_json(config.MODEL_FAST, SCORE_SYSTEM,
                          f"THÈME : {theme}\nTITRE : {d.get('titre')}\nDÉBUT DU DOCUMENT :\n{text[:6000]}",
                          max_tokens=1500)
            score = int(sc.get("pertinence") or 0)
        except Exception as e:   # un document mal noté ne bloque pas les autres
            log(f"⚠️ Notation impossible ({type(e).__name__}) : {d.get('titre', d['url'])[:70]}")
            continue
        log(f"📘 {_editeur(d['url'])} — {d.get('titre', '')[:70]} ({len(got['pages'])} p.) : pertinence {score}/10")
        if score >= seuil:
            docs.append({**d, "editeur": d.get("editeur") or _editeur(d["url"]), "pages": got["pages"],
                         "kind": got["kind"], "score": score, "resume": sc.get("resume", ""),
                         "justification": sc.get("justification", "")})
    docs = sorted(docs, key=lambda x: -x["score"])[:max_docs]
    for i, d in enumerate(docs, 1):
        d["id"] = f"O{i}"
    log(f"🏛️ {len(docs)} document(s) officiel(s) retenu(s)")
    return docs

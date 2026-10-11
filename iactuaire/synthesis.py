"""Étape 4 — Construire un COURS à partir des mémoires (cas concrets) et de sources publiques.

Déroulé, comme un formateur :
  1. plan (objectifs, sections, slides prévues) — en suivant la structure demandée si elle est donnée ;
  2. rédaction des slides par lots de 5 ;
  3. clôture : points clés, glossaire, introduction/conclusion du polycopié.
Les sources (texte des mémoires avec repères de page + sources publiques) sont envoyées dans un
contexte mis en cache, réutilisé par tous les appels.
"""
import json
import re
from dataclasses import dataclass, field

from . import config, normalize
from .llm import ask, ask_json, cached_system
from .reader import paged_text, passages_by_page
from .theme import TEMPLATES

CONTEXT_CHARS = 380_000   # ~100k tokens : au-delà, on ne garde que les pages pertinentes
BATCH = 5                 # slides rédigées par appel


@dataclass
class CourseRequest:
    theme: str
    objectifs: str = ""          # « ce que je veux apprendre »
    structure: str = ""          # structure attendue (facultative)
    official_docs: list = field(default_factory=list)   # documents EIOPA / ACPR… (O1, O2…)
    max_content_slides: int = 30                         # budget de slides de contenu
    glossary_max: int = 24                               # nombre maximal de termes du glossaire


def consignes() -> str:
    f = TEMPLATES / "consignes_cours.md"
    if f.exists():
        return "\n".join(l for l in f.read_text(encoding="utf-8").splitlines() if not l.startswith("#")).strip()
    return "Tu es un actuaire senior et un formateur exigeant. Tu construis un COURS factuel et sourcé."


# --------------------------------------------------------------------------- sources

def _short(m: dict) -> str:
    f = m["fiche"]
    auteur = str(f.get("auteur") or "").split(",")[0].strip()
    nom = auteur.split()[-1].title() if auteur else (f.get("titre") or "")[:30]
    bits = [nom, f.get("ecole"), str(f.get("annee") or "")]
    return " ".join(b for b in bits if b)


def _ref(m: dict) -> str:
    f = m["fiche"]
    return ", ".join(str(x) for x in (f.get("auteur"), f.get("titre"), f.get("ecole"), f.get("entreprise"),
                                      f.get("annee")) if x)


def source_list(retained: list[dict], official: list[dict] | None = None) -> list[dict]:
    official = official or []
    out = [{"id": m["id"], "court": _short(m), "ref": _ref(m), "url": m["url"], "nature": "Mémoire"}
           for m in retained]
    out += [{"id": d["id"], "court": f"{d.get('editeur', '')} {d.get('annee') or ''}".strip(),
             "ref": ", ".join(x for x in (d.get("editeur"), d.get("titre"), d.get("type"), d.get("annee")) if x),
             "url": d["url"], "nature": f"Document officiel ({d.get('editeur', '')})"} for d in official]
    return out


def build_context(req: CourseRequest, retained: list[dict]) -> str:
    for i, m in enumerate(retained, 1):
        m["id"] = f"M{i}"
    docs = retained + req.official_docs
    total = sum(len(t) for m in docs for t in m.get("pages", []))
    keywords = re.findall(r"[\wÀ-ÿ_]{3,}", f"{req.theme} {req.objectifs} {req.structure}".lower())
    per_doc = CONTEXT_CHARS // max(len(docs), 1)

    parts = ["MÉMOIRES SOURCES (cas concrets). Chaque page est repérée par [[Mx p.N]] : cite « Mx p.N »."]
    for m in retained:
        fiche = {k: v for k, v in m["fiche"].items() if k not in ("pertinence", "justification")}
        parts.append(f"\n### {m['id']} — {_ref(m)} — {m['url']}\nFICHE : {json.dumps(fiche, ensure_ascii=False)}")
        pages = m.get("pages") or []
        if not pages:
            continue
        if total <= CONTEXT_CHARS:
            parts.append("TEXTE INTÉGRAL :\n" + paged_text(pages, m["id"]))
        else:
            parts.append("PAGES PERTINENTES :\n" + passages_by_page(pages, m["id"], keywords, per_doc))
    if req.official_docs:
        parts.append("\nSOURCES OFFICIELLES (régulateurs et textes). Repères [[Ox p.N]] : cite « Ox p.N ». "
                     "Elles font foi pour les définitions et exigences réglementaires.")
        for d in req.official_docs:
            parts.append(f"\n### {d['id']} — {d.get('editeur', '')}, {d.get('titre', '')} ({d.get('annee') or 's.d.'}) — {d['url']}")
            pages = d.get("pages") or []
            if total <= CONTEXT_CHARS:
                parts.append("TEXTE INTÉGRAL :\n" + paged_text(pages, d["id"]))
            else:
                parts.append("PAGES PERTINENTES :\n" + passages_by_page(pages, d["id"], keywords, per_doc))
    return "\n".join(parts)


# --------------------------------------------------------------------------- formats

TYPES = """TYPES DE SLIDES (choisis le plus adapté à l'idée ; varie-les) :
- "colonnes" : 2 notions comparées
- "cartes" : 3-4 notions parallèles
- "etapes" : processus ordonné de 3 à 5 étapes
- "formule" : 1 à 3 formules expliquées (chasse fixe)
- "tableau" : variables, champs d'une table, comparaison, matrice (✓ / ✗)
- "points" : explication avec encadré
- "chiffres" : 2 à 4 chiffres clés
- "graphique" : graphique natif (barres, barres_h, courbes, anneau, cascade) à partir de données sourcées
- "schema" : schéma de flux redessiné (boîtes et flèches)"""

FIELDS = """CHAMPS COMMUNS à chaque slide :
 "type", "titre" (titre-message : la phrase à comprendre), "a_retenir" (une phrase forte),
 "sources" (["M1 p.42", "O2 p.15", …] ; [] seulement pour des chiffres fictifs ou une définition générale),
 "vigilance" (null, ou ≤ 40 mots : incohérence/coquille d'un mémoire, information non documentée),
 "notes" (4 à 7 phrases : l'explication complète ; sert de texte au polycopié).
CHAMPS PAR TYPE (respecte les longueurs, la slide doit rester lisible) :
 colonnes : "colonnes": [{"titre": str, "points": [str ≤ 22 mots] (3-5)}] ×2,
            "encadre": null | {"titre": str, "texte": str ≤ 45 mots}
 cartes   : "cartes": [{"titre": str ≤ 5 mots, "texte": str ≤ 40 mots}] (3-4)
 etapes   : "etapes": [{"titre": str ≤ 3 mots, "texte": str ≤ 25 mots}] (3-5), "texte": null | str ≤ 50 mots
 formule  : "intro": str ≤ 35 mots,
            "formules": [{"nom": str, "expression": str ≤ 90 caractères, "legende": str ≤ 35 mots}] (1-3)
 tableau  : "intro": str ≤ 30 mots, "colonnes": [str] (2-5), "lignes": [[str ≤ 14 mots]] (2-8),
            "commentaire": null | str ≤ 35 mots
 points   : "points": [str ≤ 25 mots] (3-6), "encadre": null | {"titre": str, "texte": str ≤ 50 mots}
 chiffres : "chiffres": [{"valeur": str ≤ 10 caractères, "libelle": str ≤ 12 mots}] (2-4), "texte": str ≤ 50 mots
 graphique: "intro": null | str ≤ 30 mots,
            "graphique": {"type": "barres"|"barres_h"|"courbes"|"anneau"|"cascade", "titre": str,
                          "unite": str|null, "categories": [str ≤ 4 mots],
                          "series": [{"nom": str, "valeurs": [nombre]}],
                          "totaux": [index des barres « total » — cascade uniquement] },
            "commentaire": str ≤ 40 mots
            (anneau et cascade : une seule série ; cascade : valeurs = variations, totaux = barres pleines)
 schema   : "schema": {"disposition": "ligne"|"cycle",
                       "noeuds": [{"id": str, "titre": str ≤ 4 mots, "texte": str ≤ 14 mots}] (3-6),
                       "liens": [{"de": id, "vers": id, "libelle": str ≤ 4 mots}]},
            "commentaire": null | str ≤ 35 mots"""


def _request_block(req: CourseRequest) -> str:
    b = (f"THÈME DU COURS : {req.theme}\n"
         f"LIMITE : au plus {req.max_content_slides} slides de contenu ; glossaire de {req.glossary_max} termes au plus.\n")
    if req.objectifs:
        b += f"\nCE QUE L'APPRENANT VEUT APPRENDRE :\n{req.objectifs}\n"
    if req.structure:
        b += f"\nSTRUCTURE ATTENDUE (à respecter) :\n{req.structure}\n"
    return b


PLAN_TASK = """TÂCHE : le PLAN du cours. JSON :
{"titre": str, "sous_titre": str (sur quels cas concrets il s'appuie), "public": str,
 "objectifs": [{"verbe": str, "texte": str}] (3-5),
 "sections": [{"titre": str, "accroche": str,
               "slides": [{"titre": str, "type": TYPE, "intention": str (contenu précis et sources visées)}]}]}
Règles :
- Si une STRUCTURE ATTENDUE est donnée : ses parties deviennent les sections, dans l'ordre ; chacun de
  ses points devient au moins une slide (plusieurs si nécessaire : une idée par slide). N'en omets aucun.
- Sinon : 3 à 6 sections, progression des fondamentaux vers les méthodes, la réglementation et les limites.
- BUDGET STRICT : le nombre total de slides de contenu (toutes sections confondues) ne dépasse pas la
  limite indiquée dans la demande. Si la structure attendue est plus riche, fusionne des points proches et
  priorise l'essentiel plutôt que d'omettre une partie.
- Prévois des "graphique" dès que les sources donnent des séries de chiffres, et des "schema" pour les flux.
- Ne prévois pas de glossaire ni de liste des sources : ils sont ajoutés automatiquement."""

SECTION_TASK = """TÂCHE : rédiger les slides demandées, dans l'ordre, en respectant leur titre et leur type
(tu peux préciser le titre). Réponds avec un tableau JSON de slides."""

CLOSING_TASK = """TÂCHE : clôturer le cours. JSON :
{"points_cles": [str ≤ 25 mots] (5-7),
 "pour_aller_plus_loin": [str ≤ 20 mots] (2-4, en citant les sources),
 "glossaire": [{"terme": str, "definition": str ≤ 30 mots, "source": str}] (les termes clés du cours,
              au plus le nombre indiqué dans la demande),
 "introduction": str (4-6 phrases, pour le polycopié),
 "conclusion": str (4-6 phrases, pour le polycopié)}"""


def _system(task: str, context: str) -> list[dict]:
    return cached_system(f"{consignes()}\n\n{TYPES}\n\n{FIELDS}\n\n{task}", context)


def _trim_plan(plan: dict, budget: int) -> dict:
    """Dernier recours : retire les slides en fin de section, en gardant au moins une slide par section."""
    secs = plan["sections"]
    while sum(len(s["slides"]) for s in secs) > budget:
        longest = max(secs, key=lambda s: len(s["slides"]))
        if len(longest["slides"]) <= 1:
            secs.pop()          # plus de sections que de slides autorisées
            continue
        longest["slides"].pop()
    return plan


def build_course(req: CourseRequest, retained: list[dict], log=print) -> dict:
    context = build_context(req, retained)
    log(f"📚 Contexte : {len(context) // 1000} k caractères de sources (mis en cache)")

    log("🗺️ Plan du cours…")
    plan = ask_json(config.MODEL_SMART, _system(PLAN_TASK, context), _request_block(req), max_tokens=8000)
    n_slides = sum(len(s["slides"]) for s in plan["sections"])
    if n_slides > req.max_content_slides:
        log(f"   plan trop long ({n_slides} slides pour {req.max_content_slides} autorisées) : resserrement…")
        plan = ask_json(config.MODEL_SMART, _system(PLAN_TASK, context),
                        _request_block(req) + "\nPLAN À RESSERRER (fusionne les slides proches, garde toutes les parties) :\n"
                        + json.dumps(plan, ensure_ascii=False), max_tokens=8000)
        plan = _trim_plan(plan, req.max_content_slides)
        n_slides = sum(len(s["slides"]) for s in plan["sections"])
    log(f"   {len(plan['sections'])} sections, {n_slides} slides de contenu prévues")

    sections = []
    for i, sec in enumerate(plan["sections"], 1):
        slides = []
        todo = sec["slides"]
        for k in range(0, len(todo), BATCH):
            lot = todo[k:k + BATCH]
            log(f"✍️ Section {i}/{len(plan['sections'])} « {sec['titre']} » — slides {k + 1}-{k + len(lot)}")
            out = ask_json(
                config.MODEL_SMART, _system(SECTION_TASK, context),
                _request_block(req)
                + f"\nPLAN DU COURS (contexte) :\n{json.dumps(plan, ensure_ascii=False)}\n"
                + f"\nSECTION : {sec['titre']}\nSLIDES À RÉDIGER :\n{json.dumps(lot, ensure_ascii=False)}",
                max_tokens=14000,
            )
            slides += out.get("slides", []) if isinstance(out, dict) else out
        sections.append({"titre": sec["titre"], "accroche": sec.get("accroche", ""), "slides": slides})

    log("🎓 Points clés et glossaire…")
    closing = ask_json(config.MODEL_SMART, _system(CLOSING_TASK, context),
                       _request_block(req) + f"\nPLAN : {json.dumps(plan, ensure_ascii=False)}", max_tokens=8000)

    closing = closing if isinstance(closing, dict) else {}
    closing["glossaire"] = (closing.get("glossaire") or [])[: req.glossary_max]
    return normalize.course({
        "theme": req.theme,
        "titre": plan["titre"],
        "sous_titre": plan.get("sous_titre", ""),
        "public": plan.get("public", ""),
        "objectifs": plan.get("objectifs", []),
        "sections": sections,
        **closing,
        "bibliographie": source_list(retained, req.official_docs),
    })


def rewrite_slide(req: CourseRequest, retained: list[dict], slide: dict, problems: list[str]) -> dict:
    """Corrige une slide signalée par le contrôle qualité."""
    context = build_context(req, retained)
    fixed = ask_json(
        config.MODEL_SMART, _system("TÂCHE : corriger UNE slide. Réponds avec l'objet JSON de la slide corrigée.",
                                    context),
        "SLIDE :\n" + json.dumps(slide, ensure_ascii=False) + "\n\nPROBLÈMES À CORRIGER :\n- "
        + "\n- ".join(problems)
        + "\n\nPour un chiffre introuvable : remplace-le par la valeur exacte de la source, ou retire-le, ou "
          "étiquette l'exemple « chiffres fictifs ». Pour un texte trop long : raccourcis sans perdre le fond.",
        max_tokens=5000,
    )
    return normalize.slide(fixed) if isinstance(fixed, dict) and fixed.get("type") else slide


# --------------------------------------------------------------------------- questions

QA_SYSTEM = """Tu es un actuaire senior qui explique clairement, comme un formateur. Réponds en t'appuyant
sur les sources et cite-les avec la page, ex. [M2 p.31]. Structure : l'idée en une phrase, puis
l'explication (définitions, intuition, formule si utile, exemple). Si les sources ne permettent pas de
répondre, dis-le, puis donne ce que tu sais en le signalant comme connaissance générale (non sourcée).
Réponds en français."""


def answer(question: str, theme: str, retained: list[dict], history: list[dict] | None = None,
           official: list[dict] | None = None) -> str:
    context = build_context(CourseRequest(theme, objectifs=question, official_docs=official or []), retained)
    convo = "".join(f"\n{h['role'].upper()} : {h['content']}" for h in (history or [])[-6:])
    return ask(config.MODEL_SMART, cached_system(QA_SYSTEM, context),
               f"ÉCHANGE PRÉCÉDENT :{convo}\n\nQUESTION : {question}", max_tokens=3000)

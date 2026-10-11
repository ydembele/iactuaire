"""Orchestrateur : thème → recherche → lecture → tri → synthèse → PPT + PDF."""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import (analyst, config, db, discovery, normalize, official, qa, reader, render_pdf, render_pptx, render_quarto,
               settings, synthesis)
from .settings import Reglages
from .synthesis import CourseRequest


@dataclass
class Result:
    theme: str
    examined: list[dict] = field(default_factory=list)   # tout ce qui a été regardé
    retained: list[dict] = field(default_factory=list)   # mémoires utilisés pour la synthèse
    deck: dict | None = None
    pptx_path: str | None = None
    pdf_path: str | None = None
    qa_path: str | None = None
    qa_text: str = ""
    request: CourseRequest | None = None
    stats: dict = field(default_factory=dict)


def _known_matches(theme: str, limit: int = 30) -> list[dict]:
    """Mémoires déjà lus lors de recherches précédentes qui semblent liés au thème."""
    words = [w for w in re.findall(r"\w{4,}", theme.lower())]
    hits = []
    for m in db.all_read():
        blob = json.dumps(m["fiche"], ensure_ascii=False).lower()
        score = sum(blob.count(w) for w in words)
        if score:
            hits.append((score, m))
    return [m for _, m in sorted(hits, key=lambda x: -x[0])[:limit]]


def _process(theme: str, cand: dict, log) -> dict:
    url = cand["url"]
    known = db.get_memoire(url)

    if known and known["statut"] != "lu":
        return {"url": url, "titre": known["titre"], "statut": known["statut"], "raison": known["raison"]}

    if known:  # déjà lu → seulement (re)noter la pertinence pour ce thème
        p = db.get_pertinence(theme, url)
        if p:
            score, justif = p["score"], p["justification"]
        else:
            s = analyst.score_existing(theme, known["fiche"])
            score, justif = int(s.get("pertinence", 0)), s.get("justification", "")
            db.save_pertinence(theme, url, score, justif)
        p = {"justification": justif}
        log(f"📗 Déjà lu — pertinence {score}/10 : {(known['fiche'].get('titre') or known['titre'] or '')[:80]}")
        return {"url": url, "titre": known["fiche"].get("titre") or known["titre"], "statut": "lu (mémoire)",
                "score": score, "justification": p["justification"],
                "fiche": known["fiche"], "pdf_path": known["pdf_path"]}

    if cand.get("local_path"):   # document joint par l'utilisateur : privé, jamais dans le cache commun
        ex = reader.extract(cand["local_path"])
        if ex["n_chars"] < 5000:
            return {"url": url, "titre": cand.get("titre"), "statut": "illisible", "raison": "PDF scanné ou vide"}
        fiche = analyst.make_fiche(theme, ex)
        log(f"📖 Lu ({ex['n_pages']} p.) — document joint : {fiche.get('titre') or cand.get('titre')}"[:150])
        return {"url": url, "titre": fiche.get("titre") or cand.get("titre"), "statut": "lu (joint)",
                "score": int(fiche.get("pertinence") or 0), "justification": fiche.get("justification"),
                "fiche": fiche, "pdf_path": cand["local_path"], "pages": ex["pages"], "full_text": ex["full_text"]}

    pdf, err = reader.download(url)
    if err:
        log(f"⛔ Ignoré ({err}) : {cand.get('titre', url)[:80]}")
        db.save_memoire(url, cand.get("titre"), "indisponible", raison=err)
        return {"url": url, "titre": cand.get("titre"), "statut": "indisponible", "raison": err}

    ex = reader.extract(pdf)
    if ex["n_chars"] < 5000:
        db.save_memoire(url, cand.get("titre"), "illisible", raison="PDF scanné ou vide", pdf_path=pdf)
        return {"url": url, "titre": cand.get("titre"), "statut": "illisible", "raison": "PDF scanné ou vide"}

    fiche = analyst.make_fiche(theme, ex)
    db.save_memoire(url, fiche.get("titre") or cand.get("titre"), "lu", pdf_path=pdf,
                    fiche=fiche, extrait=ex["resume"][:4000])
    score = int(fiche.get("pertinence") or 0)
    db.save_pertinence(theme, url, score, fiche.get("justification", ""))
    log(f"📖 Lu ({ex['n_pages']} p.) — pertinence {fiche.get('pertinence')}/10 : {fiche.get('titre', '')[:70]}")
    return {"url": url, "titre": fiche.get("titre"), "statut": "lu", "score": score,
            "justification": fiche.get("justification"), "fiche": fiche, "pdf_path": pdf}


def _local_candidates(uploaded: list[tuple[str, bytes]]) -> list[dict]:
    """PDF joints par l'utilisateur : enregistrés puis traités comme les autres."""
    out = []
    for name, data in uploaded or []:
        safe = re.sub(r"[^\w.\-]+", "_", name)
        folder = config.OUTPUT_DIR / "joints"          # dossier de la session, pas le cache commun
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe
        path.write_bytes(data)
        out.append({"url": f"fichier://{safe}", "titre": name, "local_path": str(path)})
    return out


def run(req: CourseRequest | str, reglages: Reglages | None = None, log=print,
        imposed_urls: list[str] | None = None, uploaded: list[tuple[str, bytes]] | None = None,
        search: bool = True, make_files: bool = True, **_ignored) -> Result:
    """Recherche + lecture de mémoires (entre le minimum et le maximum réglés), puis cours."""
    r = (reglages or settings.charger()).apply()
    req = CourseRequest(req) if isinstance(req, str) else req
    theme = req.theme
    res = Result(theme, request=req)
    examined = lambda: {e["url"] for e in res.examined}
    n_read = lambda: sum(1 for e in res.examined if e.get("fiche"))

    # 1. Mémoires imposés (liens ou PDF joints) : toujours lus et retenus
    imposed = [{"url": u.strip(), "titre": u.strip()} for u in (imposed_urls or []) if u.strip()]
    imposed += _local_candidates(uploaded)
    forced = []
    for c in imposed:
        try:
            e = _process(theme, c, log)
        except Exception as ex:
            e = {"url": c["url"], "titre": c.get("titre"), "statut": "erreur", "raison": str(ex)}
        res.examined.append(e)
        if e.get("fiche"):
            forced.append(e)
            log(f"📌 Mémoire imposé : {e.get('titre', '')[:80]}")
        else:
            log(f"⚠️ Mémoire imposé illisible ou inaccessible : {c['url']} ({e.get('raison')})")

    # 2. Sélection : les candidats (mémoires déjà lus + résultats web) sont pré-classés par l'IA d'après
    #    leur titre et leur description, puis lus du plus prometteur au moins prometteur, jusqu'à réunir
    #    `max_memoires` mémoires pertinents (note ≥ seuil). Plafond de lecture : 3 × le maximum.
    good = lambda: sum(1 for e in res.examined if e.get("fiche") and e["url"] not in {f["url"] for f in forced}
                       and (e.get("score") or 0) >= r.seuil_pertinence)
    cap = max(10, 3 * r.max_memoires)
    if search and "memoires" in r.sources:
        log("🧠 Ce que je sais déjà sur ce thème…")
        pool = [{"url": m["url"], "titre": m["titre"], "fiche": m["fiche"]}
                for m in _known_matches(theme, 40) if m["url"] not in examined()]
        query = theme + (f". Notions visées : {req.objectifs[:300]}" if req.objectifs else "")
        for rnd in range(1, 4):
            if good() >= r.max_memoires or n_read() >= cap:
                break
            log(f"🌐 Recherche de mémoires (passe {rnd}) — {good()} pertinent(s) sur {n_read()} lu(s), "
                f"objectif {r.max_memoires}")
            found = discovery.find_candidates(query, max(8, (r.max_memoires - good()) * 3), log=log,
                                              exclude=[e.get("titre") or e["url"] for e in res.examined])
            known_urls = {c["url"] for c in pool} | examined()
            pool += [c for c in found if c["url"] not in known_urls]
            if not pool:
                log("   aucune nouvelle piste")
                break
            notes = analyst.prerank(theme, req.objectifs, pool)
            order = sorted(range(len(pool)), key=lambda i: -notes[i])
            log(f"🧭 {len(pool)} candidat(s) pré-classé(s) : lecture des plus prometteurs d'abord")
            for i in order:
                if good() >= r.max_memoires or n_read() >= cap:
                    break
                if notes[i] <= 2:          # jugé hors sujet avant même d'être ouvert
                    continue
                c = pool[i]
                try:
                    res.examined.append(_process(theme, c, log))
                except Exception as e:   # un mémoire qui pose problème ne bloque pas le cours
                    log(f"⚠️ Mémoire ignoré ({type(e).__name__}) : {(c.get('titre') or c['url'])[:70]}")
                    res.examined.append({"url": c["url"], "titre": c.get("titre"), "statut": "erreur", "raison": str(e)})
            # les candidats non lus restent en lice : ils seront re-classés avec ceux de la passe suivante
            pool = [pool[i] for i in order if notes[i] > 2 and pool[i]["url"] not in examined()]
        log(f"📊 {good()} mémoire(s) pertinent(s) sur {n_read()} lu(s)")
        if good() < r.min_memoires:
            log(f"⚠️ Seulement {good()} mémoire(s) au-dessus du seuil de {r.seuil_pertinence}/10 "
                f"pour un minimum de {r.min_memoires}.")

    forced_urls = {f["url"] for f in forced}
    others = sorted([e for e in res.examined if e["url"] not in forced_urls and e.get("fiche")],
                    key=lambda e: -(e.get("score") or 0))
    good = [e for e in others if (e.get("score") or 0) >= r.seuil_pertinence]
    res.retained = (forced + good)[: max(r.max_memoires, len(forced))]
    if len(res.retained) < r.min_memoires:   # compléter avec les meilleurs mémoires restants, s'ils sont proches du sujet
        extra = [e for e in others if e not in res.retained and (e.get("score") or 0) >= 4]
        res.retained += extra[: r.min_memoires - len(res.retained)]
    res.stats["memoires_lus"] = n_read()
    res.stats["memoires_retenus"] = len(res.retained)
    log(f"✅ {n_read()} mémoire(s) lu(s), {len(res.retained)} retenu(s) pour le cours ({len(forced)} imposé(s))")

    if not make_files:
        return res
    if not res.retained and not r.officiels():
        log("Aucune source exploitable : élargis le thème, baisse le seuil de pertinence ou joins des mémoires.")
        return res
    return make_course(res, r, log)


def _sections_estimees(req: CourseRequest) -> int:
    n = len(re.findall(r"(?m)^\s*\d+\s*[.)]", req.structure or ""))
    return n if n else 5


def make_course(res: Result, reglages: Reglages | None = None, log=print, **_ignored) -> Result:
    """Sources officielles, rédaction dans le budget de slides, contrôle qualité, polycopié dans le budget de pages."""
    r = (reglages or settings.charger()).apply()
    req = res.request or CourseRequest(res.theme)
    for m in list(res.retained):
        if m.get("pdf_path") and not m.get("pages"):
            try:
                ex = reader.extract(m["pdf_path"])
            except FileNotFoundError:        # PDF effacé du cache entre-temps : on le retélécharge
                pdf, err = reader.download(m["url"]) if m["url"].startswith("http") else (None, "absent")
                if err:
                    log(f"⚠️ Source devenue inaccessible, retirée : {m.get('titre', '')[:70]}")
                    res.retained.remove(m)
                    continue
                m["pdf_path"] = pdf
                ex = reader.extract(pdf)
            m["pages"], m["full_text"] = ex["pages"], ex["full_text"]

    if r.officiels() and not req.official_docs:
        try:
            req.official_docs = official.find_official_docs(
                req.theme, req.objectifs or req.structure, r.officiels(), r.max_docs_officiels,
                max(3, r.seuil_pertinence - 1), log=log)
        except Exception as e:
            log(f"⚠️ Sources officielles indisponibles : {e}")
    if not res.retained and not req.official_docs:
        log("Aucune source exploitable.")
        return res

    # budget de slides : la limite couvre aussi couverture, objectifs, intercalaires, synthèse, glossaire, sources
    n_src = len(res.retained) + len(req.official_docs)
    gloss_pages = 0 if r.max_slides < 20 else (1 if r.max_slides < 50 else 2)
    src_pages = max(1, -(-n_src // render_pptx.SOURCES_PER_PAGE))
    req.glossary_max = gloss_pages * render_pptx.GLOSS_PER_PAGE
    req.max_content_slides = max(3, r.max_slides - (3 + _sections_estimees(req) + gloss_pages + src_pages))
    log(f"📐 Budget : {r.max_slides} slides au total, dont {req.max_content_slides} de contenu ; "
        f"polycopié de {r.max_pages_pdf} pages au plus")

    log("✍️ Rédaction du cours…")
    course = normalize.course(synthesis.build_course(req, res.retained, log=log))
    cut = render_pptx.fit_to_slides(course, r.max_slides)
    if cut:
        log(f"✂️ {cut} slide(s) retirée(s) pour respecter la limite de {r.max_slides}")

    slug = re.sub(r"\W+", "_", res.theme.lower()).strip("_")[:50]
    base = config.OUTPUT_DIR / f"{slug}_{datetime.now():%Y%m%d_%H%M}"
    pptx_path = f"{base}.pptx"

    # ---- contrôle qualité + corrections
    log("🔍 Contrôle qualité…")
    known = qa.source_numbers(res.retained + req.official_docs, req.objectifs + " " + req.structure)
    _, layout, pmap = render_pptx.render_with_issues(course, pptx_path)
    fixed = _fix(course, qa.merge(qa.fact_check(course, known), layout), req, res.retained, log)
    _, layout, pmap = render_pptx.render_with_issues(course, pptx_path)
    visual = _safe_visual(pptx_path, log) if r.controle_visuel else None
    if visual:
        by_slide: dict = {}
        for v in visual:
            key = pmap.get(v.get("slide"))
            if key:
                by_slide.setdefault(key, []).append("mise en page : " + str(v.get("probleme")))
        if by_slide:
            fixed += _fix(course, by_slide, req, res.retained, log)
            _, layout, pmap = render_pptx.render_with_issues(course, pptx_path)
            visual = _safe_visual(pptx_path, log)

    log("📄 Mise en page du polycopié…")
    pdf_path, n_pages, level, moteur = render_polycopie(course, f"{base}_polycopie.pdf", r, log)
    n_slides = render_pptx.slide_count(course)
    res.stats.update({"slides": n_slides, "max_slides": r.max_slides, "pages_pdf": n_pages,
                      "max_pages_pdf": r.max_pages_pdf, "niveau_compaction": level, "moteur_pdf": moteur, "corrections": fixed,
                      "memoires_retenus": len(res.retained), "docs_officiels": len(req.official_docs)})
    budget = [f"- PowerPoint : {n_slides} slides (limite {r.max_slides})",
              f"- Polycopié ({moteur}) : {n_pages} pages (limite {r.max_pages_pdf})"
              + ("" if n_pages <= r.max_pages_pdf else " — limite non atteignable sans retirer de contenu ; "
                 "réduis le nombre de slides ou augmente la limite de pages"),
              f"- Sources : {len(res.retained)} mémoire(s), {len(req.official_docs)} document(s) officiel(s)"]
    fact = qa.fact_check(course, known)
    res.deck, res.pptx_path, res.pdf_path = course, pptx_path, pdf_path
    res.qa_text = qa.report(course, fact, layout, visual, qa.reopen_check(pptx_path), fixed, pmap, extra=budget)
    res.qa_path = f"{base}_controle_qualite.md"
    Path(res.qa_path).write_text(res.qa_text, encoding="utf-8")
    Path(f"{base}.json").write_text(json.dumps({**course, "stats": res.stats, "official_docs": [
        {k: v for k, v in d.items() if k != "pages"} for d in req.official_docs]}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    log(f"📦 Cours prêt : {n_slides} slides, polycopié de {n_pages} pages, {fixed} correction(s) automatique(s)")
    return res


def render_polycopie(course: dict, path: str, r: Reglages, log) -> tuple[str, int, int, str]:
    """Polycopié avec le moteur choisi ; si Quarto est absent ou échoue, le moteur Standard prend le relais."""
    if getattr(r, "moteur_pdf", "quarto") == "quarto":
        if render_quarto.available():
            try:
                return (*render_quarto.render_fitted(course, path, r.max_pages_pdf, log=log), "Quarto")
            except Exception as e:
                log(f"⚠️ Quarto n'a pas pu composer le polycopié ({str(e)[:160]}) → moteur Standard")
        else:
            log("ℹ️ Quarto n'est pas installé → polycopié avec le moteur Standard")
    return (*render_pdf.render_fitted(course, path, r.max_pages_pdf, log=log), "Standard")


def _safe_visual(pptx_path: str, log):
    """La relecture visuelle est un bonus : son échec ne doit jamais faire perdre le cours."""
    try:
        return qa.visual_check(pptx_path, log=log)
    except Exception as e:
        log(f"⚠️ Relecture visuelle impossible ({type(e).__name__}) : cours livré sans cette vérification")
        return None


def _fix(course: dict, flagged: dict, req: CourseRequest, retained: list[dict], log, cap: int = 20) -> int:
    n = 0
    for (i, j), problems in list(flagged.items())[:cap]:
        sl = course["sections"][i]["slides"][j]
        log(f"🛠️ Correction de « {sl.get('titre', '')[:60]} » : {problems[0][:80]}")
        try:
            course["sections"][i]["slides"][j] = synthesis.rewrite_slide(req, retained, sl, problems)
            n += 1
        except Exception as e:
            log(f"⚠️ Correction impossible : {e}")
    return n


def regenerate(req: CourseRequest | str, reglages: Reglages | None = None, log=print, **_ignored) -> Result:
    """Refait le cours à partir des mémoires déjà lus et notés pour ce thème (sans recherche web)."""
    r = (reglages or settings.charger()).apply()
    req = CourseRequest(req) if isinstance(req, str) else req
    res = Result(req.theme, request=req)
    res.retained = load_retained(req.theme, top_n=r.max_memoires, with_text=False)
    res.examined = list(res.retained)
    res.stats["memoires_lus"] = len(res.retained)
    log(f"♻️ {len(res.retained)} mémoire(s) déjà lu(s) réutilisé(s) pour « {req.theme} »")
    return make_course(res, r, log)


def load_retained(theme: str, top_n: int = config.DEFAULT_TOP_N, with_text: bool = True) -> list[dict]:
    """Mémoires déjà lus pour un thème (ou, à défaut, les plus proches par mots-clés), prêts à être cités."""
    out = []
    with db.connect() as con:
        rows = con.execute(
            """SELECT p.url, p.score, p.justification FROM pertinences p JOIN memoires m ON m.url = p.url
               WHERE p.theme = ? AND m.statut = 'lu' AND p.score >= ? ORDER BY p.score DESC LIMIT ?""",
            (theme.lower().strip(), config.MIN_RELEVANCE, top_n)).fetchall()
    urls = [(r["url"], r["score"], r["justification"]) for r in rows]
    if not urls:
        urls = [(m["url"], None, "proche par mots-clés") for m in _known_matches(theme, top_n)]
    for url, score, justif in urls:
        m = db.get_memoire(url)
        if not m or not m.get("fiche"):
            continue
        item = {"url": url, "titre": m["fiche"].get("titre"), "score": score, "justification": justif,
                "fiche": m["fiche"], "pdf_path": m["pdf_path"], "statut": "lu (mémoire)"}
        if with_text and m.get("pdf_path"):
            try:
                ex = reader.extract(m["pdf_path"])
                item["pages"], item["full_text"] = ex["pages"], ex["full_text"]
            except FileNotFoundError:
                pass
        out.append(item)
    return out


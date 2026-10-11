"""Contrôle qualité d'un cours avant livraison.

1. Fidélité : chaque chiffre d'une slide doit se retrouver dans les sources
   (sauf slides étiquetées « chiffres fictifs »).
2. Mise en page : textes et tableaux qui débordent (estimés au rendu).
3. Ouverture : le .pptx se rouvre sans erreur.
4. Rendu visuel (si LibreOffice est installé) : chaque slide est rendue en image et relue
   par Claude pour repérer débordements et chevauchements.
Les slides signalées sont réécrites automatiquement, puis un rapport est produit.
"""
import base64
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .llm import ask_with_images, parse_json

NUM = re.compile(r"(?<![\w.,])[-−]?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|(?<![\w.,])[-−]?\d+(?:[.,]\d+)?")


def _norm(tok: str) -> str:
    t = re.sub(r"[   ]", "", tok).replace("−", "-").replace(",", ".").lstrip("-")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t


def _numbers(text: str) -> set[str]:
    return {_norm(m.group()) for m in NUM.finditer(text or "")}


def _trivial(n: str) -> bool:
    """Nombres qui ne sont pas des « chiffres » à sourcer : petits entiers, années, numérotation."""
    try:
        v = float(n)
    except ValueError:
        return True
    return (v.is_integer() and v <= 12) or (v.is_integer() and 1900 <= v <= 2100)


def _slide_text(sl: dict) -> str:
    keep = {k: v for k, v in sl.items() if k not in ("sources", "type")}
    txt = json.dumps(keep, ensure_ascii=False)
    # arguments de fonctions dans les formules (D(0,1), VaR_99,5%(…), x_(t-1)) : pas des chiffres à sourcer
    txt = re.sub(r"\b[A-Za-zΣΔ_]+\([^()]{0,20}\)", " ", txt)
    return re.sub(r"[_^]\{?[\w.,+-]+\}?", " ", txt)


def source_numbers(docs: list[dict], extra_text: str = "") -> set[str]:
    corpus = [extra_text]
    for m in docs:
        corpus += m.get("pages") or [m.get("full_text") or ""]
        corpus.append(json.dumps(m.get("fiche") or {}, ensure_ascii=False))
    nums: set[str] = set()
    for t in corpus:
        nums |= _numbers(t)
    return nums


def fact_check(course: dict, known: set[str]) -> dict:
    issues = {}
    for i, sec in enumerate(course["sections"]):
        for j, sl in enumerate(sec["slides"]):
            txt = _slide_text(sl)
            if "fictif" in txt.lower():
                continue
            missing = sorted(n for n in _numbers(txt) if not _trivial(n) and n not in known)
            if missing:
                issues[(i, j)] = [f"chiffre(s) introuvable(s) dans les sources : {', '.join(missing[:8])}"]
    return issues


def reopen_check(path: str) -> str | None:
    from pptx import Presentation
    try:
        n = len(Presentation(path).slides)
        return None if n else "le fichier ne contient aucune slide"
    except Exception as e:
        return f"le fichier ne se rouvre pas : {e}"


def _convert(soffice: str, pptx_path: str, outdir: str):
    """Conversion PPTX → PDF. Un profil LibreOffice par appel : plusieurs utilisateurs peuvent
    convertir en même temps sans se bloquer."""
    profile = Path(outdir) / "lo_profile"
    subprocess.run([soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--convert-to", "pdf",
                    "--outdir", outdir, pptx_path], check=True, capture_output=True, timeout=300)


def _soffice() -> str | None:
    for c in (shutil.which("soffice"), shutil.which("libreoffice"),
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if c and Path(c).exists():
            return c
    return None


VISUAL_PROMPT = """Tu contrôles la mise en page de slides de cours (images ci-jointes, chacune précédée
de son numéro). Signale UNIQUEMENT les défauts visibles : texte qui déborde de sa zone ou de la slide,
texte coupé, éléments qui se chevauchent, tableau qui passe sous l'encadré « À retenir » ou le pied de
page, graphique illisible, étiquettes superposées. Ne commente pas le fond.
JSON : [{"slide": numéro, "probleme": str}]  ([] si tout est correct)"""


def visual_check(pptx_path: str, log=print) -> list[dict] | None:
    """Rend chaque slide en image et la fait relire. None si LibreOffice est absent."""
    soffice = _soffice()
    if not soffice:
        return None
    import pymupdf
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _convert(soffice, pptx_path, tmp)
        except Exception as e:
            log(f"⚠️ Rendu visuel impossible : {e}")
            return None
        pdf = next(Path(tmp).glob("*.pdf"), None)
        if not pdf:
            return None
        doc = pymupdf.open(pdf)
        images = [base64.b64encode(p.get_pixmap(dpi=55).tobytes("png")).decode() for p in doc]
    problems = []
    for k in range(0, len(images), 8):
        parts = []
        for n, img in enumerate(images[k:k + 8], k + 1):
            parts += [("text", f"Slide {n}"), ("image", img)]
        parts.append(("text", "Liste les défauts en JSON."))
        try:
            problems += parse_json(ask_with_images(VISUAL_PROMPT, parts)) or []
        except ValueError:
            pass
    log(f"👁️ Rendu visuel relu : {len(images)} slides, {len(problems)} défaut(s) signalé(s)")
    return problems


def thumbnails(pptx_path: str, max_n: int = 12, dpi: int = 45) -> list[bytes] | None:
    """Images PNG des premières slides (aperçu dans l'application). None si LibreOffice est absent."""
    soffice = _soffice()
    if not soffice:
        return None
    import pymupdf
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _convert(soffice, pptx_path, tmp)
            pdf = next(Path(tmp).glob("*.pdf"))
        except Exception:
            return None
        doc = pymupdf.open(pdf)
        return [doc[i].get_pixmap(dpi=dpi).tobytes("png") for i in range(min(max_n, len(doc)))]


def merge(*dicts) -> dict:
    out: dict = {}
    for d in dicts:
        for k, v in d.items():
            out.setdefault(k, []).extend(v)
    return out


def report(course: dict, fact: dict, layout: dict, visual: list | None, reopen: str | None,
           fixed: int, page_map: dict, extra: list[str] | None = None) -> str:
    inv = {v: k for k, v in page_map.items()}
    n_slides = sum(len(s["slides"]) for s in course["sections"])
    lines = [f"# Contrôle qualité — {course['titre']}", "",
             f"- Slides de contenu : {n_slides} ; slides corrigées automatiquement : {fixed}",
             f"- Ouverture du fichier : {'OK' if not reopen else reopen}",
             f"- Rendu visuel : {'non effectué (désactivé, ou LibreOffice absent)' if visual is None else f'{len(visual)} défaut(s) restant(s)'}",
             *(extra or []), ""]
    remaining = merge(fact, layout)
    if remaining:
        lines.append("## Points restant à vérifier")
        for (i, j), probs in sorted(remaining.items()):
            sl = course["sections"][i]["slides"][j]
            lines.append(f"- Slide {inv.get((i, j), '?')} « {sl.get('titre', '')} » : " + " ; ".join(probs))
    if visual:
        lines.append("## Défauts visuels signalés")
        lines += [f"- Slide {v.get('slide')} : {v.get('probleme')}" for v in visual]
    vig = [(inv.get((i, j), "?"), sl.get("titre", ""), sl["vigilance"])
           for i, sec in enumerate(course["sections"]) for j, sl in enumerate(sec["slides"]) if sl.get("vigilance")]
    if vig:
        lines.append("## Incohérences et informations non documentées signalées dans le cours")
        lines += [f"- Slide {n} « {t} » : {v}" for n, t, v in vig]
    if not remaining and not visual:
        lines.append("Aucun problème restant détecté.")
    return "\n".join(lines) + "\n"

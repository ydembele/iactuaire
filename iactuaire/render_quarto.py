"""Étape 5b (variante) — Polycopié PDF rédigé en Quarto et composé avec Typst.

Même contenu et même charte que le polycopié « Standard » (render_pdf.py) :
le cours est écrit dans un fichier `.qmd` (Markdown), puis Quarto le compose avec le
modèle de `templates/quarto/` (typst-template.typ + filtre iactuaire.lua).

Si Quarto n'est pas installé ou échoue, le pipeline revient au moteur Standard.
"""
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from . import theme as theme_mod
from .config import ROOT
from .render_pptx import MOIS

TEMPLATE_DIR = ROOT / "templates" / "quarto"
TEMPLATE_FILES = ("typst-template.typ", "typst-show.typ", "page.typ", "iactuaire.lua")


class QuartoError(RuntimeError):
    pass


def quarto_bin() -> str | None:
    """Quarto dans le PATH, ou à son emplacement d'installation habituel (macOS, Windows)."""
    for c in (shutil.which("quarto"), "/Applications/quarto/bin/quarto", "/usr/local/bin/quarto",
              "/opt/homebrew/bin/quarto", r"C:\Program Files\Quarto\bin\quarto.exe"):
        if c and Path(c).exists():
            return c
    return None


def available() -> bool:
    return quarto_bin() is not None and all((TEMPLATE_DIR / f).exists() for f in TEMPLATE_FILES)


# ---------------------------------------------------------------- Markdown sûr
_ESC = re.compile(r"([\\`*_\[\]{}<>#@~^|$&])")


def md(text) -> str:
    """Texte rédigé par l'IA → Markdown littéral (aucun caractère n'est interprété)."""
    s = str(text or "")
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", s) if p.strip()]
    out = []
    for p in paras:
        p = _ESC.sub(r"\\\1", p).replace("--", "-\\-")
        p = re.sub(r"^([-+:=>|])", r"\\\1", p)                   # puce, citation, bloc…
        p = re.sub(r"^(\d+)([.)])", r"\1\\\2", p)                # « 1. » en début de ligne
        out.append(p)
    return "\n\n".join(out)


def md1(text) -> str:
    """Une seule ligne (titres, cellules de tableau, puces)."""
    return md(text).replace("\n\n", " ")


def code(text) -> str:
    """Formule en chasse fixe : code en ligne, recopié tel quel."""
    s = " ".join(str(text or "").split())
    if not s:
        return ""
    ticks = "`" * (max((len(m) for m in re.findall(r"`+", s)), default=0) + 1)
    pad = " " if s.startswith("`") or s.endswith("`") else ""
    return f"{ticks}{pad}{s}{pad}{ticks}"


def url_md(u: str) -> str:
    u = str(u or "").strip()
    if not re.match(r"https?://", u):
        return md1(u)
    shown = md1(u).replace("/", "/​")                       # coupure possible après « / »
    dest = u.replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("<", "%3C").replace(">", "%3E")
    return f"[{shown}]({dest})"


def label(text, suffix: str = "") -> str:
    """Étiquette en gras (rouge) suivie d'une espace ; rien si le libellé est vide."""
    t = md1(text)
    return f"**{t}{suffix}** " if t else ""


def two_sentences(txt: str) -> str:
    return " ".join(re.split(r"(?<=[.!?])\s+", txt or "")[:2])


# ---------------------------------------------------------------- briques
def div(cls: str, body: str, **attrs) -> str:
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    head = f"{{.{cls}{' ' + a if a else ''}}}" if a else cls
    return f"::: {head}\n{body}\n:::"


def bullets(items) -> str:
    return "\n".join(f"- {md1(i)}" for i in items if str(i or "").strip())


def table(header, rows, widths=None) -> str:
    cell = lambda x: md1(x) or " "
    lines = ["| " + " | ".join(cell(h) for h in header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        r = list(r) + [""] * (len(header) - len(r))
        lines.append("| " + " | ".join(cell(c) for c in r[:len(header)]) + " |")
    t = "\n".join(lines)
    return div("tableau", t, largeurs=",".join(f"{w:g}" for w in widths)) if widths else t


# ---------------------------------------------------------------- contenu d'une slide
def slide_content(sl: dict, chart) -> list[str]:
    ty, out = sl.get("type"), []
    if ty == "colonnes":
        cols = [div("colonne", f"{label(c.get('titre'))}\n\n{bullets(c.get('points', []))}")
                for c in sl.get("colonnes", [])[:2]]
        out.append("::::: colonnes\n" + "\n\n".join(cols) + "\n:::::")
        if sl.get("encadre"):
            e = sl["encadre"]
            out.append(div("boite", f"{label(e.get('titre'), ' —')}{md1(e.get('texte'))}", fond="white"))
    elif ty == "cartes":
        out.append(table(["", "Notion", "En bref"],
                         [[str(i), c.get("titre"), c.get("texte")] for i, c in enumerate(sl.get("cartes", []), 1)],
                         [0.8, 4, 12.2]))
    elif ty == "etapes":
        out.append(table(["Étape", "Ce qui se passe"],
                         [[f"{i}. {e.get('titre', '')}", e.get("texte")] for i, e in enumerate(sl.get("etapes", []), 1)],
                         [4, 13]))
        if sl.get("texte"):
            out.append(md(sl["texte"]))
    elif ty == "formule":
        if sl.get("intro"):
            out.append(md(sl["intro"]))
        for f in sl.get("formules", []):
            body = f"{label(f.get('nom'))}\n\n{code(f.get('expression'))}"
            if f.get("legende"):
                body += "\n\n" + div("petit", md(f.get("legende")))
            out.append(div("boite", body, fond="panel"))
    elif ty == "tableau":
        if sl.get("intro"):
            out.append(md(sl["intro"]))
        out.append(table(sl.get("colonnes") or [""], sl.get("lignes", [])))
        if sl.get("commentaire"):
            out.append(div("petit", md(sl["commentaire"])))
    elif ty == "chiffres":
        items = []
        for x in sl.get("chiffres", [])[:4]:
            v = str(x.get("valeur") or "").replace('"', "”")
            lab = str(x.get("libelle") or "").replace('"', "”")
            items.append(f'::: {{.chiffre valeur="{v}" libelle="{lab}"}}\n:::')
        out.append("::::: chiffres\n" + "\n".join(items) + "\n:::::")
        if sl.get("texte"):
            out.append(md(sl["texte"]))
    elif ty == "graphique":
        if sl.get("intro"):
            out.append(md(sl["intro"]))
        img = chart(sl.get("graphique") or {})
        out.append(f"![]({img}){{width=100%}}" if img else div("petit", "(graphique non reproduit : données incomplètes)"))
        if sl.get("commentaire"):
            out.append(f"**Lecture —** {md1(sl['commentaire'])}")
    elif ty == "code":
        if sl.get("intro"):
            out.append(md(sl["intro"]))
        if sl.get("fichier"):
            out.append(div("petit", "Fichier : " + code(sl["fichier"])))
        src = (sl.get("code_poly") or sl.get("code") or "").replace("\t", "    ").rstrip("\n")
        fence = "`" * max(3, max((len(m) for m in re.findall(r"`+", src)), default=0) + 1)
        lang = re.sub(r"[^\w+-]", "", sl.get("langage") or "") or "text"
        out.append(f"{fence}{lang}\n{src}\n{fence}")
        if sl.get("commentaire"):
            out.append(f"**À noter —** {md1(sl['commentaire'])}")
    elif ty == "schema":
        sc = sl.get("schema") or {}
        names = {n["id"]: n.get("titre", n["id"]) for n in sc.get("noeuds", [])}
        out.append(table(["Élément", "Rôle"], [[n.get("titre"), n.get("texte")] for n in sc.get("noeuds", [])],
                         [4.5, 12.5]))
        if sc.get("liens"):
            out.append(md1("Enchaînement : " + " ; ".join(
                f"{names.get(l.get('de'), l.get('de'))} → {names.get(l.get('vers'), l.get('vers'))}"
                + (f" ({l['libelle']})" if l.get("libelle") else "") for l in sc["liens"])))
        if sl.get("commentaire"):
            out.append(div("petit", md(sl["commentaire"])))
    else:  # points
        out.append(bullets(sl.get("points", [])))
        if sl.get("encadre"):
            e = sl["encadre"]
            out.append(div("boite", f"{label(e.get('titre'), ' —')}{md1(e.get('texte'))}", fond="white"))
    return out


# ---------------------------------------------------------------- document
def _plain(s: str) -> str:
    return re.sub(r'["\\]', "", str(s or "")).strip()


def build_qmd(course: dict, level: int, chart) -> str:
    """Écrit le cours en Quarto Markdown. level : 0 aéré · 1 compact · 2 notes résumées · 3 notes et glossaire retirés."""
    t = theme_mod.load()
    n = sum(1 for b in course.get("bibliographie", []) if b.get("nature", "Mémoire") == "Mémoire")
    ligne = " · ".join(b for b in (t["auteur"], f"{MOIS[date.today().month - 1]} {date.today().year}",
                                   f"cas concrets tirés de {n} mémoires d'actuariat" if n else "") if b)
    meta = {
        "title": md1(course["titre"]),
        "lang": "fr",
        "format": {"typst": {"template-partials": list(TEMPLATE_FILES[:3]), "keep-typ": False,
                             "syntax-highlighting": "idiomatic"}},
        "filters": [TEMPLATE_FILES[3]],
        "iact": {
            "red": t["red"], "red-dark": t["red_dark"], "ink": t["ink"], "grey": t["grey"],
            "line": t["line"], "panel": t["panel"], "soft": t["soft"],
            "police": _plain(t.get("font")) or "Arial", "mono": _plain(t.get("mono")) or "Consolas",
            "corps": "10.5pt" if level == 0 else "9.5pt",
            "surtitre": "SUPPORT DE COURS", "ligne": md1(ligne), "pied": md1(course["titre"][:110]),
            "auteur": _plain(t["auteur"]), "credit": _plain(t["credit"]),
        },
    }
    if course.get("sous_titre"):
        meta["subtitle"] = md1(course["sous_titre"])
    if t.get("logo"):
        meta["iact"]["logo"] = "logo" + Path(t["logo"]).suffix
    if not meta["iact"]["auteur"]:
        del meta["iact"]["auteur"]

    parts = ["---\n" + json.dumps(meta, ensure_ascii=False, indent=1) + "\n---"]
    add = parts.append
    saut = "::: saut\n:::"
    besoin = lambda h: f'::: {{.besoin hauteur="{h}"}}\n:::'

    add("# Objectifs du cours")
    parts += [label(o.get("verbe")) + md1(o.get("texte")) for o in course.get("objectifs", [])]
    add("## Sommaire")
    parts += [f"**{i}.** {md1(sec['titre'])}" for i, sec in enumerate(course["sections"], 1)]
    if course.get("introduction") and level < 2:
        add("## Introduction")
        add(md(course["introduction"]))

    for i, sec in enumerate(course["sections"], 1):
        add(saut if level == 0 else besoin("8cm"))
        add(f"# {i}. {md1(sec['titre'])}")
        if sec.get("accroche"):
            add(div("petit", md(sec["accroche"])))
        for j, sl in enumerate(sec["slides"], 1):
            add(besoin("5cm"))
            add(f"## {i}.{j}  {md1(sl.get('titre', ''))}")
            if sl.get("notes") and level < 3:
                add(md(sl["notes"] if level < 2 else two_sentences(sl["notes"])))
            parts += slide_content(sl, chart)
            if sl.get("vigilance"):
                add(div("boite", f"**⚠ Point de vigilance —** {md1(sl['vigilance'])}", fond="white", barre="red-dark"))
            if sl.get("a_retenir"):
                add(div("boite", f"**À retenir** {md1(sl['a_retenir'])}", fond="soft"))
            if sl.get("sources"):
                add(div("petit", md1("Sources : " + ", ".join(sl["sources"]))))

    add(saut if level == 0 else besoin("8cm"))
    add("# Synthèse")
    add("## Les points clés")
    parts += [f"**{i}.** {md1(p)}" for i, p in enumerate(course.get("points_cles", []), 1)]
    if course.get("pour_aller_plus_loin"):
        add("## Pour aller plus loin")
        add(bullets(course["pour_aller_plus_loin"]))
    if course.get("conclusion") and level < 2:
        add("## Conclusion")
        add(md(course["conclusion"]))
    if course.get("glossaire") and level < 3:
        add(saut)
        add("# Glossaire")
        add(table(["Terme", "Définition", "Source"],
                  [[g.get("terme"), g.get("definition"), g.get("source")] for g in course["glossaire"]],
                  [3.8, 10.4, 2.8]))
    add(("## " if course.get("glossaire") and level < 3 else "# ") + "Toutes les sources")
    rows = [[b.get("id", ""), b.get("nature", ""), b.get("ref", ""), b.get("url", "")]
            for b in course.get("bibliographie", [])]
    lines = ["| Réf. | Nature | Référence | Lien |", "|---|---|---|---|"]
    lines += ["| " + " | ".join([md1(r[0]) or " ", md1(r[1]) or " ", md1(r[2]) or " ", url_md(r[3]) or " "]) + " |"
              for r in rows]
    add(div("tableau", "\n".join(lines), largeurs="1.1,2.4,7,6.5"))
    return "\n\n".join(parts) + "\n"


def render(course: dict, path: str, level: int = 0, timeout: int = 240) -> str:
    """Compose le polycopié avec Quarto. Lève QuartoError en cas d'échec."""
    from reportlab.graphics import renderPDF
    from reportlab.lib.units import cm
    from reportlab.lib.pagesizes import A4
    from . import render_pdf

    if not available():
        raise QuartoError("Quarto n'est pas installé")
    out = Path(path)
    work = out.parent / f"_quarto_{out.stem}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for f in TEMPLATE_FILES:
        shutil.copy(TEMPLATE_DIR / f, work / f)
    t = theme_mod.load()
    if t.get("logo"):
        shutil.copy(t["logo"], work / ("logo" + Path(t["logo"]).suffix))

    F = render_pdf._fonts()
    W = A4[0] - 4 * cm
    counter = iter(range(1, 10_000))

    def chart(g: dict) -> str | None:
        try:
            name = f"graphique-{next(counter)}.pdf"
            renderPDF.drawToFile(render_pdf.chart_drawing(g, t, F, W, level), str(work / name))
            return name
        except Exception:
            return None

    try:
        (work / "cours.qmd").write_text(build_qmd(course, level, chart), encoding="utf-8")
        try:
            p = subprocess.run([quarto_bin(), "render", "cours.qmd", "--to", "typst"], cwd=work,
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise QuartoError(f"Quarto n'a pas fini en {timeout} s")
        pdf = work / "cours.pdf"
        if p.returncode != 0 or not pdf.exists():
            err = [l for l in (p.stderr or p.stdout or "").splitlines() if l.strip() and "warning" not in l.lower()]
            raise QuartoError("Quarto a échoué : " + " | ".join(err[-4:])[:600])
        shutil.move(str(pdf), out)
        # source complète du polycopié (qmd + graphiques + modèle), recompilable avec `quarto render`
        keep = out.parent / f"{out.stem}_quarto"
        shutil.rmtree(keep, ignore_errors=True)
        shutil.copytree(work, keep, ignore=shutil.ignore_patterns("*.typ.bak", ".quarto", "*_files"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return str(out)


def render_fitted(course: dict, path: str, max_pages: int, log=print) -> tuple[str, int, int]:
    """Compose le polycopié en le compactant progressivement jusqu'à tenir dans `max_pages`."""
    import pymupdf
    pages, level = 0, 0
    for level in range(4):
        render(course, path, level)
        pages = len(pymupdf.open(path))
        if pages <= max_pages:
            break
        log(f"📄 Polycopié : {pages} pages pour {max_pages} autorisées → mise en page plus compacte")
    return path, pages, level

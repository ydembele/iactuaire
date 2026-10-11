"""Étape 5b — Polycopié PDF du cours (même charte que le PowerPoint, voir theme.py).

Chaque slide devient une sous-partie : le texte explicatif (notes du formateur),
puis le contenu de la slide, puis l'encadré « À retenir ».
"""
import re
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak, KeepTogether, ListFlowable, ListItem, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, BaseDocTemplate, Frame,
)

from . import theme as theme_mod
from .render_pptx import MOIS

# Polices Unicode (Σ, →, ≤…) : on prend la première disponible sur la machine.
_FONT_CANDIDATES = {
    "Body": ["/System/Library/Fonts/Supplemental/Arial.ttf", "C:/Windows/Fonts/arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "Body-Bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "Mono": ["/System/Library/Fonts/Supplemental/Courier New.ttf", "C:/Windows/Fonts/consola.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
}
_FALLBACK = {"Body": "Helvetica", "Body-Bold": "Helvetica-Bold", "Mono": "Courier"}


def _fonts() -> dict:
    out = {}
    for name, paths in _FONT_CANDIDATES.items():
        out[name] = _FALLBACK[name]
        for p in paths:
            if Path(p).exists():
                try:
                    pdfmetrics.registerFont(TTFont(name, p))
                    out[name] = name
                    break
                except Exception:
                    continue
    return out


def _two_sentences(txt: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", txt or "")
    return " ".join(parts[:2])


def render(course: dict, path: str, level: int = 0) -> str:
    """level 0 : mise en page aérée ; 1 : compacte ; 2 : notes résumées ; 3 : notes et glossaire retirés."""
    t = theme_mod.load()
    F = _fonts()
    RED, INK, GREY = (colors.HexColor("#" + t[k]) for k in ("red", "ink", "grey"))
    PANEL, SOFT, LINE = (colors.HexColor("#" + t[k]) for k in ("panel", "soft", "line"))
    W = A4[0] - 4 * cm

    st = {
        "body": ParagraphStyle("body", fontName=F["Body"], fontSize=10.5 if level == 0 else 9.5,
                               leading=15.5 if level == 0 else 13, textColor=INK,
                               spaceAfter=6),
        "small": ParagraphStyle("small", fontName=F["Body"], fontSize=8.5, leading=11, textColor=GREY),
        "h1": ParagraphStyle("h1", fontName=F["Body-Bold"], fontSize=20, leading=25, textColor=RED,
                             spaceBefore=4, spaceAfter=4),
        "h2": ParagraphStyle("h2", fontName=F["Body-Bold"], fontSize=13, leading=17, textColor=INK,
                             spaceBefore=14, spaceAfter=6),
        "label": ParagraphStyle("label", fontName=F["Body-Bold"], fontSize=10.5, leading=14, textColor=RED),
        "cell": ParagraphStyle("cell", fontName=F["Body"], fontSize=9, leading=12, textColor=INK),
        "cellh": ParagraphStyle("cellh", fontName=F["Body-Bold"], fontSize=9, leading=12, textColor=colors.white),
        "mono": ParagraphStyle("mono", fontName=F["Mono"], fontSize=10.5, leading=14, textColor=INK),
        "kpi": ParagraphStyle("kpi", fontName=F["Body-Bold"], fontSize=20, leading=24, textColor=RED,
                              alignment=TA_CENTER),
        "kpil": ParagraphStyle("kpil", fontName=F["Body"], fontSize=9, leading=12, textColor=INK,
                               alignment=TA_CENTER),
    }
    P = lambda txt, s="body": Paragraph(escape(str(txt or "")), st[s])
    B = lambda label, txt, s="body": Paragraph(
        f'<font name="{F["Body-Bold"]}" color="#{t["red"]}">{escape(label)}</font> {escape(str(txt or ""))}', st[s])

    def box(flowables, bg=PANEL, bar=RED, pad=8):
        tb = Table([[flowables]], colWidths=[W])
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 3, bar),
            ("LEFTPADDING", (0, 0), (-1, -1), pad + 4), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
            ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ]))
        return tb

    def bullets(items):
        return ListFlowable([ListItem(P(i), leftIndent=12, value="•") for i in items],
                            bulletType="bullet", bulletColor=RED, start="•", leftIndent=12)

    def grid(header, rows, widths=None):
        data = [[P(h, "cellh") for h in header]] + [[P(c, "cell") for c in r] for r in rows]
        n = len(header)
        tb = Table(data, colWidths=widths or [W / n] * n, repeatRows=1)
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), RED),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return tb

    def chart(g):
        """Graphique vectoriel natif du PDF (mêmes données que le PowerPoint)."""
        from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
        from reportlab.graphics.charts.legends import Legend
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
        from reportlab.graphics.charts.doughnut import Doughnut
        from reportlab.graphics.shapes import Drawing, String
        from .render_pptx import _num

        kind = g.get("type", "barres")
        cats = [str(c) for c in g.get("categories", [])]
        series = [[_num(v) for v in ser["valeurs"]][:len(cats)] for ser in g["series"]]
        names = [str(ser.get("nom", "")) for ser in g["series"]]
        pal = [colors.HexColor("#" + c) for c in (t["red"], t["ink"], t["grey"], t["red_dark"], "E8918D", "BDBDBD")]
        GH = 7.5 * cm if level == 0 else (6.2 * cm if level < 3 else 5.2 * cm)
        d = Drawing(W, GH)
        d.add(String(0, GH - 12, g.get("titre", ""), fontName=F["Body-Bold"], fontSize=10, fillColor=INK))
        if kind == "anneau":
            c = Doughnut()
            c.x, c.y, c.width, c.height = 1 * cm, 0.3 * cm, GH - 1.5 * cm, GH - 1.5 * cm
            c.data = series[0]
            total = sum(series[0]) or 1
            c.labels = [f"{v / total:.0%}" for v in series[0]]
            c.slices.fontName, c.slices.fontSize = F["Body"], 8
            for i in range(len(series[0])):
                c.slices[i].fillColor = pal[i % len(pal)]
                c.slices[i].strokeColor = colors.white
            d.add(c)
            lg = Legend()
            lg.x, lg.y = GH + 1 * cm, GH - 2 * cm
            lg.fontName, lg.fontSize = F["Body"], 8.5
            lg.colorNamePairs = [(pal[i % len(pal)], f"{cats[i]} ({v:g})") for i, v in enumerate(series[0])]
            d.add(lg)
            return d
        if kind == "courbes":
            c = HorizontalLineChart()
            c.data = series
            for i in range(len(series)):
                c.lines[i].strokeColor = pal[i % len(pal)]
                c.lines[i].strokeWidth = 1.8
        else:
            c = HorizontalBarChart() if kind == "barres_h" else VerticalBarChart()
            if kind == "cascade":
                vals, totals = series[0], set(g.get("totaux") or [])
                base, vis, running = [], [], 0.0
                for i, v in enumerate(vals):
                    if i in totals:
                        base.append(0); vis.append(v); running = v
                    else:
                        base.append(min(running, running + v)); vis.append(abs(v)); running += v
                c.data = [base, vis]
                c.categoryAxis.style = "stacked"
                c.bars[0].fillColor = colors.white
                c.bars[0].strokeColor = None
                c.bars[1].strokeColor = None
                for i, v in enumerate(vals):
                    c.bars[(1, i)].fillColor = INK if i in totals else (RED if v > 0 else GREY)
                names = []
            else:
                c.data = series
                for i in range(len(series)):
                    c.bars[i].fillColor = pal[i % len(pal)]
                    c.bars[i].strokeColor = None
        c.x, c.y, c.width, c.height = 1.6 * cm, 1.4 * cm, W - 2.2 * cm, GH - 2.3 * cm
        c.categoryAxis.categoryNames = cats
        for ax in (c.categoryAxis, c.valueAxis):
            ax.labels.fontName, ax.labels.fontSize = F["Body"], 8
        c.valueAxis.gridStrokeColor = LINE
        c.valueAxis.visibleGrid = True
        if kind == "barres_h":
            c.categoryAxis.labels.boxAnchor = "e"
        d.add(c)
        if len(names) > 1:
            lg = Legend()
            lg.x, lg.y = 1.6 * cm, 0.4 * cm
            lg.alignment, lg.columnMaximum = "right", 1
            lg.fontName, lg.fontSize = F["Body"], 8
            lg.colorNamePairs = [(pal[i % len(pal)], n) for i, n in enumerate(names)]
            d.add(lg)
        return d

    # ------------------------------------------------------------- contenu des slides
    def slide_content(sl):
        ty, out = sl.get("type"), []
        if ty == "colonnes":
            cols = sl.get("colonnes", [])[:2]
            cells = [[P(c.get("titre"), "label"), Spacer(1, 4), bullets(c.get("points", []))] for c in cols]
            tb = Table([cells], colWidths=[W / max(len(cols), 1)] * len(cols))
            tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("LINEABOVE", (0, 0), (-1, 0), 2, RED), ("LINEAFTER", (0, 0), (0, 0), 6, colors.white),
                                    ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
            out.append(tb)
            if sl.get("encadre"):
                e = sl["encadre"]
                out += [Spacer(1, 6), box([B(e.get("titre", "") + " —", e.get("texte"))], bg=colors.white)]
        elif ty == "cartes":
            out.append(grid(["", "Notion", "En bref"],
                            [[str(i), c.get("titre"), c.get("texte")] for i, c in enumerate(sl.get("cartes", []), 1)],
                            [0.8 * cm, 4 * cm, W - 4.8 * cm]))
        elif ty == "etapes":
            out.append(grid(["Étape", "Ce qui se passe"],
                            [[f"{i}. {e.get('titre', '')}", e.get("texte")] for i, e in enumerate(sl.get("etapes", []), 1)],
                            [4 * cm, W - 4 * cm]))
            if sl.get("texte"):
                out += [Spacer(1, 4), P(sl["texte"])]
        elif ty == "formule":
            if sl.get("intro"):
                out.append(P(sl["intro"]))
            for f in sl.get("formules", []):
                out += [box([P(f.get("nom"), "label"), Spacer(1, 3), P(f.get("expression"), "mono"),
                             Spacer(1, 3), P(f.get("legende"), "small")]), Spacer(1, 5)]
        elif ty == "tableau":
            if sl.get("intro"):
                out.append(P(sl["intro"]))
            out.append(grid(sl.get("colonnes", [""]), sl.get("lignes", [])))
            if sl.get("commentaire"):
                out += [Spacer(1, 4), P(sl["commentaire"], "small")]
        elif ty == "chiffres":
            k = sl.get("chiffres", [])[:4]
            cells = [[P(x.get("valeur"), "kpi"), P(x.get("libelle"), "kpil")] for x in k]
            tb = Table([cells], colWidths=[W / max(len(k), 1)] * len(k))
            tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LINEBELOW", (0, 0), (-1, -1), 2, RED),
                                    ("LINEAFTER", (0, 0), (-2, -1), 6, colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
            out.append(tb)
            if sl.get("texte"):
                out += [Spacer(1, 4), P(sl["texte"])]
        elif ty == "graphique":
            if sl.get("intro"):
                out.append(P(sl["intro"]))
            try:
                out.append(chart(sl.get("graphique") or {}))
            except Exception:
                out.append(P("(graphique non reproduit : données incomplètes)", "small"))
            if sl.get("commentaire"):
                out += [Spacer(1, 4), B("Lecture —", sl["commentaire"])]
        elif ty == "schema":
            sc = sl.get("schema") or {}
            names = {n["id"]: n.get("titre", n["id"]) for n in sc.get("noeuds", [])}
            out.append(grid(["Élément", "Rôle"], [[n.get("titre"), n.get("texte")] for n in sc.get("noeuds", [])],
                            [4.5 * cm, W - 4.5 * cm]))
            if sc.get("liens"):
                out += [Spacer(1, 4), P("Enchaînement : " + " ; ".join(
                    f"{names.get(l.get('de'), l.get('de'))} → {names.get(l.get('vers'), l.get('vers'))}"
                    + (f" ({l['libelle']})" if l.get("libelle") else "") for l in sc["liens"]))]
            if sl.get("commentaire"):
                out.append(P(sl["commentaire"], "small"))
        else:  # points
            out.append(bullets(sl.get("points", [])))
            if sl.get("encadre"):
                e = sl["encadre"]
                out += [Spacer(1, 4), box([B(e.get("titre", "") + " —", e.get("texte"))], bg=colors.white)]
        return out

    # ------------------------------------------------------------- mise en page
    def cover(c, doc):
        c.saveState()
        c.setFillColor(RED)
        c.rect(0, 0, 1.2 * cm, A4[1], stroke=0, fill=1)
        if t["logo"]:
            c.drawImage(t["logo"], A4[0] - 6 * cm, A4[1] - 3.2 * cm, height=1.6 * cm, width=4 * cm,
                        preserveAspectRatio=True, anchor="ne", mask="auto")
        c.restoreState()

    def page(c, doc):
        c.saveState()
        c.setFillColor(RED)
        c.rect(2 * cm, A4[1] - 1.35 * cm, 1.2 * cm, 0.12 * cm, stroke=0, fill=1)
        if t["logo"]:
            c.drawImage(t["logo"], A4[0] - 5 * cm, A4[1] - 1.7 * cm, height=0.8 * cm, width=3 * cm,
                        preserveAspectRatio=True, anchor="ne", mask="auto")
        c.setStrokeColor(LINE)
        c.line(2 * cm, 1.5 * cm, A4[0] - 2 * cm, 1.5 * cm)
        c.setFont(F["Body"], 8)
        c.setFillColor(GREY)
        c.drawString(2 * cm, 1.05 * cm, course["titre"][:110])
        c.drawRightString(A4[0] - 2 * cm, 1.05 * cm, str(doc.page))
        c.restoreState()

    doc = BaseDocTemplate(path, pagesize=A4, title=course["titre"], author=t["auteur"] or "IActuaire",
                          creator=t["credit"])
    frame = Frame(2 * cm, 2 * cm, W, A4[1] - 4.2 * cm, id="f")
    doc.addPageTemplates([PageTemplate("cover", [Frame(2.5 * cm, 2 * cm, A4[0] - 4.5 * cm, A4[1] - 4 * cm)],
                                       onPage=cover),
                          PageTemplate("page", [frame], onPage=page)])

    n = sum(1 for b in course.get("bibliographie", []) if b.get("nature", "Mémoire") == "Mémoire")
    story = [Spacer(1, 6 * cm), P("SUPPORT DE COURS", "label"), Spacer(1, 8),
             Paragraph(escape(course["titre"]), ParagraphStyle("t", parent=st["h1"], fontSize=28, leading=34,
                                                               textColor=INK)),
             Spacer(1, 10), P(course.get("sous_titre")), Spacer(1, 3 * cm),
             P(" · ".join(b for b in (t["auteur"], f"{MOIS[date.today().month - 1]} {date.today().year}",
                                      f"cas concrets tirés de {n} mémoires d'actuariat") if b), "small"),
             NextPageTemplate("page"), PageBreak()]

    # Objectifs + sommaire
    story += [P("Objectifs du cours", "h1")]
    story += [B(o.get("verbe", ""), o.get("texte")) for o in course.get("objectifs", [])]
    story += [P("Sommaire", "h2")]
    story += [B(f"{i}.", sec["titre"]) for i, sec in enumerate(course["sections"], 1)]
    if course.get("introduction") and level < 2:
        story += [P("Introduction", "h2"), P(course["introduction"])]

    for i, sec in enumerate(course["sections"], 1):
        story += [PageBreak() if level == 0 else CondPageBreak(8 * cm), P(f"{i}. {sec['titre']}", "h1"), P(sec.get("accroche"), "small"), Spacer(1, 6)]
        for j, sl in enumerate(sec["slides"], 1):
            block = [P(f"{i}.{j}  {sl.get('titre', '')}", "h2")]
            if sl.get("notes") and level < 3:
                block.append(P(sl["notes"] if level < 2 else _two_sentences(sl["notes"])))
            block += slide_content(sl)
            if sl.get("vigilance"):
                block += [Spacer(1, 6), box([B("⚠ Point de vigilance —", sl["vigilance"])], bg=colors.white,
                                            bar=colors.HexColor("#" + t["red_dark"]))]
            if sl.get("a_retenir"):
                block += [Spacer(1, 6), box([B("À retenir", sl["a_retenir"])], bg=SOFT)]
            if sl.get("sources"):
                block += [Spacer(1, 3), P("Sources : " + ", ".join(sl["sources"]), "small")]
            story += [CondPageBreak(5 * cm), KeepTogether(block[:3]), *block[3:]]

    story += [PageBreak() if level == 0 else CondPageBreak(8 * cm), P("Synthèse", "h1"), P("Les points clés", "h2")]
    story += [B(f"{i}.", p) for i, p in enumerate(course.get("points_cles", []), 1)]
    if course.get("pour_aller_plus_loin"):
        story += [P("Pour aller plus loin", "h2"), bullets(course["pour_aller_plus_loin"])]
    if course.get("conclusion") and level < 2:
        story += [P("Conclusion", "h2"), P(course["conclusion"])]
    if course.get("glossaire") and level < 3:
        story += [PageBreak(), P("Glossaire", "h1"),
                  grid(["Terme", "Définition", "Source"],
                       [[g.get("terme"), g.get("definition"), g.get("source")] for g in course["glossaire"]],
                       [3.8 * cm, W - 6.6 * cm, 2.8 * cm])]
    story += [P("Toutes les sources", "h1" if not course.get("glossaire") else "h2"),
              grid(["Réf.", "Nature", "Référence", "Lien"],
                   [[b["id"], b.get("nature", ""), b["ref"], b["url"]] for b in course.get("bibliographie", [])],
                   [1.1 * cm, 2.4 * cm, 7 * cm, W - 10.5 * cm])]
    doc.build(story)
    return path


def render_fitted(course: dict, path: str, max_pages: int, log=print) -> tuple[str, int, int]:
    """Rend le polycopié en le compactant progressivement jusqu'à tenir dans `max_pages`."""
    import pymupdf
    pages = 0
    for level in range(4):
        render(course, path, level)
        pages = len(pymupdf.open(path))
        if pages <= max_pages:
            break
        log(f"📄 Polycopié : {pages} pages pour {max_pages} autorisées → mise en page plus compacte")
    return path, pages, level

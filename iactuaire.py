"""IActuaire — se former à n'importe quel sujet d'actuariat financier, à partir de sources fiables.

Lancer :  streamlit run iactuaire.py
"""
import html
import json
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from iactuaire import config, db, llm, pipeline, qa, render_quarto, runtime, settings, synthesis
from iactuaire import theme as theme_mod
from iactuaire.orchestrator import EXPERTS, PALETTE, ecole_courte, figure, run_turn
from iactuaire.settings import SOURCES
from iactuaire.synthesis import CourseRequest

st.set_page_config(page_title="IActuaire", page_icon="🎓", layout="wide")

# --------------------------------------------------------------------------- style
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root { --ink:#ECE6DA; --muted:#9FB0B8; --petrol:#0F1B24; --surface:#152530; --line:#27404D;
        --red:#C21B17; --brass:#B89B5E; }
html, body, [class*="css"], .stMarkdown, .stTextInput, .stButton, .stTabs { font-family: 'IBM Plex Sans', sans-serif; }
.block-container { max-width: 1180px; padding-top: 2.4rem; }
[data-testid="stSidebar"] { background: #0B151C; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] h2 { font-family: 'Newsreader', serif; font-weight: 500; font-size: 1.5rem; }
[data-testid="stSidebar"] h3 { font-size: .95rem; color: var(--brass); font-weight: 600; margin: 1.2rem 0 .2rem; }
[data-testid="stSidebar"] [data-testid="stExpander"] details { border: none; border-bottom: 1px solid var(--line);
        border-radius: 0; background: transparent; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary { padding: .7rem 0; background: transparent !important; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary p { font-family: 'Newsreader', serif; font-size: 1.12rem;
        color: var(--brass); }
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] { padding: 0 0 .8rem 0; }
h1, h2, h3 { font-family: 'Newsreader', serif !important; font-weight: 500 !important; letter-spacing: -.01em; }
.brand { font-family: 'Newsreader', serif; font-size: 1.9rem; font-weight: 500; letter-spacing: -.01em;
         color: var(--ink); margin: -.6rem 0 .4rem; }
.brand span { color: var(--red); }
.hero { font-family: 'Newsreader', serif; font-size: 3.4rem; line-height: 1.05; font-weight: 400;
        margin: .6rem 0 .5rem; color: var(--ink); }
.lede { color: var(--muted); font-size: 1.05rem; max-width: 62ch; margin-bottom: 1.6rem; }
[data-testid="stMain"] .stTextInput input { font-family: 'Newsreader', serif; font-size: 1.45rem;
        padding: .9rem 1rem; background: transparent; border: none; border-bottom: 2px solid var(--brass);
        border-radius: 0; }
[data-testid="stMain"] .stTextInput input:focus { border-bottom-color: var(--red); box-shadow: none; }
.stButton button[kind="primary"] { border-radius: 4px; font-weight: 600; padding: .55rem 1.4rem; }
.course-title { font-family: 'Newsreader', serif; font-size: 2.3rem; line-height: 1.12; margin: .4rem 0 .3rem; }
.course-sub { color: var(--muted); max-width: 75ch; }
.spec { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--line);
        border-top: 2px solid var(--brass); margin: 1.4rem 0 1.2rem; }
.spec div { background: var(--petrol); padding: .8rem .9rem; }
.spec b { display: block; font-family: 'Newsreader', serif; font-size: 1.7rem; font-weight: 500; color: var(--ink); }
.spec span { color: var(--muted); font-size: .82rem; }
.spec .over b { color: #F0837F; }
.muted { color: var(--muted); font-size: .9rem; }
.sec { font-family: 'Newsreader', serif; font-size: 1.25rem; margin: 1rem 0 .3rem; }
.slide-line { padding: .25rem 0 .25rem 1rem; border-left: 2px solid var(--line); color: var(--ink); }
.slide-line small { color: var(--muted); }
.expert { font-weight: 600; color: var(--brass); margin: .8rem 0 .3rem; }
.live-head { display: flex; justify-content: space-between; align-items: baseline; }
.live-title { font-family: 'Newsreader', serif; font-size: 1.5rem; }
.live-time { color: var(--muted); font-size: .9rem; font-variant-numeric: tabular-nums; }
.live-steps { display: flex; flex-wrap: wrap; gap: .3rem 1.1rem; margin: .5rem 0 .2rem; font-size: .84rem; }
.live-steps .st { color: #5E7480; }
.live-steps .st.ok { color: var(--brass); }
.live-steps .st.on { color: var(--ink); font-weight: 600; border-bottom: 2px solid var(--red); }
.live-counts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: .6rem 0 .4rem; }
.live-counts b { display: block; font-family: 'Newsreader', serif; font-size: 1.6rem; font-weight: 500; }
.live-counts span { color: var(--muted); font-size: .8rem; }
.live-now { color: var(--ink); font-size: .95rem; padding: .5rem 0 .2rem; border-top: 1px solid var(--line); }
.live-src { margin-top: .4rem; font-size: .86rem; }
.live-src > div { color: var(--muted); margin-bottom: .2rem; }
.live-src ul { list-style: none; padding: 0; margin: 0; }
.live-src li { display: flex; justify-content: space-between; gap: 1rem; padding: .15rem 0;
               border-bottom: 1px solid #1E3340; }
.live-src em { color: var(--brass); font-style: normal; white-space: nowrap; }
.credit { color: #5E7480; font-size: .78rem; margin-top: 1.2rem; }
@media (max-width: 800px) { .hero { font-size: 2.3rem; } .spec { grid-template-columns: repeat(2, 1fr); } }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------- session
# Chaque visiteur a son propre contexte (clé API, modèles, dossier de cours), jamais partagé.
# En public, l'identifiant du dossier de cours est gardé dans l'adresse (?s=…) : si la connexion se coupe
# pendant une création (onglet en veille, réseau, redémarrage), la page rechargée retrouve ses cours.
if type(st.session_state.get("rt")) is not runtime.Runtime:   # nouvelle session (ou ancienne version)
    if config.LOCAL:
        out = config.OUTPUT_BASE
    else:
        sid = str(st.query_params.get("s", ""))
        if not re.fullmatch(r"[0-9a-f]{16}", sid) or not (config.OUTPUT_BASE / "sessions" / sid).is_dir():
            sid = uuid.uuid4().hex[:16]
        out = config.OUTPUT_BASE / "sessions" / sid
        st.query_params["s"] = sid
    st.session_state.rt = runtime.Runtime(out_dir=out)
rt: runtime.Runtime = runtime.activate(st.session_state.rt)


@st.cache_resource(ttl=3600, show_spinner=False)
def _housekeeping(_hour: int):
    """Serveur public : efface les cours des sessions de plus de 24 h et limite le cache de PDF à 1,5 Go."""
    if config.LOCAL:
        return
    now = time.time()
    for d in (config.OUTPUT_BASE / "sessions").glob("*"):
        if now - d.stat().st_mtime > 86400:
            shutil.rmtree(d, ignore_errors=True)
    pdfs = sorted(config.PDF_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in pdfs)
    while pdfs and total > 1.5e9:
        old = pdfs.pop(0)
        total -= old.stat().st_size
        old.unlink(missing_ok=True)


_housekeeping(int(time.time() // 3600))


@st.cache_data(ttl=3600, show_spinner=False)
def _models(provider: str, key: str) -> list[str]:
    return llm.list_models(provider, key)


# --------------------------------------------------------------------------- paramètres
_fields = settings.Reglages.__dataclass_fields__
_old = st.session_state.get("reglages")
if _old is None:
    st.session_state.reglages = settings.charger()
elif type(_old) is not settings.Reglages or any(not hasattr(_old, f) for f in _fields):
    # session ouverte avant une mise à jour de l'application : on reprend ses réglages dans le nouveau format
    st.session_state.reglages = settings.Reglages(**{f: getattr(_old, f) for f in _fields if hasattr(_old, f)})
r: settings.Reglages = st.session_state.reglages

with st.sidebar:
    st.header("Paramètres")

    # Accès à l'IA : la clé de l'utilisateur, gardée dans sa session uniquement
    key_ok = llm.has_key() and (config.LOCAL and not rt.api_key)   # clé du .env en usage local
    models: list[str] = []
    with st.expander("Votre accès IA", expanded=not st.session_state.get("key_valid")):
        names = {k: v["nom"] for k, v in runtime.PROVIDERS.items()}
        provider = st.radio("Fournisseur", list(names), format_func=names.get, horizontal=True,
                            index=list(names).index(rt.provider), label_visibility="collapsed")
        if provider != rt.provider:
            rt.provider, rt.api_key = provider, ""
            st.session_state.key_valid = False
        typed = st.text_input(f"Clé API {names[provider]}", type="password", key=f"key_{provider}",
                              placeholder=runtime.PROVIDERS[provider]["cle"] + "…")
        rt.api_key = typed.strip()
        if rt.api_key:
            try:
                models = _models(provider, rt.api_key)
                key_ok = True
                st.caption(f"✓ Clé valide · {len(models)} modèles disponibles")
            except Exception as e:
                key_ok = False
                st.error("Clé refusée par " + names[provider] + f" ({type(e).__name__}).")
        elif key_ok:
            try:
                models = _models(provider, "")      # liste interrogée avec la clé du .env
                st.caption(f"✓ Clé du fichier .env utilisée · {len(models)} modèles disponibles")
            except Exception as e:
                key_ok = False
                st.error("Clé du fichier .env refusée par " + names[provider] + f" ({type(e).__name__}).")
        st.caption(f"Pas encore de clé ? [La créer ici]({runtime.PROVIDERS[provider]['obtenir']}). "
                   "Elle reste dans votre session : ni enregistrée, ni partagée. Votre fournisseur vous "
                   "facture directement chaque cours. Un abonnement ChatGPT Plus ou Claude Pro "
                   "ne suffit pas : il faut une clé API.")
    st.session_state.key_valid = key_ok

    # Blocs repliables (titres fixes : un titre qui change refermerait le bloc à chaque réglage)
    with st.expander("Modèle d'IA", expanded=True):
        smart_def, fast_def = llm.default_models(provider, models)
        options = models or [smart_def, fast_def]
        pick = lambda cur, d: options.index(cur) if cur in options else options.index(d)
        r.modele = st.selectbox("Rédaction du cours", options, index=pick(r.modele, smart_def))
        r.modele_lecture = st.selectbox("Lecture des sources", options, index=pick(r.modele_lecture, fast_def))

    with st.expander("Format du cours", expanded=True):
        r.max_slides = st.slider("Slides PowerPoint (maximum)", 10, 100, r.max_slides,
                                 help="Toutes slides comprises : couverture, intercalaires, glossaire, sources.")
        r.max_pages_pdf = st.slider("Pages du polycopié PDF (maximum)", 4, 120, r.max_pages_pdf)
        moteurs = {"quarto": "Quarto", "standard": "Standard"}
        r.moteur_pdf = st.radio("Mise en page du polycopié", list(moteurs), format_func=moteurs.get, horizontal=True,
                                index=list(moteurs).index(r.moteur_pdf if r.moteur_pdf in moteurs else "quarto"),
                                help="Quarto compose le polycopié avec Typst (modèle modifiable dans templates/quarto/). "
                                     "Standard : moteur intégré. En cas d'échec de Quarto, Standard prend le relais.")
        if r.moteur_pdf == "quarto" and not render_quarto.available():
            st.caption("Quarto n'est pas installé ici : le moteur Standard sera utilisé.")
        r.auteur = st.text_input("Votre nom (couverture)", value=r.auteur or theme_mod.load()["auteur"],
                                 placeholder="facultatif")

    with st.expander("Lecture des sources"):
        r.min_memoires, r.max_memoires = st.slider("Mémoires à lire (minimum – maximum)", 0, 40,
                                                   (min(r.min_memoires, r.max_memoires), r.max_memoires))
        if r.max_memoires == 0:
            r.max_memoires = 1
        chosen = st.multiselect("Sources autorisées", list(SOURCES), default=[k for k in r.sources if k in SOURCES],
                                format_func=lambda k: SOURCES[k]["nom"])
        r.sources = chosen or ["memoires"]
        r.max_docs_officiels = st.slider("Documents officiels lus en entier (maximum)", 0, 10, r.max_docs_officiels,
                                         disabled=not r.officiels())
        r.seuil_pertinence = st.slider("Pertinence minimale d'une source (/10)", 3, 9, r.seuil_pertinence)

    TEAM = config.LOCAL and provider == "anthropic"   # équipe d'experts : usage local, avec Claude
    with st.expander("Qualité"):
        r.controle_visuel = st.toggle("Relecture visuelle de chaque slide", value=r.controle_visuel,
                                      help="Nécessite LibreOffice. Ajoute quelques minutes.")
        memory = st.toggle("Mémoire de conversation (équipe d'experts)", value=True) if TEAM else False

    r.apply()
    settings.sauver(r)
    minutes = 2 + 0.6 * r.max_memoires + 0.8 * r.max_docs_officiels + r.max_slides / 6 + (3 if r.controle_visuel else 0)
    st.caption(f"Durée indicative d'un cours : {int(minutes * 0.7)} à {int(minutes * 1.3)} minutes.")
    st.caption(f"Bibliothèque commune : {db.stats().get('lu', 0)} mémoires déjà lus.")
    st.markdown('<div class="credit">IActuaire · conçu par Youssouf Dembélé</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- progression
class LivePanel:
    """Suivi en direct de la création d'un cours : étapes, compteurs, activité, sources lues."""
    STEPS = ["Recherche des mémoires", "Lecture des mémoires", "Textes officiels", "Plan du cours",
             "Rédaction des slides", "Contrôle qualité", "Mise en page"]
    ROUTE = [("🧠", 0), ("🌐", 0), ("🔎", 0), ("📚 ", 0), ("🧭", 1), ("📖", 1), ("📗", 1), ("⛔ Ignoré", 1),
             ("📊", 1), ("✅", 1),
             ("🏛️", 2), ("📘", 2), ("⛔ Document", 2), ("📐", 3), ("✍️ Rédaction du cours", 3), ("📚 Contexte", 3),
             ("🗺️", 3), ("✍️ Section", 4), ("🎓", 4), ("✂️", 4), ("🔍", 5), ("🛠️", 5), ("👁️", 5),
             ("📄", 6), ("📦", 7)]

    def __init__(self, r: settings.Reglages):
        self.r, self.t0, self.step, self.lines = r, time.time(), 0, []
        self.lus = self.ignores = self.officiels = self.ecrites = self.prevues = self.corrections = 0
        self.pertinents = 0
        self.pending = 0   # slides du lot en cours d'écriture (comptées une fois le lot terminé)
        self.sources: list[tuple[str, str]] = []
        box = st.container(border=True)
        self.head, self.bar, self.counts, self.now, self.srcs = (box.empty(), box.progress(0.0), box.empty(),
                                                                 box.empty(), box.empty())
        with box.expander("Journal détaillé"):
            self.journal = st.empty()
        self.render("Démarrage…")

    def __call__(self, msg: str):
        self.lines.append(msg)
        m = msg.strip()
        for key, idx in self.ROUTE:
            if m.startswith(key):
                self.step = max(self.step, idx)
                break
        if m.startswith(("📖", "📗")):
            self.lus += 1
            score = re.search(r"pertinence (\d+)/10", m)
            if score and int(score.group(1)) >= self.r.seuil_pertinence:
                self.pertinents += 1
            title = m.split(" : ", 1)[-1]
            self.sources.append((title, f"{score.group(1)}/10" if score else ""))
        elif m.startswith("⛔ Ignoré"):
            self.ignores += 1
        elif m.startswith("📘"):
            score = re.search(r"pertinence (\d+)/10", m)
            self.sources.append((m[2:].split(" (")[0].strip(), f"{score.group(1)}/10" if score else ""))
        elif re.search(r"(\d+) document\(s\) officiel\(s\) retenu", m):
            self.officiels = int(re.search(r"(\d+) document", m).group(1))
        elif re.search(r"(\d+) slides de contenu prévues", m):
            self.prevues = int(re.search(r"(\d+) slides de contenu", m).group(1))
        elif m.startswith("✍️ Section"):
            rng = re.search(r"slides (\d+)-(\d+)", m)
            self.ecrites += self.pending
            self.pending = int(rng.group(2)) - int(rng.group(1)) + 1 if rng else 0
        elif m.startswith("🛠️"):
            self.corrections += 1
        if m.startswith(("🎓", "🔍", "📦")):   # fin de la rédaction : le dernier lot est écrit
            self.ecrites += self.pending
            self.pending = 0
        self.render(m)

    def _progress(self) -> float:
        base = [0.0, .06, .40, .50, .55, .86, .95, 1.0][min(self.step, 7)]
        if self.step == 1:
            base += .34 * min(1, self.pertinents / max(self.r.max_memoires, 1))
        if self.step == 4 and self.prevues:
            base += .31 * min(1, self.ecrites / self.prevues)
        return min(base, 1.0)

    def render(self, current: str):
        sec = int(time.time() - self.t0)
        elapsed = f"{sec // 60} min {sec % 60:02d} s" if sec >= 60 else f"{sec} s"
        done = self.step >= 7
        label = "Cours prêt" if done else self.STEPS[self.step]
        steps = "".join(
            f'<span class="st {"ok" if i < self.step or done else ("on" if i == self.step else "")}">'
            f'{"✓ " if i < self.step or done else ""}{html.escape(s_)}</span>' for i, s_ in enumerate(self.STEPS))
        self.head.markdown(
            f'<div class="live-head"><span class="live-title">{html.escape(label)}</span>'
            f'<span class="live-time">{elapsed}</span></div><div class="live-steps">{steps}</div>',
            unsafe_allow_html=True)
        self.bar.progress(self._progress())
        slides = f"{self.ecrites} / {self.prevues}" if self.prevues else "–"
        self.counts.markdown(
            '<div class="live-counts">'
            f'<div><b>{self.pertinents} / {self.r.max_memoires}</b><span>mémoires pertinents, sur {self.lus} lus'
            f'{f", {self.ignores} inaccessible" + ("s" if self.ignores > 1 else "") if self.ignores else ""}</span></div>'
            f'<div><b>{self.officiels}</b><span>textes officiels retenus</span></div>'
            f'<div><b>{slides}</b><span>slides rédigées</span></div>'
            f'<div><b>{self.corrections}</b><span>corrections qualité</span></div></div>', unsafe_allow_html=True)
        if not done:
            clean = re.sub(r"^[^\wÀ-ÿ«(]+", "", current).strip()
            self.now.markdown(f'<div class="live-now">{html.escape(clean[:160])}</div>', unsafe_allow_html=True)
        else:
            self.now.empty()
        if self.sources:
            items = "".join(f"<li>{html.escape(t[:95])}<em>{html.escape(sc)}</em></li>"
                            for t, sc in self.sources[-6:][::-1])
            self.srcs.markdown(f'<div class="live-src"><div>Dernières sources lues</div><ul>{items}</ul></div>',
                               unsafe_allow_html=True)
        self.journal.markdown("\n".join(f"- {html.escape(l)}" for l in self.lines[-200:]) or "…")


# --------------------------------------------------------------------------- fiche d'un cours
def spec_grid(stats: dict) -> str:
    cells = [
        (f"{stats.get('slides', '–')}", f"slides sur {stats.get('max_slides', '–')} autorisées",
         stats.get("slides", 0) > stats.get("max_slides", 10 ** 6)),
        (f"{stats.get('pages_pdf', '–')}", f"pages de polycopié sur {stats.get('max_pages_pdf', '–')}",
         stats.get("pages_pdf", 0) > stats.get("max_pages_pdf", 10 ** 6)),
        (f"{stats.get('memoires_lus', '–')}", f"mémoires lus, {stats.get('memoires_retenus', '–')} retenus", False),
        (f"{stats.get('docs_officiels', 0)}", "textes officiels lus en entier", False),
        (f"{stats.get('corrections', 0)}", "corrections du contrôle qualité", False),
    ]
    return '<div class="spec">' + "".join(
        f'<div class="{"over" if over else ""}"><b>{html.escape(v)}</b><span>{html.escape(l)}</span></div>'
        for v, l, over in cells) + "</div>"


def downloads(files: list[tuple[str, str]], key: str):
    cols = st.columns(len(files))
    for i, (label, path) in enumerate(files):
        if path and Path(path).exists():
            cols[i].download_button(label, Path(path).read_bytes(), file_name=Path(path).name, key=f"{key}{i}",
                                    type="primary" if i == 0 else "secondary", width="stretch")


def cartographie(examined: list, retained: list, key: str):
    """Graphiques sur les mémoires lus pour ce cours, calculés à partir de leurs fiches (sans IA)."""
    lus = [e for e in (examined or retained) if e.get("fiche")]
    if not lus:
        st.markdown('<p class="muted">Aucun mémoire lu pour ce cours.</p>', unsafe_allow_html=True)
        return
    kept = {m["url"] for m in retained}
    rows = []
    for e in lus:
        f = e["fiche"]
        rows.append({"Mémoire": (f.get("titre") or e.get("titre") or "")[:60], "url": e["url"],
                     "Pertinence /10": e.get("score") or 0, "Retenu": "Retenu" if e["url"] in kept else "Écarté",
                     "École": ecole_courte(f.get("ecole")), "Année": f.get("annee"),
                     "Méthodes": f.get("methodes") or [], "Réglementation": f.get("cadre_reglementaire") or []})
    df = pd.DataFrame(rows)
    seen: dict = {}                       # deux mémoires de même titre : une barre chacun
    labels = []
    for t in df["Mémoire"]:
        seen[t] = seen.get(t, 0) + 1
        labels.append(t if seen[t] == 1 else f"{t} ({seen[t]})")
    df["Mémoire"] = labels
    st.markdown(f'<p class="muted">{len(df)} mémoire(s) lu(s) pour ce cours, dont '
                f'{int((df["Retenu"] == "Retenu").sum())} retenu(s).</p>', unsafe_allow_html=True)

    def show(fig, k, counts=None):
        if fig is not None:
            fig.update_layout(font_family="IBM Plex Sans", height=380, margin=dict(l=10, r=10, t=50, b=10))
            if counts is not None and len(counts) and counts.max() <= 10:   # pas de « demi-mémoire »
                fig.update_xaxes(dtick=1) if k in ("ecole", "meth") else fig.update_yaxes(dtick=1)
            st.plotly_chart(fig, width="stretch", key=f"carto_{key}_{k}")

    pert = df.sort_values("Pertinence /10")
    fig = px.bar(pert, x="Pertinence /10", y="Mémoire", color="Retenu", orientation="h", template="plotly_dark",
                 title="Pertinence de chaque mémoire lu", range_x=[0, 10], labels={"Mémoire": ""},
                 color_discrete_map={"Retenu": PALETTE[0], "Écarté": PALETTE[4]})
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="",
                      yaxis=dict(categoryorder="array", categoryarray=list(pert["Mémoire"])))
    fig.update_layout(height=max(320, 26 * len(df) + 120))
    st.plotly_chart(fig, width="stretch", key=f"carto_{key}_pert")

    c1, c2 = st.columns(2)
    ecoles = df.groupby("École").size().reset_index(name="Mémoires").sort_values("Mémoires", ascending=False)
    with c1:
        show(figure(ecoles, {"type": "barres_h", "x": "École", "y": ["Mémoires"]}, "Par école"), "ecole", ecoles["Mémoires"])
    annees = df.dropna(subset=["Année"]).assign(Année=lambda d: d["Année"].astype(int))
    annees = annees.groupby("Année").size().reset_index(name="Mémoires").sort_values("Année")
    with c2:
        show(figure(annees, {"type": "barres", "x": "Année", "y": ["Mémoires"]}, "Par année"), "annee", annees["Mémoires"])
    c3, c4 = st.columns(2)
    meth = df.explode("Méthodes").dropna(subset=["Méthodes"])
    meth = meth.assign(Méthodes=meth["Méthodes"].astype(str).str.slice(0, 40))
    meth = meth.groupby("Méthodes").size().reset_index(name="Mémoires").sort_values("Mémoires", ascending=False).head(12)
    with c3:
        show(figure(meth, {"type": "barres_h", "x": "Méthodes", "y": ["Mémoires"]}, "Méthodes les plus utilisées"), "meth", meth["Mémoires"])
    reg = df.explode("Réglementation").dropna(subset=["Réglementation"])
    reg = reg.groupby("Réglementation").size().reset_index(name="Mémoires").sort_values("Mémoires", ascending=False).head(8)
    with c4:
        show(figure(reg, {"type": "camembert", "x": "Réglementation", "y": ["Mémoires"]}, "Cadre réglementaire"), "reg")


def show_course(deck: dict, stats: dict, paths: dict, retained: list, official: list, qa_text: str,
                logs: list, key: str, examined: list | None = None):
    st.markdown(f'<div class="course-title">{html.escape(deck["titre"])}</div>'
                f'<div class="course-sub">{html.escape(deck.get("sous_titre", ""))}</div>', unsafe_allow_html=True)
    st.markdown(spec_grid(stats), unsafe_allow_html=True)
    downloads([("Télécharger le PowerPoint", paths.get("pptx")), ("Télécharger le polycopié PDF", paths.get("pdf")),
               ("Rapport qualité", paths.get("qa"))], key)

    t_apercu, t_plan, t_sources, t_qa, t_q, t_carto, t_log = st.tabs(
        ["Aperçu", "Plan", "Sources", "Contrôle qualité", "Poser une question", "Cartographie", "Journal"])
    with t_apercu:
        tk = f"thumbs::{paths.get('pptx')}"
        if tk not in st.session_state:
            with st.spinner("Préparation de l'aperçu…"):
                st.session_state[tk] = qa.thumbnails(paths.get("pptx"), max_n=12) if paths.get("pptx") else None
        thumbs = st.session_state[tk]
        if thumbs:
            cols = st.columns(3)
            for i, img in enumerate(thumbs):
                cols[i % 3].image(img, width="stretch")
            st.caption("Les 12 premières slides. Le fichier complet est à télécharger ci-dessus.")
        else:
            st.markdown('<p class="muted">L\'aperçu en images nécessite LibreOffice. Le plan détaillé est dans '
                        'l\'onglet suivant.</p>', unsafe_allow_html=True)
    with t_plan:
        if deck.get("objectifs"):
            st.markdown('<div class="sec">À la fin de ce cours, vous saurez</div>', unsafe_allow_html=True)
            for o in deck["objectifs"]:
                st.markdown(f"- **{o.get('verbe', '')}** {o.get('texte', '')}")
        for i, sec in enumerate(deck["sections"], 1):
            st.markdown(f'<div class="sec">{i}. {html.escape(sec["titre"])}</div>', unsafe_allow_html=True)
            for sl in sec["slides"]:
                src = ", ".join(sl.get("sources") or []) or "chiffres fictifs ou définition générale"
                st.markdown(f'<div class="slide-line">{html.escape(sl.get("titre", ""))}<br>'
                            f'<small>{html.escape(src)}</small></div>', unsafe_allow_html=True)
    with t_sources:
        if retained:
            st.markdown('<div class="sec">Mémoires d\'actuariat</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([{
                "Réf.": m.get("id"), "Titre": (m.get("fiche") or {}).get("titre") or m.get("titre"),
                "Auteur": (m.get("fiche") or {}).get("auteur"), "Année": (m.get("fiche") or {}).get("annee"),
                "École": (m.get("fiche") or {}).get("ecole"), "Pertinence /10": m.get("score"), "Lien": m.get("url")}
                for m in retained]), hide_index=True, width="stretch",
                column_config={"Lien": st.column_config.LinkColumn("Lien", display_text="ouvrir")})
        if official:
            st.markdown('<div class="sec">Textes officiels</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([{
                "Réf.": d.get("id"), "Éditeur": d.get("editeur"), "Titre": d.get("titre"), "Type": d.get("type"),
                "Année": d.get("annee"), "Pertinence /10": d.get("score"), "Lien": d.get("url")} for d in official]),
                hide_index=True, width="stretch",
                column_config={"Lien": st.column_config.LinkColumn("Lien", display_text="ouvrir")})
    with t_qa:
        st.markdown(qa_text or "Pas de rapport.")
    with t_q:
        if not retained and not official:
            st.markdown('<p class="muted">Sources indisponibles pour ce cours.</p>', unsafe_allow_html=True)
        else:
            hist = st.session_state.setdefault(f"qa_{key}", [])
            for h in hist:
                st.markdown(f"**{h['q']}**")
                st.markdown(h["a"])
            q = st.text_input("Votre question sur ce cours", key=f"q_{key}",
                              placeholder="Pourquoi la TVOG augmente-t-elle quand les taux baissent ?")
            if st.button("Demander", key=f"ask_{key}") and q:
                with st.spinner("Relecture des sources…"):
                    a = synthesis.answer(q, deck.get("theme", deck["titre"]), retained,
                                         [{"role": "user", "content": h["q"]} for h in hist], official=official)
                hist.append({"q": q, "a": a})
                st.rerun()
    with t_carto:
        cartographie(examined, retained, key)
    with t_log:
        st.markdown("\n".join(f"- {l}" for l in logs) or "Journal indisponible.")


# --------------------------------------------------------------------------- pages
st.markdown('<div class="brand"><span>IA</span>ctuaire</div>', unsafe_allow_html=True)
tabs = st.tabs(["Apprendre"] + (["Équipe d'experts"] if TEAM else []) + ["Bibliothèque"])
tab_learn, tab_lib = tabs[0], tabs[-1]

with tab_learn:
    st.markdown('<div class="hero">Que voulez-vous apprendre ?</div>'
                '<div class="lede">Mémoires d\'actuariat, EIOPA, ACPR : un cours PowerPoint et son polycopié, '
                'chaque chiffre sourcé.</div>', unsafe_allow_html=True)
    if "sujet" not in st.session_state:
        st.session_state.sujet = ""
    sujet = st.text_input("Sujet", key="sujet", label_visibility="collapsed",
                          placeholder="ex. la marge de risque sous Solvabilité II")

    with st.expander("Affiner la demande (facultatif)"):
        objectifs = st.text_area("Ce que je veux savoir faire à la fin", height=80,
                                 placeholder="ex. calculer la marge de risque, comprendre les simplifications autorisées, "
                                             "lire le SFCR d'un assureur")
        structure = st.text_area("Structure imposée", height=120,
                                 placeholder="1. Définitions et cadre réglementaire\n2. Méthodes de calcul\n3. Cas pratique")
        c1, c2 = st.columns([2, 1])
        urls = c1.text_area("Mémoires à utiliser (liens, un par ligne)", height=68)
        files = c2.file_uploader("ou PDF", type=["pdf"], accept_multiple_files=True)
        only = st.checkbox("N'utiliser que ces mémoires", value=False)

    go = st.button("Créer mon cours", type="primary", disabled=not sujet or not key_ok)
    if not key_ok:
        st.caption("Pour commencer, renseignez votre clé API dans « Votre accès IA », à gauche.")

    # Emplacements fixes : le suivi en direct et le cours gardent la même place d'une exécution à l'autre,
    # sinon Streamlit affiche un instant l'ancien et le nouveau bloc (graphiques en double).
    live = st.container()
    zone = st.container(key="course_zone")

    if go:
        req = CourseRequest(sujet.strip(), objectifs=objectifs.strip(), structure=structure.strip())
        uploaded = [(f.name, f.getvalue()) for f in (files or [])]
        imposed = [u for u in urls.splitlines() if u.strip()]
        failure = None
        with live:
            st.caption("Gardez cet onglet ouvert pendant la création du cours.")
            prog = LivePanel(r)
            try:
                res = pipeline.run(req, r, log=prog, imposed_urls=imposed, uploaded=uploaded,
                                   search=not (only and (imposed or uploaded)))
            except Exception as e:
                failure = e
            if failure is not None:   # message lisible, hors du bloc replié
                if isinstance(failure, llm.MissingAPIKey):
                    st.error(str(failure))
                else:
                    st.error(f"Le cours n'a pas pu être produit — {type(failure).__name__} : {failure}")
                    with st.expander("Journal"):
                        st.markdown("\n".join(f"- {l}" for l in prog.lines))
                st.stop()
            st.session_state.course = {"res": res, "logs": prog.lines}
            if not res.pptx_path:
                st.warning("Aucune source exploitable n'a été trouvée. Élargissez le sujet, baissez la pertinence "
                           "minimale ou ajoutez des sources autorisées.")

    with zone:
        cur = st.session_state.get("course")
        if cur and cur["res"].pptx_path:
            res = cur["res"]
            st.divider()
            show_course(res.deck, res.stats, {"pptx": res.pptx_path, "pdf": res.pdf_path, "qa": res.qa_path},
                        res.retained, res.request.official_docs, res.qa_text, cur["logs"], key="cur",
                        examined=res.examined)
        elif not config.LOCAL and not go:
            # connexion perdue pendant la création : le cours a bien été produit, on le retrouve sur le disque
            done = sorted(config.OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if done:
                try:
                    last = json.loads(done[0].read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    last = None
                if last:
                    base = str(done[0])[:-5]
                    st.divider()
                    st.markdown(f'<div class="course-title">{html.escape(last.get("titre", ""))}</div>'
                                f'<div class="course-sub">{html.escape(last.get("sous_titre", ""))}</div>',
                                unsafe_allow_html=True)
                    if last.get("stats"):
                        st.markdown(spec_grid(last["stats"]), unsafe_allow_html=True)
                    downloads([("Télécharger le PowerPoint", base + ".pptx"),
                               ("Télécharger le polycopié PDF", base + "_polycopie.pdf"),
                               ("Rapport qualité", base + "_controle_qualite.md")], key="last")
                    st.markdown('<p class="muted">Votre dernier cours, retrouvé après une reconnexion. '
                                'Tous les cours de cette visite sont aussi dans l\'onglet Bibliothèque.</p>',
                                unsafe_allow_html=True)

def _team_tab():
    st.markdown('<p class="muted">Adressez-vous à l\'équipe ou à un expert en particulier : '
                + ", ".join(f"<b>{k}</b>" for k in EXPERTS) + ".</p>", unsafe_allow_html=True)
    if "turns" not in st.session_state:
        st.session_state.turns = []
    if st.session_state.turns and st.button("Effacer la conversation"):
        st.session_state.turns = []
        st.rerun()
    for k, item in enumerate(st.session_state.turns):
        t = item["turn"]
        st.markdown(f"**Vous** — {html.escape(item['user'])}")
        if t.final:
            st.markdown(t.final)
        with st.expander("Le travail des experts" + (f" ({', '.join(t.experts)})" if t.experts else ""),
                         expanded=(k == len(st.session_state.turns) - 1)):
            for expert, md in t.reasoning:
                st.markdown(f'<div class="expert">{expert}</div>', unsafe_allow_html=True)
                st.markdown(md)
            for titre, q in t.sql:
                st.code(q, language="sql")
            for i, (titre, fig, df) in enumerate(t.charts + t.carto):
                if fig is not None:
                    fig.update_layout(font_family="IBM Plex Sans")
                    st.plotly_chart(fig, width="stretch", key=f"tc{k}_{i}")
                st.dataframe(df, hide_index=True, width="stretch")
            for i, df in enumerate(t.memoires):
                st.dataframe(df, hide_index=True, width="stretch",
                             column_config={"Lien": st.column_config.LinkColumn("Lien", display_text="ouvrir")})
            if t.course:
                c = t.course
                show_course(c["deck"], c["stats"], {"pptx": c["pptx"], "pdf": c["pdf"], "qa": c["qa"]},
                            c["retained"], c["official"], t.qa, [], key=f"t{k}")
    with st.form("team", clear_on_submit=True):
        q = st.text_area("Votre demande", height=90, label_visibility="collapsed",
                         placeholder="ex. Que le Cartographe montre les méthodes des mémoires sur l'ALM, puis que "
                                     "l'Expert actuariel compare flexing et projection complète.")
        files_t = st.file_uploader("Joindre des mémoires (PDF)", type=["pdf"], accept_multiple_files=True)
        sent = st.form_submit_button("Envoyer", type="primary")
    if sent and q.strip():
        if not key_ok:
            st.error("Renseignez votre clé API dans « Votre accès IA ».")
            st.stop()
        history = []
        if memory:
            for item in st.session_state.turns[-6:]:
                t = item["turn"]
                notes = "\n\n".join(f"[{e}] {md}" for e, md in t.reasoning)[:3500]
                history += [{"role": "user", "content": item["user"]},
                            {"role": "assistant", "content": (t.final or "") + "\n\nRésultats des experts :\n" + notes}]
        with st.status("L'équipe travaille…", expanded=True) as status:
            try:
                turn = run_turn(q.strip(), history, r.modele,
                                attachments=[(f.name, f.getvalue()) for f in (files_t or [])] or None,
                                log=status.write, reglages=r)
                status.update(label="Terminé", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Erreur", state="error")
                st.error(f"{type(e).__name__} : {e}")
                st.stop()
        st.session_state.turns.append({"user": q.strip(), "turn": turn})
        st.rerun()


if TEAM:
    with tabs[1]:
        _team_tab()

with tab_lib:
    courses = sorted(config.OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not config.LOCAL:
        st.markdown('<p class="muted">Les cours créés pendant cette visite. Téléchargez-les : ils sont '
                    'effacés du serveur au bout de 24 heures.</p>', unsafe_allow_html=True)
    if not courses:
        st.markdown('<p class="muted">Vos cours apparaîtront ici.</p>', unsafe_allow_html=True)
    for i, p in enumerate(courses):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        base = str(p)[:-5]
        stats = c.get("stats", {})
        when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y")
        with st.expander(f"{c.get('titre', p.stem)}  ({when})"):
            if stats:
                st.markdown(spec_grid(stats), unsafe_allow_html=True)
            downloads([("PowerPoint", base + ".pptx"), ("Polycopié PDF", base + "_polycopie.pdf"),
                       ("Rapport qualité", base + "_controle_qualite.md")], key=f"lib{i}_")

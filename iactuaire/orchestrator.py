"""IActuaire — un chef d'orchestre (Claude) qui fait travailler des experts.

Chaque expert est un outil. L'utilisateur peut les désigner (« Demande au Documentaliste… »,
« Ne sollicite pas le Formateur ») ; sinon le chef d'orchestre choisit lui-même.
Tout ce que produisent les experts est rangé dans un `Turn` (raisonnement, requêtes SQL,
tableaux, graphiques, mémoires, fichiers) que l'interface affiche en onglets.
"""
import json
import re
import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from . import config, db, pipeline, synthesis
from .llm import client
from .synthesis import CourseRequest

EXPERTS = {
    "Documentaliste": "cherche de nouveaux mémoires sur le site, les télécharge, les lit et note leur pertinence",
    "Analyste": "interroge en SQL la base des mémoires déjà lus et trace des graphiques",
    "Cartographe": "cartographie les mémoires (années, écoles, branches, méthodes, réglementation…)",
    "Lecteur": "présente la fiche détaillée d'un mémoire précis",
    "Expert actuariel": "explique une notion ou répond à une question en citant les mémoires (pages)",
    "Formateur": "construit un cours PowerPoint + polycopié PDF à partir des mémoires et des documents officiels "
                 "(EIOPA, ACPR…), dans les limites de slides et de pages réglées, avec contrôle qualité",
}

PALETTE = ["#C21B17", "#5B8DEF", "#F2A6A2", "#8E1410", "#9AA5B1", "#2E3A59"]


@dataclass
class Turn:
    reasoning: list = field(default_factory=list)   # [(expert, markdown)]
    sql: list = field(default_factory=list)         # [(titre, requête)]
    charts: list = field(default_factory=list)      # [(titre, figure plotly, dataframe)]
    memoires: list = field(default_factory=list)    # [dataframe]
    carto: list = field(default_factory=list)       # [(titre, figure, dataframe)]
    files: list = field(default_factory=list)       # [(libellé, chemin)]
    qa: str = ""
    course: dict | None = None                       # cours produit (fiche résultat)
    final: str = ""
    experts: list = field(default_factory=list)


# --------------------------------------------------------------------------- graphiques

def figure(df: pd.DataFrame, spec: dict | None, title: str):
    import plotly.express as px

    spec = spec or {}
    kind = spec.get("type", "barres")
    if kind == "aucun" or df.empty:
        return None
    cols = list(df.columns)
    x = spec.get("x") if spec.get("x") in cols else cols[0]
    y = spec.get("y") or [c for c in cols if c != x and pd.api.types.is_numeric_dtype(df[c])][:3]
    y = [c for c in ([y] if isinstance(y, str) else y) if c in cols]
    if not y:
        return None
    color = spec.get("couleur") if spec.get("couleur") in cols else None
    data = df
    if len(y) > 1 and kind != "camembert":           # plusieurs mesures → une couleur par mesure
        data = df.melt(id_vars=[x], value_vars=y, var_name="Mesure", value_name="Valeur")
        y, color = ["Valeur"], "Mesure"
    if kind != "courbes":                              # années, codes… : catégories, pas un axe continu
        data = data.assign(**{x: data[x].astype(str)})
    common = dict(title=title, color_discrete_sequence=PALETTE, template="plotly_dark")
    if kind == "courbes":
        fig = px.line(data, x=x, y=y[0], color=color, markers=True, **common)
    elif kind == "camembert":
        fig = px.pie(data, names=x, values=y[0], hole=0.5, **common)
    elif kind == "barres_h":
        fig = px.bar(data, y=x, x=y[0], color=color, orientation="h", barmode="group", **common)
    else:
        fig = px.bar(data, x=x, y=y[0], color=color, barmode="group", **common)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=460,
                      margin=dict(l=10, r=10, t=60, b=10), legend_title_text=color or "")
    if kind in ("barres", "barres_h"):                # garde l'ordre des données (ex. années croissantes)
        order = list(dict.fromkeys(data[x]))
        axis = dict(type="category", categoryorder="array",
                    categoryarray=order if kind == "barres" else order[::-1])
        fig.update_xaxes(**axis) if kind == "barres" else fig.update_yaxes(**axis)
    return fig


def _df_text(df: pd.DataFrame, n: int = 30) -> str:
    if df.empty:
        return "(aucune ligne)"
    return f"{len(df)} ligne(s). Colonnes : {', '.join(map(str, df.columns))}\n" + df.head(n).to_csv(index=False)


# --------------------------------------------------------------------------- experts

def _readonly() -> sqlite3.Connection:
    with db.connect():   # crée tables et vue si besoin
        pass
    return sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)


def analyste(turn: Turn, requete: str, titre: str = "Résultat", graphique: dict | None = None, **_):
    q = requete.strip().rstrip(";")
    if not re.match(r"(?is)^\s*(select|with)\b", q) or re.search(r"(?i)\b(insert|update|delete|drop|alter|attach|pragma|create|replace)\b", q):
        raise ValueError("seules les requêtes de lecture (SELECT / WITH) sont autorisées")
    with _readonly() as con:
        df = pd.read_sql_query(f"SELECT * FROM ({q}) LIMIT 500", con)
    turn.sql.append((titre, q))
    fig = figure(df, graphique, titre)
    turn.charts.append((titre, fig, df))
    turn.reasoning.append(("Analyste", f"**{titre}** — {len(df)} ligne(s) obtenue(s).\n\n```sql\n{q}\n```"))
    return _df_text(df)


ECOLES = [  # regroupement des libellés d'écoles (les fiches les écrivent de façons variées)
    (r"ISFA|Science Financi[eè]re et d.Assurances|Lyon 1", "ISFA"), (r"ENSAE", "ENSAE"), (r"ENSAI", "ENSAI"),
    (r"Dauphine", "Dauphine"), (r"CNAM|Conservatoire national", "CNAM"), (r"ISUP|Sorbonne|Pierre et Marie Curie", "ISUP"),
    (r"EURIA|Brest|Bretagne Occidentale", "EURIA"), (r"\bCEA\b|Centre d.[ÉE]tudes Actuarielles", "CEA"),
    (r"IRM|Risk Management", "IRM"), (r"Strasbourg", "Strasbourg"), (r"Louvain|UCL", "UCLouvain"),
    (r"Laval", "Université Laval"), (r"Paris.?Saclay|Orsay", "Paris-Saclay"), (r"Le Mans", "Le Mans"),
]


def ecole_courte(v) -> str:
    if not v or str(v).lower() in ("none", "null"):
        return "non renseigné"
    for pat, name in ECOLES:
        if re.search(pat, str(v), re.I):
            return name
    return str(v)[:40]


AXES = {"annee": "annee", "ecole": "ecole", "entreprise": "entreprise", "branche": "branche",
        "methodes": "methodes", "cadre_reglementaire": "cadre_reglementaire", "mots_cles": "mots_cles"}


def cartographe(turn: Turn, axe: str, theme: str = "", top: int = 15, **_):
    col = AXES.get(axe)
    if not col:
        raise ValueError(f"axe inconnu ; choisir parmi {', '.join(AXES)}")
    is_list = col in ("methodes", "cadre_reglementaire", "mots_cles")
    filt, params = "v.statut = 'lu'", []
    if theme:
        filt += " AND v.url IN (SELECT url FROM pertinences WHERE theme = ? AND score >= ?)"
        params = [theme.lower().strip(), config.MIN_RELEVANCE]
    if is_list:
        q = (f"SELECT TRIM(j.value) AS {col}, COUNT(*) AS nb_memoires FROM v_memoires v, json_each(v.{col}) j "
             f"WHERE {filt} GROUP BY 1 ORDER BY 2 DESC LIMIT {int(top)}")
    else:
        q = (f"SELECT COALESCE(CAST(v.{col} AS TEXT), 'non renseigné') AS {col}, COUNT(*) AS nb_memoires "
             f"FROM v_memoires v WHERE {filt} GROUP BY 1 ORDER BY {'1' if col == 'annee' else '2 DESC'} LIMIT {int(top)}")
    if col == "ecole":   # regroupement des libellés avant de compter
        q = f"SELECT v.ecole AS ecole FROM v_memoires v WHERE {filt}"
    with _readonly() as con:
        df = pd.read_sql_query(q, con, params=params)
    if col == "ecole":
        df = (df.assign(ecole=df["ecole"].map(ecole_courte)).groupby("ecole").size()
                .reset_index(name="nb_memoires").sort_values("nb_memoires", ascending=False).head(int(top)))
    elif is_list:        # noms de méthodes trop longs : on les raccourcit pour le graphique
        df[col] = df[col].astype(str).str.slice(0, 60)
    titre = f"Mémoires par {axe.replace('_', ' ')}" + (f" — {theme}" if theme else "")
    fig = figure(df, {"type": "courbes" if col == "annee" else "barres_h", "x": col, "y": "nb_memoires"}, titre)
    turn.carto.append((titre, fig, df))
    turn.sql.append((titre, q))
    turn.reasoning.append(("Cartographe", f"**{titre}** : {len(df)} modalité(s)."))
    return _df_text(df)


def _memoires_df(items: list[dict]) -> pd.DataFrame:
    rows = []
    for e in items:
        f = e.get("fiche") or {}
        rows.append({"Titre": f.get("titre") or e.get("titre"), "Auteur": f.get("auteur"), "Année": f.get("annee"),
                     "École": f.get("ecole"), "Pertinence /10": e.get("score"), "Statut": e.get("statut"),
                     "Pourquoi": e.get("justification") or e.get("raison"), "Lien": e.get("url")})
    df = pd.DataFrame(rows)
    for c in ("Année", "Pertinence /10"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df


def documentaliste(turn: Turn, theme: str, attachments=None, reglages=None, log=print, **_):
    res = pipeline.run(CourseRequest(theme), reglages, make_files=False, uploaded=attachments, log=log)
    df = _memoires_df(res.examined).sort_values("Pertinence /10", ascending=False, na_position="last")
    turn.memoires.append(df)
    scored = df.dropna(subset=["Pertinence /10"]).head(15)
    if not scored.empty:
        short = scored.assign(Mémoire=scored["Titre"].fillna("").str.slice(0, 55))
        turn.charts.append((f"Pertinence des mémoires — {theme}",
                            figure(short, {"type": "barres_h", "x": "Mémoire", "y": "Pertinence /10"},
                                   f"Pertinence des mémoires — {theme}"), scored))
    ok = df[df["Pertinence /10"].fillna(0) >= config.MIN_RELEVANCE]
    turn.reasoning.append(("Documentaliste",
                           f"{len(df)} mémoire(s) examiné(s) sur « {theme} », {len(ok)} pertinent(s) "
                           f"(≥ {config.MIN_RELEVANCE}/10), {int((df['Statut'] == 'indisponible').sum())} indisponible(s)."))
    return _df_text(df[["Titre", "Auteur", "Année", "Pertinence /10", "Statut", "Lien"]], 25)


def lecteur(turn: Turn, recherche: str, **_):
    like = f"%{recherche.lower()}%"
    with _readonly() as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT url FROM v_memoires WHERE statut='lu' AND (lower(titre) LIKE ? OR lower(auteur) LIKE ? OR lower(url) LIKE ?) LIMIT 1",
            (like, like, like)).fetchone()
    if not row:
        return "Aucun mémoire déjà lu ne correspond. Le Documentaliste peut le chercher."
    m = db.get_memoire(row["url"])
    f = m["fiche"]
    lst = lambda k: "\n".join(f"- {x}" for x in (f.get(k) or [])) or "—"
    md = (f"### {f.get('titre')}\n{f.get('auteur') or '?'} · {f.get('ecole') or '?'} · {f.get('entreprise') or '?'} · "
          f"{f.get('annee') or '?'} — [PDF]({m['url']})\n\n**Problématique** — {f.get('problematique') or '—'}\n\n"
          f"**Méthodes**\n{lst('methodes')}\n\n**Données** — {f.get('donnees') or '—'}\n\n"
          f"**Cadre réglementaire**\n{lst('cadre_reglementaire')}\n\n**Résultats clés**\n{lst('resultats_cles')}\n\n"
          f"**Limites**\n{lst('limites')}")
    turn.reasoning.append(("Lecteur", md))
    turn.memoires.append(_memoires_df([{**m, "fiche": f, "statut": "lu"}]))
    return md


def expert_actuariel(turn: Turn, question: str, theme: str = "", **_):
    retained = pipeline.load_retained(theme or question, top_n=6)
    if not retained:
        return "Aucun mémoire déjà lu sur ce sujet : demande d'abord au Documentaliste d'en chercher."
    ans = synthesis.answer(question, theme or question, retained)
    turn.reasoning.append(("Expert actuariel", ans + "\n\n" + "\n".join(
        f"- **{m['id']}** — {(m['fiche'].get('auteur') or '')} · {m['fiche'].get('titre')} ({m['fiche'].get('annee') or '?'})"
        for m in retained)))
    turn.memoires.append(_memoires_df(retained).assign(Réf=[m["id"] for m in retained]))
    return ans


def formateur(turn: Turn, theme: str, objectifs: str = "", structure: str = "",
              memoires_deja_lus: bool = False, uniquement_pieces_jointes: bool = False,
              attachments=None, reglages=None, log=print, **_):
    req = CourseRequest(theme, objectifs=objectifs, structure=structure)
    if memoires_deja_lus and not attachments:
        res = pipeline.regenerate(req, reglages, log=log)
    else:
        res = pipeline.run(req, reglages, uploaded=attachments, log=log,
                           search=not (uniquement_pieces_jointes and attachments))
    if not res.pptx_path:
        return "Cours non produit : aucun mémoire exploitable."
    turn.files += [("Cours PowerPoint", res.pptx_path), ("Polycopié PDF", res.pdf_path),
                   ("Rapport qualité", res.qa_path)]
    turn.qa = res.qa_text
    turn.course = {"deck": res.deck, "stats": res.stats, "pptx": res.pptx_path, "pdf": res.pdf_path,
                   "qa": res.qa_path, "retained": res.retained,
                   "official": [{k: v for k, v in d.items() if k != "pages"} for d in res.request.official_docs]}
    turn.memoires.append(_memoires_df(res.retained))
    n = sum(len(s["slides"]) for s in res.deck["sections"])
    plan = "\n".join(f"{i}. **{s['titre']}** — {len(s['slides'])} slides" for i, s in enumerate(res.deck["sections"], 1))
    turn.reasoning.append(("Formateur", f"### {res.deck['titre']}\n{n} slides de contenu, "
                                        f"{len(res.retained)} mémoire(s), {len(res.request.official_docs)} texte(s) officiel(s).\n\n{plan}"))
    return f"Cours « {res.deck['titre']} » produit ({n} slides). Plan :\n{plan}\n\nContrôle qualité :\n{res.qa_text[:1500]}"


TOOLS = [
    {"name": "documentaliste", "description": "Documentaliste : " + EXPERTS["Documentaliste"]
        + ". Long (quelques minutes). À utiliser pour un sujet peu couvert par la base.",
     "input_schema": {"type": "object", "properties": {"theme": {"type": "string"}}, "required": ["theme"]}},
    {"name": "analyste", "description": "Analyste : exécute une requête SQL SQLite en lecture seule et trace un graphique. "
        "Tables : v_memoires(url, statut ['lu'|'indisponible'|'illisible'], raison, lu_le, titre, auteur, annee, "
        "ecole, entreprise, branche, problematique, methodes, donnees, cadre_reglementaire, resultats_cles, limites, "
        "mots_cles) — methodes, cadre_reglementaire, resultats_cles, limites, mots_cles sont des tableaux JSON "
        "(utiliser json_each) ; pertinences(theme, url, score 0-10, justification).",
     "input_schema": {"type": "object", "properties": {
         "requete": {"type": "string"}, "titre": {"type": "string"},
         "graphique": {"type": "object", "properties": {
             "type": {"type": "string", "enum": ["barres", "barres_h", "courbes", "camembert", "aucun"]},
             "x": {"type": "string"}, "y": {"type": "array", "items": {"type": "string"}},
             "couleur": {"type": "string"}}}},
         "required": ["requete", "titre"]}},
    {"name": "cartographe", "description": "Cartographe : " + EXPERTS["Cartographe"] + " pour tous les mémoires lus ou ceux d'un thème.",
     "input_schema": {"type": "object", "properties": {
         "axe": {"type": "string", "enum": list(AXES)}, "theme": {"type": "string"},
         "top": {"type": "integer", "minimum": 3, "maximum": 40}}, "required": ["axe"]}},
    {"name": "lecteur", "description": "Lecteur : " + EXPERTS["Lecteur"] + " (recherche par titre, auteur ou lien).",
     "input_schema": {"type": "object", "properties": {"recherche": {"type": "string"}}, "required": ["recherche"]}},
    {"name": "expert_actuariel", "description": "Expert actuariel : " + EXPERTS["Expert actuariel"]
        + ". S'appuie sur les mémoires déjà lus du thème.",
     "input_schema": {"type": "object", "properties": {
         "question": {"type": "string"}, "theme": {"type": "string"}}, "required": ["question"]}},
    {"name": "formateur", "description": "Formateur : " + EXPERTS["Formateur"]
        + ". Très long (10 à 20 minutes) et payant : seulement si l'utilisateur demande un cours, une formation ou un support.",
     "input_schema": {"type": "object", "properties": {
         "theme": {"type": "string"},
         "objectifs": {"type": "string", "description": "ce que l'utilisateur veut apprendre, tel qu'il l'a écrit"},
         "structure": {"type": "string", "description": "structure attendue, recopiée telle quelle si fournie"},
         "memoires_deja_lus": {"type": "boolean", "description": "réutiliser les mémoires déjà lus du thème, sans recherche"},
         "uniquement_pieces_jointes": {"type": "boolean"}}, "required": ["theme"]}},
]

TOOL_EXPERT = {"documentaliste": "Documentaliste", "analyste": "Analyste", "cartographe": "Cartographe",
               "lecteur": "Lecteur", "expert_actuariel": "Expert actuariel", "formateur": "Formateur"}
FUNCS = {"documentaliste": documentaliste, "analyste": analyste, "cartographe": cartographe,
         "lecteur": lecteur, "expert_actuariel": expert_actuariel, "formateur": formateur}

SYSTEM = """Tu es IActuaire, chef d'orchestre d'une équipe d'experts en actuariat qui travaillent sur une base
de mémoires d'actuariat (ressources-actuarielles.net, Institut des actuaires).
Experts disponibles (outils) :
{experts}

Règles :
- Respecte à la lettre les consignes de l'utilisateur sur les experts à solliciter ou à ne pas solliciter.
- Sinon, choisis le minimum d'experts utile. Enchaîne-les si nécessaire (ex. Documentaliste puis Expert actuariel).
- Réutilise les résultats des échanges précédents (mémoire de conversation) plutôt que de tout refaire.
- Le Formateur est long et payant : ne le lance que si un cours est explicitement demandé.
- Les productions des experts sont affichées à l'utilisateur dans des onglets : ne les recopie pas.
- Réponse finale : 3 à 6 phrases en français — ce qui a été fait, ce qu'il faut en retenir, une suite possible.
- N'invente aucun chiffre : ceux que tu cites viennent des résultats des experts.
{pj}"""


def run_turn(user_text: str, history: list[dict], model: str, attachments=None, log=print, reglages=None) -> Turn:
    turn = Turn()
    experts = "\n".join(f"- {k} : {v}" for k, v in EXPERTS.items())
    pj = (f"\nL'utilisateur a joint {len(attachments)} PDF ({', '.join(n for n, _ in attachments)}) : "
          "ils sont transmis au Documentaliste et au Formateur." if attachments else "")
    system = SYSTEM.format(experts=experts, pj=pj)
    messages = [*history, {"role": "user", "content": user_text}]

    for _ in range(10):
        r = client().messages.create(model=model, max_tokens=4000, system=system, tools=TOOLS, messages=messages)
        texts = [b.text for b in r.content if b.type == "text" and b.text.strip()]
        if r.stop_reason != "tool_use":
            turn.final = "\n\n".join(texts)
            break
        if texts:
            turn.reasoning.append(("IActuaire", "\n\n".join(texts)))
        messages.append({"role": "assistant", "content": r.content})
        results = []
        for b in r.content:
            if b.type != "tool_use":
                continue
            name = TOOL_EXPERT.get(b.name, b.name)
            if name not in turn.experts:
                turn.experts.append(name)
            log(f"🧑‍💼 {name} : {json.dumps(b.input, ensure_ascii=False)[:160]}")
            try:
                out = FUNCS[b.name](turn, **b.input, attachments=attachments, log=log, reglages=reglages)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(out)[:12000]})
            except Exception as e:
                log(f"⚠️ {name} : {e}")
                turn.reasoning.append((name, f"⚠️ Erreur : {e}"))
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": f"Erreur : {e}", "is_error": True})
        messages.append({"role": "user", "content": results})
    else:
        turn.final = "J'ai atteint le nombre maximal d'étapes ; voici ce que les experts ont produit."
    return turn

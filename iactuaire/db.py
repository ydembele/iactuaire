"""Mémoire de l'agent : tout ce qu'il a lu est gardé dans SQLite.

C'est ce qui le fait « apprendre » : un mémoire lu une fois a une fiche
réutilisable pour toutes les recherches suivantes, sans le relire.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS memoires (
    url         TEXT PRIMARY KEY,
    titre       TEXT,
    statut      TEXT,          -- lu | indisponible | illisible
    raison      TEXT,          -- pourquoi indisponible/illisible
    pdf_path    TEXT,
    fiche_json  TEXT,          -- fiche synthétique produite par le LLM
    extrait     TEXT,          -- résumé + conclusion extraits du PDF
    lu_le       TEXT
);
CREATE TABLE IF NOT EXISTS pertinences (
    theme       TEXT,
    url         TEXT,
    score       INTEGER,
    justification TEXT,
    PRIMARY KEY (theme, url)
);
-- Vue « à plat » des fiches, pratique pour l'analyste SQL
CREATE VIEW IF NOT EXISTS v_memoires AS
SELECT url, statut, raison, lu_le,
       COALESCE(json_extract(fiche_json, '$.titre'), titre) AS titre,
       json_extract(fiche_json, '$.auteur')               AS auteur,
       json_extract(fiche_json, '$.annee')                AS annee,
       json_extract(fiche_json, '$.ecole')                AS ecole,
       json_extract(fiche_json, '$.entreprise')           AS entreprise,
       json_extract(fiche_json, '$.branche')              AS branche,
       json_extract(fiche_json, '$.problematique')        AS problematique,
       json_extract(fiche_json, '$.methodes')             AS methodes,
       json_extract(fiche_json, '$.donnees')              AS donnees,
       json_extract(fiche_json, '$.cadre_reglementaire')  AS cadre_reglementaire,
       json_extract(fiche_json, '$.resultats_cles')       AS resultats_cles,
       json_extract(fiche_json, '$.limites')              AS limites,
       json_extract(fiche_json, '$.mots_cles')            AS mots_cles
FROM memoires;
"""


_ready = False

_TEXT = ("titre", "auteur", "ecole", "entreprise", "branche", "problematique", "donnees", "justification")
_LIST = ("methodes", "cadre_reglementaire", "resultats_cles", "limites", "mots_cles")


def normalize_fiche(f: dict | None) -> dict | None:
    """Les modèles renvoient parfois une liste là où on attend un texte (plusieurs auteurs…) ou
    l'inverse : on remet chaque champ dans sa forme attendue."""
    if not isinstance(f, dict):
        return f
    f = dict(f)
    for k in _TEXT:
        v = f.get(k)
        if isinstance(v, (list, tuple)):
            f[k] = ", ".join(str(x) for x in v if x) or None
        elif v is not None and not isinstance(v, str):
            f[k] = str(v)
    for k in _LIST:
        v = f.get(k)
        if v is None:
            f[k] = []
        elif isinstance(v, str):
            f[k] = [v]
    a = f.get("annee")
    if isinstance(a, str):
        digits = "".join(c for c in a if c.isdigit())[:4]
        f["annee"] = int(digits) if len(digits) == 4 else None
    p = f.get("pertinence")
    if p is not None and not isinstance(p, int):
        try:
            f["pertinence"] = int(float(str(p).split("/")[0]))
        except ValueError:
            f["pertinence"] = 0
    return f


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH, timeout=30)      # plusieurs utilisateurs à la fois : on attend son tour
    con.row_factory = sqlite3.Row
    global _ready
    if not _ready:
        con.execute("PRAGMA journal_mode=WAL")      # lectures et écriture simultanées
        con.executescript(SCHEMA)
        _ready = True
    try:
        yield con
        con.commit()
    finally:
        con.close()


def get_memoire(url: str) -> dict | None:
    with connect() as con:
        row = con.execute("SELECT * FROM memoires WHERE url=?", (url,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["fiche"] = normalize_fiche(json.loads(d["fiche_json"])) if d["fiche_json"] else None
    return d


def save_memoire(url, titre, statut, raison=None, pdf_path=None, fiche=None, extrait=None):
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO memoires
               (url, titre, statut, raison, pdf_path, fiche_json, extrait, lu_le)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                url, titre, statut, raison, pdf_path,
                json.dumps(fiche, ensure_ascii=False) if fiche else None,
                extrait, datetime.now().isoformat(timespec="seconds"),
            ),
        )


def save_pertinence(theme, url, score, justification):
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO pertinences VALUES (?,?,?,?)",
            (theme.lower().strip(), url, int(score), justification),
        )


def get_pertinence(theme, url):
    with connect() as con:
        row = con.execute(
            "SELECT score, justification FROM pertinences WHERE theme=? AND url=?",
            (theme.lower().strip(), url),
        ).fetchone()
    return dict(row) if row else None


def all_read() -> list[dict]:
    """Toutes les fiches déjà connues (pour réutiliser sans rien re-télécharger)."""
    with connect() as con:
        rows = con.execute(
            "SELECT url, titre, fiche_json FROM memoires WHERE statut='lu'"
        ).fetchall()
    return [
        {"url": r["url"], "titre": r["titre"], "fiche": normalize_fiche(json.loads(r["fiche_json"]))}
        for r in rows
        if r["fiche_json"]
    ]


def stats() -> dict:
    with connect() as con:
        rows = con.execute(
            "SELECT statut, COUNT(*) n FROM memoires GROUP BY statut"
        ).fetchall()
    return {r["statut"]: r["n"] for r in rows}

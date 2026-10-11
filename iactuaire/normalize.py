"""Remise en forme du contenu rédigé par l'IA, avant toute mise en page.

Les modèles respectent la plupart du temps le format demandé, mais pas toujours : des notes en
liste de phrases au lieu d'un paragraphe, un titre en liste, des points en un seul texte… Chaque
champ est ramené à la forme attendue (texte, liste de textes, tableau, objet), pour que le
PowerPoint, le polycopié et le contrôle qualité ne cassent jamais sur un écart de format.
"""


def txt(v) -> str:
    """N'importe quelle valeur → un texte."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return " ".join(t for t in (txt(x) for x in v) if t)
    if isinstance(v, dict):
        return " ".join(t for t in (txt(x) for x in v.values()) if t)
    return str(v)


def opt(v) -> str | None:
    t = txt(v).strip()
    return t or None


def lst(v) -> list[str]:
    """N'importe quelle valeur → une liste de textes."""
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)):
        return [t for t in (txt(x) for x in v) if t]
    if isinstance(v, str):
        lines = [l.strip(" -•\t") for l in v.splitlines() if l.strip(" -•\t")]
        return lines if len(lines) > 1 else [v]
    return [txt(v)]


def objs(v, keys: tuple, text_keys: tuple = ()) -> list[dict]:
    """Liste d'objets {clé: texte}. Un simple texte devient un objet dont il remplit la première clé."""
    out = []
    for x in (v if isinstance(v, (list, tuple)) else ([v] if v else [])):
        if isinstance(x, dict):
            o = {k: txt(x.get(k)) for k in keys if k not in text_keys}
            o.update({k: (lst(x.get(k)) if k in text_keys else txt(x.get(k))) for k in text_keys})
            out.append(o)
        elif x:
            o = {k: "" for k in keys}
            o[keys[0]] = txt(x)
            out.append(o)
    return out


def _num(v):
    if isinstance(v, (int, float)):
        return v
    s = txt(v).replace(" ", "").replace(" ", "").replace("%", "").replace(",", ".").replace("−", "-")
    try:
        return float(s)
    except ValueError:
        return None


def slide(sl) -> dict:
    if not isinstance(sl, dict):
        return {"type": "points", "titre": "", "points": lst(sl), "sources": []}
    s = dict(sl)
    s["type"] = txt(s.get("type")).strip() or "points"
    for k in ("titre", "notes"):
        s[k] = txt(s.get(k))
    for k in ("a_retenir", "vigilance", "intro", "texte", "commentaire"):
        s[k] = opt(s.get(k))
    s["sources"] = lst(s.get("sources"))
    t = s["type"]
    if t == "colonnes":
        s["colonnes"] = objs(s.get("colonnes"), ("titre", "points"), text_keys=("points",))
    elif t == "tableau":
        s["colonnes"] = lst(s.get("colonnes"))
        s["lignes"] = [lst(r) if isinstance(r, (list, tuple)) else [txt(r)] for r in (s.get("lignes") or [])]
    elif t == "code":
        for k in ("code", "code_poly"):
            v = s.get(k)
            s[k] = "\n".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v or "")
        s["fichier"], s["langage"] = txt(s.get("fichier")), txt(s.get("langage")) or "python"
    if "points" in s or t == "points":
        s["points"] = lst(s.get("points"))
    if "cartes" in s:
        s["cartes"] = objs(s.get("cartes"), ("titre", "texte"))
    if "etapes" in s:
        s["etapes"] = objs(s.get("etapes"), ("titre", "texte"))
    if "formules" in s:
        s["formules"] = objs(s.get("formules"), ("expression", "nom", "legende"))
    if "chiffres" in s:
        s["chiffres"] = objs(s.get("chiffres"), ("valeur", "libelle"))
    if isinstance(s.get("encadre"), (dict, str, list)) and s.get("encadre"):
        e = s["encadre"]
        s["encadre"] = {"titre": txt(e.get("titre")), "texte": txt(e.get("texte"))} if isinstance(e, dict) \
            else {"titre": "", "texte": txt(e)}
    else:
        s["encadre"] = None
    g = s.get("graphique")
    if isinstance(g, dict):
        series = []
        for ser in g.get("series") or []:
            if isinstance(ser, dict):
                vals = [_num(x) for x in (ser.get("valeurs") or [])]
                series.append({"nom": txt(ser.get("nom")), "valeurs": [0 if x is None else x for x in vals]})
        s["graphique"] = {**g, "type": txt(g.get("type")) or "barres", "titre": txt(g.get("titre")),
                          "unite": opt(g.get("unite")), "categories": lst(g.get("categories")), "series": series,
                          "totaux": [int(x) for x in (g.get("totaux") or []) if _num(x) is not None]}
    sc = s.get("schema")
    if isinstance(sc, dict):
        noeuds = objs(sc.get("noeuds"), ("titre", "texte", "id"))
        for i, n in enumerate(noeuds):
            n["id"] = n["id"] or f"n{i}"
        liens = [{"de": txt(l.get("de")), "vers": txt(l.get("vers")), "libelle": txt(l.get("libelle"))}
                 for l in (sc.get("liens") or []) if isinstance(l, dict)]
        s["schema"] = {"disposition": txt(sc.get("disposition")) or "ligne", "noeuds": noeuds, "liens": liens}
    return s


def course(c: dict) -> dict:
    c = dict(c)
    for k in ("titre", "sous_titre", "public", "introduction", "conclusion", "theme"):
        c[k] = txt(c.get(k))
    c["objectifs"] = objs(c.get("objectifs"), ("texte", "verbe"))
    c["points_cles"] = lst(c.get("points_cles"))
    c["pour_aller_plus_loin"] = lst(c.get("pour_aller_plus_loin"))
    c["glossaire"] = objs(c.get("glossaire"), ("terme", "definition", "source"))
    secs = []
    for sec in c.get("sections") or []:
        if isinstance(sec, dict):
            secs.append({**sec, "titre": txt(sec.get("titre")), "accroche": txt(sec.get("accroche")),
                         "slides": [slide(x) for x in (sec.get("slides") or [])]})
    c["sections"] = secs
    return c

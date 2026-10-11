"""Étape 2 — Télécharger un mémoire et en extraire les parties utiles.

Un mémoire confidentiel ou retiré n'est simplement pas téléchargeable :
on le marque « indisponible » et on passe au suivant.
"""
import hashlib
import re
import time
from urllib.parse import urljoin

import httpx
import pymupdf

from . import config

_last_call = 0.0


def _polite_get(url: str) -> httpx.Response:
    global _last_call
    wait = config.HTTP_DELAY_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
    return httpx.get(
        url, headers={"User-Agent": config.USER_AGENT},
        follow_redirects=True, timeout=60,
    )


def download(url: str) -> tuple[str | None, str | None]:
    """Retourne (chemin_pdf, None) ou (None, raison_de_l_echec)."""
    path = config.PDF_DIR / (hashlib.md5(url.encode()).hexdigest() + ".pdf")
    if path.exists():
        return str(path), None
    try:
        r = _polite_get(url)
    except httpx.HTTPError as e:
        return None, f"réseau : {e.__class__.__name__}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} (confidentiel ou retiré ?)"

    if not r.content.startswith(b"%PDF"):
        # Page HTML de notice : on cherche le lien vers le PDF dedans.
        links = re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', r.text, re.I)
        if not links:
            return None, "pas de PDF accessible sur la page"
        try:
            r = _polite_get(urljoin(str(r.url), links[0]))
        except httpx.HTTPError as e:
            return None, f"réseau : {e.__class__.__name__}"
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            return None, "lien PDF inaccessible"

    path.write_bytes(r.content)
    return str(path), None


# Titres de sections qu'on cherche dans les mémoires
_RESUME = r"(r[ée]sum[ée]|note de synth[èe]se|executive summary|synth[èe]se|abstract)"
_CONCL = r"(conclusion g[ée]n[ée]rale|conclusion|conclusions)"
_BIBLIO = r"(bibliographie|r[ée]f[ée]rences|annexes?)"


def _section(text: str, start_pat: str, max_chars: int) -> str:
    """Récupère le texte qui suit le titre de section (hors sommaire)."""
    matches = list(re.finditer(rf"^\s*(?:\d+[\.\s]*)?{start_pat}\s*$", text, re.I | re.M))
    for m in matches:
        chunk = text[m.end(): m.end() + max_chars]
        # Une entrée de sommaire ressemble à « ...... 12 » : on la saute.
        if len(re.findall(r"\.{5,}\s*\d+", chunk[:600])) < 2:
            return chunk.strip()
    return ""


def resolve(pdf_path: str) -> str:
    """Retrouve un PDF même si le dossier du projet a été déplacé (chemins stockés en absolu)."""
    from pathlib import Path
    p = Path(pdf_path)
    if p.exists():
        return str(p)
    local = config.PDF_DIR / p.name
    if local.exists():
        return str(local)
    raise FileNotFoundError(f"PDF introuvable : {p.name}")


def extract(pdf_path: str) -> dict:
    doc = pymupdf.open(resolve(pdf_path))
    pages = [p.get_text() for p in doc]
    full = "\n".join(pages)
    n_pages = len(pages)

    resume = _section(full, _RESUME, 9000)
    # Conclusion : on cherche dans la seconde moitié du document
    half = full[len(full) // 2:]
    conclusion = _section(half, _CONCL, 6000)
    conclusion = re.split(rf"^\s*{_BIBLIO}\s*$", conclusion, flags=re.I | re.M)[0]

    return {
        "n_pages": n_pages,
        "n_chars": len(full),
        "cover": "\n".join(pages[:2])[:3000],    # page de garde : titre, auteur, école, entreprise
        "resume": resume or "\n".join(pages[2:8])[:9000],
        "conclusion": conclusion[:6000],
        "full_text": full,
        "pages": pages,
    }


def paged_text(pages: list[str], mid: str) -> str:
    """Texte intégral avec un repère par page, pour des citations du type « M1 p.42 »."""
    return "\n".join(f"[[{mid} p.{i}]]\n{t.strip()}" for i, t in enumerate(pages, 1) if t.strip())


def passages_by_page(pages: list[str], mid: str, keywords: list[str], max_chars: int) -> str:
    """Lecture ciblée qui garde les numéros de page : les pages les plus pertinentes, dans l'ordre."""
    kws = [k.lower() for k in keywords if len(k) > 2]
    scored = sorted(
        ((sum(p.lower().count(k) for k in kws), i, p) for i, p in enumerate(pages, 1) if p.strip()),
        key=lambda x: -x[0],
    )
    keep, size = [], 0
    for score, i, p in scored:
        if score == 0 or size + len(p) > max_chars:
            continue
        keep.append((i, p))
        size += len(p)
    return "\n".join(f"[[{mid} p.{i}]]\n{p.strip()}" for i, p in sorted(keep))


def fetch_document(url: str) -> dict:
    """Document officiel (PDF ou page web) → {"pages": [...], "kind": "pdf"|"html", "path": ...}.

    Une page web sans PDF est découpée en pseudo-pages de ~3 000 caractères pour pouvoir être citée.
    """
    path = config.PDF_DIR / (hashlib.md5(url.encode()).hexdigest() + ".pdf")
    if not path.exists():
        r = _polite_get(url)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        if not r.content.startswith(b"%PDF"):
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            # une page d'annonce qui renvoie vers le document PDF : on suit le lien
            pdfs = [a["href"] for a in soup.find_all("a", href=True) if ".pdf" in a["href"].lower()]
            if pdfs and len(soup.get_text(" ", strip=True)) < 6000:
                r2 = _polite_get(urljoin(str(r.url), pdfs[0]))
                if r2.status_code == 200 and r2.content.startswith(b"%PDF"):
                    path.write_bytes(r2.content)
                    return {"pages": extract(str(path))["pages"], "kind": "pdf", "path": str(path)}
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
                tag.decompose()
            main = soup.find("main") or soup.find("article") or soup.body or soup
            text = re.sub(r"\n{3,}", "\n\n", main.get_text("\n", strip=True))
            pages = [text[i:i + 3000] for i in range(0, len(text), 3000)] or [""]
            return {"pages": pages, "kind": "html", "path": None}
        path.write_bytes(r.content)
    return {"pages": extract(str(path))["pages"], "kind": "pdf", "path": str(path)}


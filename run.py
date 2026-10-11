"""Ligne de commande : créer un cours sans l'interface.

Exemples :
  python run.py "Marge de risque sous Solvabilité II"
  python run.py "Prophet ALS et TVOG" --objectifs objectifs.txt --structure structure.txt \
                --pdf sarr_2017.pdf --pdf ouadeih_2018.pdf --uniquement --max-slides 60 --max-pages 40
Usage local (IACTUAIRE_LOCAL=1 et la clé dans .env). Les options non précisées reprennent tes réglages.
"""
import argparse
from pathlib import Path

from iactuaire import pipeline, runtime, settings
from iactuaire.synthesis import CourseRequest

r = settings.charger()
ap = argparse.ArgumentParser(description="IActuaire : un cours à partir de sources fiables")
ap.add_argument("theme")
ap.add_argument("--objectifs", help="fichier texte : ce que tu veux apprendre")
ap.add_argument("--structure", help="fichier texte : structure imposée")
ap.add_argument("--memoire", action="append", default=[], help="lien d'un mémoire à utiliser (répétable)")
ap.add_argument("--pdf", action="append", default=[], help="PDF d'un mémoire à utiliser (répétable)")
ap.add_argument("--uniquement", action="store_true", help="n'utiliser que les mémoires fournis")
ap.add_argument("--fournisseur", choices=list(runtime.PROVIDERS), default="anthropic",
                help="clé lue dans .env : ANTHROPIC_API_KEY ou OPENAI_API_KEY")
ap.add_argument("--modele", default=None, help="modèle de rédaction (par défaut selon le fournisseur)")
ap.add_argument("--modele-lecture", default=None)
ap.add_argument("--max-slides", type=int, default=r.max_slides)
ap.add_argument("--max-pages", type=int, default=r.max_pages_pdf)
ap.add_argument("--min-memoires", type=int, default=r.min_memoires)
ap.add_argument("--max-memoires", type=int, default=r.max_memoires)
ap.add_argument("--sources", default=",".join(r.sources), help="ex. memoires,eiopa,acpr")
a = ap.parse_args()

rt = runtime.get()
rt.provider = a.fournisseur
d = runtime.DEFAULT_MODELS[a.fournisseur]
r.modele = a.modele or (r.modele if a.fournisseur == "anthropic" else d["smart"])
r.modele_lecture = a.modele_lecture or (r.modele_lecture if a.fournisseur == "anthropic" else d["fast"])
r.max_slides, r.max_pages_pdf = a.max_slides, a.max_pages
r.min_memoires, r.max_memoires = a.min_memoires, a.max_memoires
r.sources = [s.strip() for s in a.sources.split(",") if s.strip() in settings.SOURCES]
read = lambda f: Path(f).read_text(encoding="utf-8").strip() if f else ""
req = CourseRequest(a.theme, objectifs=read(a.objectifs), structure=read(a.structure))
res = pipeline.run(req, r, imposed_urls=a.memoire, uploaded=[(Path(p).name, Path(p).read_bytes()) for p in a.pdf],
                   search=not (a.uniquement and (a.memoire or a.pdf)))
if res.pptx_path:
    print(f"\nCours : {res.pptx_path}\nPolycopié : {res.pdf_path}\nRapport qualité : {res.qa_path}\n{res.stats}")

"""Réglages d'un utilisateur : propres à sa session en public, enregistrés (data/reglages.json) en local."""
import json
from dataclasses import asdict, dataclass, field

from . import config, runtime

# Sources jugées fiables. « memoires » = mémoires d'actuariat ; les autres = documents officiels.
SOURCES = {
    "memoires": {"nom": "Ressources actuarielles (mémoires)",
                 "domaines": ["ressources-actuarielles.net", "institutdesactuaires.com"]},
    "eiopa": {"nom": "EIOPA", "domaines": ["eiopa.europa.eu"]},
    "acpr": {"nom": "ACPR", "domaines": ["acpr.banque-france.fr"]},
    "eurlex": {"nom": "EUR-Lex (textes réglementaires UE)", "domaines": ["eur-lex.europa.eu"]},
    "legifrance": {"nom": "Légifrance (Code des assurances)", "domaines": ["legifrance.gouv.fr"]},
    "ia": {"nom": "Institut des actuaires (publications)", "domaines": ["institutdesactuaires.com"]},
}


@dataclass
class Reglages:
    modele: str = "claude-sonnet-5-5"            # rédaction du cours et chef d'orchestre
    modele_lecture: str = "claude-haiku-5-5"     # lecture et notation des sources
    max_slides: int = 40                         # PowerPoint, toutes slides comprises
    max_pages_pdf: int = 30                      # polycopié
    min_memoires: int = 3                        # mémoires à lire au minimum
    max_memoires: int = 12                       # mémoires à lire au maximum
    max_docs_officiels: int = 4                  # documents EIOPA / ACPR… lus en entier
    seuil_pertinence: int = 6                    # /10
    sources: list = field(default_factory=lambda: ["memoires", "eiopa", "acpr"])
    controle_visuel: bool = True
    moteur_pdf: str = "quarto"                   # polycopié : « quarto » (Typst) ou « standard » (reportlab)
    auteur: str = ""                             # nom affiché sur la couverture des cours

    def officiels(self) -> list[str]:
        return [d for k in self.sources if k != "memoires" for d in SOURCES.get(k, {}).get("domaines", [])]

    def apply(self) -> "Reglages":
        """Répercute les réglages sur le contexte de l'utilisateur courant (jamais sur les autres)."""
        self.min_memoires = max(0, min(self.min_memoires, self.max_memoires))
        rt = runtime.get()
        rt.model_smart, rt.model_fast = self.modele, self.modele_lecture
        rt.min_relevance, rt.auteur = self.seuil_pertinence, self.auteur
        return self


FICHIER = config.DATA_DIR / "reglages.json"


def charger() -> Reglages:
    """En local : réglages enregistrés. En public : valeurs par défaut (chaque session a les siens)."""
    if not config.LOCAL:
        return Reglages().apply()
    try:
        data = json.loads(FICHIER.read_text(encoding="utf-8"))
        known = Reglages.__dataclass_fields__
        return Reglages(**{k: v for k, v in data.items() if k in known}).apply()
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return Reglages().apply()


def sauver(r: Reglages) -> None:
    if not config.LOCAL:
        return
    FICHIER.write_text(json.dumps(asdict(r), ensure_ascii=False, indent=1), encoding="utf-8")

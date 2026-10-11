# IActuaire

Se former à n'importe quel sujet d'actuariat financier à partir de sources fiables.
On tape un sujet ; IActuaire lit les mémoires de ressources-actuarielles et les textes officiels
(EIOPA, ACPR, et au choix EUR-Lex, Légifrance), puis remet un **cours PowerPoint** et son
**polycopié PDF**, chaque chiffre sourcé à la page (« M2 p.41 », « O1 p.12 »), avec contrôle qualité.

Conçu par Youssouf Dembélé.

## Comment l'utiliser (site public)

1. Choisir son fournisseur d'IA (Claude ou ChatGPT) et coller **sa propre clé API** dans « Votre accès IA ».
   Un abonnement Claude Pro ou ChatGPT Plus ne suffit pas : l'API est un produit séparé, facturé à l'usage.
   - Clé Claude : https://console.anthropic.com/settings/keys
   - Clé OpenAI : https://platform.openai.com/api-keys
2. Taper le sujet, régler le format (slides, pages, nombre de mémoires à lire), puis « Créer mon cours ».
3. Télécharger le PowerPoint et le polycopié. Garder l'onglet ouvert pendant la création.

La clé reste dans la session du visiteur : elle n'est ni enregistrée, ni partagée, ni visible des autres
visiteurs. Les PDF joints restent privés. Les fiches des mémoires publics déjà lus sont partagées entre
tous (un mémoire lu une fois ne l'est plus jamais) ; les cours, eux, sont propres à chaque visiteur et
effacés du serveur au bout de 24 h.

## Déployer sur Streamlit Community Cloud (gratuit)

1. **Mettre le code sur GitHub** : créer un dépôt (public ou privé) et y pousser ce dossier.
   `.gitignore` exclut déjà `.env` (ta clé), `data/` et tes réglages personnels.
2. Aller sur https://share.streamlit.io, se connecter avec GitHub, **Create app** → « Deploy a public
   app from GitHub ».
3. Choisir le dépôt et la branche ; **Main file path** : `iactuaire.py`.
4. **Advanced settings** → Python 3.12. Ne mets **aucune clé API dans les « Secrets »** : chaque
   visiteur utilise la sienne.
5. **Deploy**. Le premier démarrage prend quelques minutes (installation de LibreOffice via
   `packages.txt`, pour l'aperçu et la relecture visuelle des slides).

À savoir sur l'offre gratuite : l'application se met en veille après quelques jours sans visite (un clic
la réveille) et son disque est remis à zéro à chaque redémarrage (la bibliothèque commune de mémoires
repart de zéro, ce qui ne casse rien). Si l'installation de LibreOffice échoue, retire la première ligne
de `packages.txt` : tout fonctionne sans, hors aperçu et relecture visuelle.

## Usage local (sur ton ordinateur)

```bash
pip install -r requirements.txt
cp .env.example .env        # IACTUAIRE_LOCAL=1 et ta clé API
streamlit run iactuaire.py
```

En local, la clé est lue dans `.env`, tes réglages sont enregistrés, la bibliothèque montre tous tes cours
et l'onglet « Équipe d'experts » (questions libres sur la base de mémoires, avec Claude) est disponible.
En ligne de commande : `python run.py "Marge de risque sous Solvabilité II" --max-slides 30`
(`python run.py --help` pour toutes les options).

## Polycopié avec Quarto

Le polycopié peut être composé par **Quarto** (moteur Typst) ou par le moteur **Standard** intégré
(réglage « Mise en page du polycopié »). Les deux donnent la même charte ; si Quarto est absent ou échoue,
le moteur Standard prend le relais automatiquement.

- Installer Quarto (une fois) : https://quarto.org/docs/get-started/ (ou `brew install --cask quarto`).
- Chaque cours laisse, à côté du PDF, un dossier `…_polycopie_quarto/` (le `cours.qmd`, ses graphiques
  et le modèle) : on peut le retoucher et le recompiler avec `quarto render cours.qmd --to typst`.
- Le modèle est dans `templates/quarto/` : `typst-template.typ` (couverture, en-têtes, titres, encadrés,
  tableaux) et `iactuaire.lua` (blocs `::: boite`, `::: colonnes`, `::: chiffres`…).

## Personnaliser

- `templates/consignes_cours.md` : les exigences de fond et de forme appliquées à tous les cours.
- `templates/theme.json` (local, non publié) : nom par défaut sur la couverture, couleurs, police
  (voir `templates/LISEZMOI.txt`) ; `templates/logo.png` : un logo.

## Organisation du code

```
iactuaire.py        application
run.py              ligne de commande
packages.txt        paquets système pour Streamlit Cloud (LibreOffice, polices)
templates/quarto/   modèle Quarto/Typst du polycopié
iactuaire/
  runtime.py        contexte propre à chaque visiteur (clé, modèles, dossier) — jamais partagé
  llm.py            accès à Claude ou à OpenAI (texte, recherche web, images, liste des modèles)
  pipeline.py       déroulé complet : recherche, lecture, textes officiels, cours, contrôle, mise en page
  discovery.py      recherche des mémoires
  reader.py         téléchargement et extraction des PDF, page par page
  analyst.py        fiche et note de pertinence d'un mémoire
  official.py       textes officiels EIOPA / ACPR… lus en entier
  synthesis.py      plan et rédaction du cours, réponses aux questions
  render_pptx.py    PowerPoint (graphiques natifs, schémas, glossaire, sources)
  render_pdf.py     polycopié PDF (moteur Standard) et graphiques du polycopié
  render_quarto.py  polycopié PDF via Quarto (cours → .qmd → Typst), retour au Standard en cas d'échec
  qa.py             contrôle qualité (chiffres, débordements, rendu visuel)
  orchestrator.py   équipe d'experts (usage local)
  settings.py       réglages de l'utilisateur
  db.py, theme.py, config.py
```

# Exemple de demande (à copier dans l'application, champ par champ)

## Thème du cours
Prophet ALS : PVFP, TVOG, allocation d'actifs et interactions actif-passif en épargne euro

## Ce que je veux apprendre
Prophet / Prophet ALS, la PVFP, la TVOG, l'allocation d'actifs, la modélisation des actifs dans
Prophet et la modélisation des interactions actif-passif dans Prophet.

## Mémoires à utiliser (joindre les PDF ou coller les liens) — cocher « uniquement ces mémoires »
- A. SARR, ISFA / Aviva France Vie, 2017 – modèle ALM Prophet ALS
- M. A. OUADEIH, ENSAE / Crédit Agricole Assurances, 2018 – méthodes Flexing et Internal

## Structure attendue
1. Prophet ALS :
   - ce qu'est l'outil, le modèle déterministe et le modèle stochastique, le flexing ;
   - la chaîne données → générateur de scénarios → modèle ALM → résultats ;
   - l'interface (Run Control, tables .fac, runs numérotés) et la nomenclature des fichiers ;
   - les variables core et input (fenêtre Variable Properties, contraintes) ;
   - un dictionnaire des variables avec leur enchaînement ;
   - les tables ASSET_POOL_BASIS, ASSET_EQUITY et ASSET_BOND champ par champ ;
   - les 19 pools ; la lecture d'une sortie (D_PROFIT_PL) ;
   - les variables du passif (NO_*, MT_*, _PP, LAPSE_TIMING…) avec leurs formules ;
   - la boucle de calcul d'un modèle ALM sous Prophet.
2. PVFP et TVOG :
   - les définitions (VIF = PVFP − TVOG) et l'asymétrie assureur / assurés ;
   - un exemple réel chiffré en graphique en cascade ;
   - les facteurs qui font varier la TVOG.
3. Allocation d'actifs :
   - le portefeuille réel ; cible et allocation constatée ;
   - valeur comptable ou valeur de marché ;
   - allocation statique ou dynamique ;
   - un exemple pas à pas ; les règles d'achat-vente de deux assureurs.
4. Modélisation des actifs dans Prophet :
   - processus, catégorisation, catégories, tables ;
   - calcul des proportions d'un pool ;
   - valorisation des indices et des obligations, plus-values latentes ;
   - achats et ventes ; gross-up et asset scalar.
5. Interactions actif-passif dans Prophet :
   - la boucle actif-passif ; les flux de passif, avec les données de marché ;
   - la chronologie d'une période ; les phases BD / BR / AR, avec une matrice de ce
     qui est autorisé à chaque phase ; le réalignement ;
   - les réserves (RC, PRE, PPE) ;
   - la participation aux bénéfices : minimum réglementaire, taux servi en 6 étapes,
     arbre de décision, PPE en 9 générations ;
   - Flexing ou Internal ; la table DET_CF et les ratios de flexing ;
   - les formules du BE et de la VIF ; l'exemple chiffré BE + VIF ≈ actif.

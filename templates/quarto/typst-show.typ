// Appel du modèle : les valeurs viennent de l'en-tête YAML du .qmd (bloc `iact:`)
#show: doc => iactuaire(
$if(title)$
  title: [$title$],
$endif$
$if(subtitle)$
  subtitle: [$subtitle$],
$endif$
$if(iact.surtitre)$
  surtitre: [$iact.surtitre$],
$endif$
$if(iact.ligne)$
  ligne: [$iact.ligne$],
$endif$
  pied: [$iact.pied$],
$if(iact.logo)$
  logo: "$iact.logo$",
$endif$
$if(iact.auteur)$
  auteur: "$iact.auteur$",
$endif$
  credit: "$iact.credit$",
$if(lang)$
  lang: "$lang$",
$endif$
  doc,
)

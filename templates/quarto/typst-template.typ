// =============================================================================
// IActuaire — modèle Typst du polycopié (utilisé par Quarto, format `typst`)
//
// Reproduit la charte du polycopié : bandeau rouge sur la couverture, petit trait
// rouge en haut de page, pied de page (titre du cours + numéro), titres rouges,
// encadrés « À retenir », « Point de vigilance », formules, chiffres clés…
//
// Les couleurs, la police et l'auteur viennent de templates/theme.json (via le
// générateur) : il n'est pas nécessaire de les modifier ici.
// =============================================================================

// ---------------------------------------------------------------- charte
#let iact-red = rgb("#$iact.red$")
#let iact-red-dark = rgb("#$iact.red-dark$")
#let iact-ink = rgb("#$iact.ink$")
#let iact-grey = rgb("#$iact.grey$")
#let iact-line = rgb("#$iact.line$")
#let iact-panel = rgb("#$iact.panel$")
#let iact-soft = rgb("#$iact.soft$")
#let iact-body-size = $iact.corps$
#let iact-fonts = ("$iact.police$", "Arial", "Helvetica", "Liberation Sans", "DejaVu Sans")
#let iact-mono = ("$iact.mono$", "Consolas", "Courier New", "Liberation Mono", "DejaVu Sans Mono")

// ---------------------------------------------------------------- blocs du cours
// Encadré à filet vertical (À retenir, Point de vigilance, encadrés des slides, formules)
#let boite(fond: "panel", barre: "red", body) = {
  let bg = if fond == "soft" { iact-soft } else if fond == "white" { white } else { iact-panel }
  let bar = if barre == "red-dark" { iact-red-dark } else { iact-red }
  block(width: 100%, fill: bg, stroke: (left: 3pt + bar), inset: (left: 12pt, rest: 8pt),
        above: 8pt, below: 8pt, breakable: false, body)
}

// Tuiles de même hauteur, côte à côte (la plus haute donne la hauteur des autres)
#let tuiles(items, tuile) = layout(size => {
  let n = items.len()
  if n == 0 { return }
  let w = (size.width - 6pt * (n - 1)) / n
  let h = calc.max(..items.map(x => measure(tuile(x, w, auto)).height))
  grid(columns: (w,) * n, column-gutter: 6pt, ..items.map(x => tuile(x, w, h)))
})

// Deux colonnes sur fond clair, filet rouge en haut
#let colonnes(..cols) = tuiles(cols.pos(), (x, w, h) => block(width: w, height: h,
  fill: iact-panel, stroke: (top: 2pt + iact-red), inset: 8pt, x))

// Chiffres clés : valeur en grand, libellé dessous, filet rouge en bas
#let chiffres(..items) = tuiles(items.pos(), ((valeur, libelle), w, h) => block(width: w, height: h,
  fill: iact-panel, stroke: (bottom: 2pt + iact-red), inset: 8pt, align(center)[
    #text(size: 20pt, weight: "bold", fill: iact-red, valeur) \
    #v(2pt) #text(size: 9pt, libelle)
  ]))

// Passe à la page suivante s'il reste moins de `h` sur la page (évite un titre seul en bas de page)
#let besoin(h) = {
  block(width: 100%, height: h, breakable: false, above: 0pt, below: 0pt)
  v(-h)
}

// Petit texte gris (accroches, sources, légendes)
#let petit(body) = block(above: 4pt, below: 6pt, text(size: 8.5pt, fill: iact-grey, body))

// Étiquette rouge (titres de colonnes, noms de formules)
#let etiquette(body) = text(weight: "bold", fill: iact-red, body)

// ---------------------------------------------------------------- document
#let iactuaire(
  title: none,
  subtitle: none,
  surtitre: "SUPPORT DE COURS",
  ligne: none,
  pied: none,
  logo: none,
  auteur: none,
  credit: none,
  lang: "fr",
  doc,
) = {
  set document(title: pied, author: if auteur != none { auteur } else { "IActuaire" },
               description: credit)
  set text(font: iact-fonts, size: iact-body-size, fill: iact-ink, lang: lang)
  set par(justify: false, leading: 0.85em, spacing: 1.35em)

  // Titres : niveau 1 rouge (parties), niveau 2 encre (sous-parties)
  show heading: set block(sticky: true)
  show heading.where(level: 1): it => block(above: 6pt, below: 8pt,
    text(size: 20pt, weight: "bold", fill: iact-red, it.body))
  show heading.where(level: 2): it => block(above: 20pt, below: 9pt,
    text(size: 13pt, weight: "bold", fill: iact-ink, it.body))
  show heading.where(level: 3): it => block(above: 10pt, below: 6pt,
    text(size: 10.5pt, weight: "bold", fill: iact-red, it.body))

  // Gras = rouge (verbes des objectifs, « À retenir », « Lecture — »…)
  show strong: set text(fill: iact-red)
  // Listes à puces rouges
  set list(marker: text(fill: iact-red)[•], indent: 4pt, body-indent: 8pt, spacing: 1.0em)
  // Formules : police à chasse fixe
  show raw: set text(font: iact-mono, size: 1.0em)
  // Blocs de code : fond clair, filet sombre, petite taille, coupables entre deux pages
  show raw.where(block: true): set block(fill: none, inset: 0pt, radius: 0pt, stroke: none)
  show raw.where(block: true): it => block(width: 100%, fill: iact-panel, stroke: (left: 3pt + iact-ink), radius: 0pt,
    inset: (left: 10pt, rest: 7pt), above: 6pt, below: 8pt, breakable: true,
    { set par(leading: 0.48em); text(size: 7.4pt, it) })
  // Liens : même couleur que le texte
  show link: set text(fill: iact-ink)

  // Tableaux : en-tête rouge, lignes alternées, filets fins
  set table(
    inset: (x: 5pt, y: 4pt),
    align: left + top,
    fill: (_, y) => if y == 0 { iact-red } else if calc.even(y) { iact-panel } else { white },
    stroke: (_, y) => (bottom: 0.4pt + iact-line),
  )
  show table.cell: set text(size: 9pt)
  show table.cell: set par(leading: 0.55em, spacing: 0.6em)
  show table.cell.where(y: 0): set text(fill: white, weight: "bold")
  show figure.where(kind: table): set block(breakable: true)
  show figure: set block(above: 8pt, below: 8pt)

  // ------------------------------------------------------------ couverture
  page(
    paper: "a4",
    margin: (left: 2.5cm, right: 2cm, top: 2cm, bottom: 2cm),
    background: place(left + top, rect(width: 1.2cm, height: 100%, fill: iact-red)),
    header: none, footer: none,
  )[
    #if logo != none { place(top + right, dy: -0.8cm, image(logo, height: 1.6cm)) }
    #v(6cm)
    #text(size: 10.5pt, weight: "bold", fill: iact-red, surtitre)
    #v(8pt)
    #block(text(size: 28pt, weight: "bold", fill: iact-ink, hyphenate: false,
                par(leading: 0.42em, title)))
    #v(10pt)
    #if subtitle != none { subtitle }
    #v(3cm)
    #if ligne != none { text(size: 8.5pt, fill: iact-grey, ligne) }
  ]

  // ------------------------------------------------------------ pages courantes
  set page(
    paper: "a4",
    margin: (left: 2cm, right: 2cm, top: 2.2cm, bottom: 2cm),
    header-ascent: 0pt,
    header: {
      place(top + left, dy: 1.23cm, rect(width: 1.2cm, height: 0.12cm, fill: iact-red))
      if logo != none { place(top + right, dy: 0.9cm, image(logo, height: 0.8cm)) }
    },
    footer-descent: 0.45cm,
    footer: {
      line(length: 100%, stroke: 0.5pt + iact-line)
      v(-2pt)
      set text(size: 8pt, fill: iact-grey)
      grid(columns: (1fr, auto), pied, context counter(page).display())
    },
  )
  doc
}

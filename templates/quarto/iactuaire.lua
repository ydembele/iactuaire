--[[
IActuaire — filtre Quarto/Pandoc du polycopié.

Transforme les blocs Markdown du .qmd en éléments du modèle Typst :

  ::: {.boite fond="soft"}            → #boite(fond: "soft")[…]
  ::: {.boite fond="white" barre="red-dark"}
  ::: colonnes  (avec ::: colonne)     → #colonnes([…], […])
  ::: chiffres  (avec ::: {.chiffre valeur="85 %" libelle="…"})
  ::: petit                            → texte gris
  ::: {.tableau largeurs="1,3"}        → largeurs relatives des colonnes du tableau qu'il contient
  ::: saut                             → saut de page
  ::: {.besoin hauteur="5cm"}           → saut de page s'il reste moins de 5 cm

Tous les tableaux occupent toute la largeur (colonnes égales si rien n'est précisé).
]]

local function raw(s) return pandoc.RawBlock("typst", s) end

local function typst_str(s)
  s = s:gsub("\\", "\\\\"):gsub('"', '\\"')
  return '"' .. s .. '"'
end

local function wrap(open, blocks, close)
  local out = { raw(open) }
  for _, b in ipairs(blocks) do table.insert(out, b) end
  table.insert(out, raw(close))
  return out
end

local function full_width(tbl, weights)
  local n = #tbl.colspecs
  local total = 0
  local w = {}
  for i = 1, n do
    w[i] = (weights and tonumber(weights[i])) or 1
    total = total + w[i]
  end
  for i = 1, n do
    tbl.colspecs[i] = { tbl.colspecs[i][1], w[i] / total }
  end
  return tbl
end

local function split(s)
  local t = {}
  for x in string.gmatch(s or "", "[^,]+") do table.insert(t, x) end
  return t
end

function Table(tbl)
  -- tableau ordinaire : pleine largeur, colonnes égales (sauf si déjà fixées)
  local fixed = false
  for _, cs in ipairs(tbl.colspecs) do
    if type(cs[2]) == "number" and cs[2] > 0 then fixed = true end
  end
  if not fixed then return full_width(tbl, nil) end
  return tbl
end

function Div(el)
  local c = el.classes
  if c:includes("tableau") then
    local weights = split(el.attributes["largeurs"])
    return pandoc.walk_block(el, { Table = function(t) return full_width(t, weights) end }).content
  end
  if c:includes("boite") then
    local fond = el.attributes["fond"] or "panel"
    local barre = el.attributes["barre"] or "red"
    return wrap(string.format('#boite(fond: "%s", barre: "%s")[', fond, barre), el.content, "]")
  end
  if c:includes("petit") then
    return wrap("#petit[", el.content, "]")
  end
  if c:includes("besoin") then
    return raw("#besoin(" .. (el.attributes["hauteur"] or "5cm") .. ")")
  end
  if c:includes("saut") then
    return raw("#pagebreak(weak: true)")
  end
  if c:includes("colonnes") then
    local out = { raw("#colonnes(") }
    for _, child in ipairs(el.content) do
      if child.t == "Div" then
        table.insert(out, raw("["))
        for _, b in ipairs(child.content) do table.insert(out, b) end
        table.insert(out, raw("],"))
      end
    end
    table.insert(out, raw(")"))
    return out
  end
  if c:includes("chiffres") then
    local items = {}
    for _, child in ipairs(el.content) do
      if child.t == "Div" then
        table.insert(items, "(" .. typst_str(child.attributes["valeur"] or "") .. ", "
          .. typst_str(child.attributes["libelle"] or "") .. ")")
      end
    end
    return raw("#chiffres(" .. table.concat(items, ", ") .. ")")
  end
  return nil
end

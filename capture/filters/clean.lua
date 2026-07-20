-- Pandoc filter for HTML -> markdown capture conversion.

-- KaTeX server-side rendering wraps display equations in a
-- span.katex-display, but pandoc recovers the TeX (from the MathML
-- annotation) as InlineMath. Promote it back to DisplayMath so the
-- gfm writer emits a ```math block instead of an inline span.
function Span(el)
  if el.classes:includes('katex-display') then
    local tex
    el:walk({ Math = function(m) tex = m.text end })
    if tex then
      return pandoc.Math(pandoc.DisplayMath, tex)
    end
  end
end

-- A table with exactly one cell is a layout wrapper (1990s centering
-- tables, e.g. xkcd.com/solution.html): unwrap it, since the gfm
-- writer would collapse block content in tables to "[TABLE]".
function Table(el)
  local cells = {}
  local function collect(rows)
    for _, row in ipairs(rows) do
      for _, cell in ipairs(row.cells) do
        table.insert(cells, cell)
      end
    end
  end
  collect(el.head.rows)
  for _, body in ipairs(el.bodies) do
    collect(body.head)
    collect(body.body)
  end
  collect(el.foot.rows)
  if #cells == 1 then
    return cells[1].contents
  end
end

-- Pandoc writes code blocks as indented markdown unless they carry a
-- language, and syntax highlighters leave junk classes ("highlight")
-- that gfm drops: normalize so every block comes out fenced.
function CodeBlock(el)
  if #el.classes == 0 or el.classes[1] == 'highlight' then
    el.classes = { 'text' }
    return el
  end
end

-- Jekyll/Rouge put the language on an ancestor div
-- (<div class="language-ruby highlighter-rouge">): push it down onto
-- the code block. Runs after CodeBlock (pandoc walks bottom-up), so
-- this overrides the 'text' placeholder.
function Div(el)
  for _, cls in ipairs(el.classes) do
    local lang = cls:match('^language%-(.+)$')
    if lang then
      return el:walk({
        CodeBlock = function(block)
          block.classes = { lang }
          return block
        end,
      })
    end
  end
end

-- Some sites (AoPS, wp-latex) render math as images whose alt text is
-- the TeX source: recover the math. Otherwise, drop base64 data: URI
-- images (single-file inlines them and they dwarf the prose), keeping
-- their caption.
function Image(el)
  local alt = pandoc.utils.stringify(el.caption)
  local tex = alt:match('^%$+(.-)%$+$')
  if tex and tex ~= '' then
    local style = alt:match('^%$%$') and pandoc.DisplayMath or pandoc.InlineMath
    return pandoc.Math(style, tex)
  end
  if el.src:match('^data:') then
    return alt ~= '' and pandoc.Emph(el.caption) or {}
  end
end

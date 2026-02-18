-- hwpx-filter.lua
-- Complete HWPX converter for Quarto (pure Lua, no Python dependency)
-- Converts Pandoc AST directly to HWPX document format.

-- ══════════════════════════════════════════════════════════════════════
-- PART 1: Constants and Configuration
-- ══════════════════════════════════════════════════════════════════════

local SCRIPT_DIR = PANDOC_SCRIPT_FILE:match("(.*[/\\])") or "./"

local LANG_FONT_MAP = {
  HANGUL   = 'NanumSquareOTF',
  LATIN    = 'NimbusSanL',
  HANJA    = 'Noto Sans CJK KR',
  JAPANESE = 'Noto Sans CJK KR',
  OTHER    = 'NimbusSanL',
  SYMBOL   = 'STIX Two Text',
  USER     = 'NimbusSanL',
}

local HEADING_STYLE = {
  [1] = {style=2, para=2, char=7},
  [2] = {style=3, para=3, char=8},
  [3] = {style=4, para=4, char=9},
  [4] = {style=5, para=5, char=0},
  [5] = {style=6, para=6, char=0},
  [6] = {style=7, para=7, char=0},
}

local HEADING_CHAR_PROPS = {
  {id=7,  height=2200, bold=true,  font_ref=0},
  {id=8,  height=1600, bold=true,  font_ref=0},
  {id=9,  height=1300, bold=false, font_ref=0},
}

local HEADING_SPACING = { [2]=800, [3]=600, [4]=400 }

local CODE_CHAR_PR_ID = 10
local CODE_FONT_REF   = 2

local CHAR_HEIGHT_MAP = {
  [0]=1000, [7]=2200, [8]=1600, [9]=1300, [10]=1000,
}

local TABLE_BORDER_FILL_ID = 3
local PAGE_TEXT_WIDTH = 42520
local CHAR_HEIGHT_NORMAL = 1000
local LINE_SPACING_PCT = 160
local LUNIT_PER_MM = 283.465

-- ══════════════════════════════════════════════════════════════════════
-- PART 2: State
-- ══════════════════════════════════════════════════════════════════════

local para_id_counter = 3121190098
local max_char_pr_id = CODE_CHAR_PR_ID
local char_pr_cache = {}
local images = {}

local function next_para_id()
  para_id_counter = para_id_counter + 1
  return tostring(para_id_counter)
end

local function unique_id()
  return tostring(math.floor(os.clock() * 1000000) % 100000000 + math.random(0, 10000))
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 3: Utility Functions
-- ══════════════════════════════════════════════════════════════════════

local function xml_escape(s)
  if not s then return '' end
  return s:gsub('&', '&amp;'):gsub('<', '&lt;'):gsub('>', '&gt;')
           :gsub('"', '&quot;'):gsub("'", '&apos;')
end

local function file_exists(path)
  local f = io.open(path, 'rb')
  if f then f:close(); return true end
  return false
end

local function read_file(path)
  local f = io.open(path, 'r')
  if not f then return nil end
  local content = f:read('*a')
  f:close()
  return content
end

local function write_file(path, content)
  local f = io.open(path, 'w')
  if not f then return false end
  f:write(content)
  f:close()
  return true
end

local function shell_escape(s)
  return "'" .. s:gsub("'", "'\\''") .. "'"
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 4: Image Dimension Reader
-- ══════════════════════════════════════════════════════════════════════

local function get_png_dimensions(path)
  local f = io.open(path, 'rb')
  if not f then return nil, nil end
  local header = f:read(24)
  f:close()
  if not header or #header < 24 then return nil, nil end
  if header:byte(1) ~= 137 or header:byte(2) ~= 80 then return nil, nil end
  local w = header:byte(17)*16777216 + header:byte(18)*65536
          + header:byte(19)*256 + header:byte(20)
  local h = header:byte(21)*16777216 + header:byte(22)*65536
          + header:byte(23)*256 + header:byte(24)
  return w, h
end

local function get_jpeg_dimensions(path)
  local f = io.open(path, 'rb')
  if not f then return nil, nil end
  local data = f:read('*a')
  f:close()
  local i = 3
  while i < #data - 8 do
    if data:byte(i) == 0xFF then
      local marker = data:byte(i+1)
      if marker >= 0xC0 and marker <= 0xCF and marker ~= 0xC4 and marker ~= 0xC8 and marker ~= 0xCC then
        local h = data:byte(i+5)*256 + data:byte(i+6)
        local w = data:byte(i+7)*256 + data:byte(i+8)
        return w, h
      end
      local seg_len = data:byte(i+2)*256 + data:byte(i+3)
      i = i + 2 + seg_len
    else
      i = i + 1
    end
  end
  return nil, nil
end

local function get_image_dimensions(path)
  if not path or not file_exists(path) then return nil, nil end
  local lower = path:lower()
  if lower:match('%.png$') then
    return get_png_dimensions(path)
  elseif lower:match('%.jpe?g$') then
    return get_jpeg_dimensions(path)
  end
  return nil, nil
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 5: Math Converter (LaTeX → HWP Script)
-- ══════════════════════════════════════════════════════════════════════

local function latex_to_hwp_script(latex)
  local s = latex:match('^%s*(.-)%s*$')
  s = s:gsub('^%$', ''):gsub('%$$', '')
  s = s:gsub('\\frac{([^}]*)}{([^}]*)}', '{%1} over {%2}')
  s = s:gsub('\\sum_{([^}]*)}%^{([^}]*)}', 'sum from{%1} to{%2}')
  s = s:gsub('\\int_{([^}]*)}%^{([^}]*)}', 'int from{%1} to{%2}')
  s = s:gsub('\\sqrt{([^}]*)}', 'sqrt{%1}')
  s = s:gsub('\\left%(', 'left('):gsub('\\right%)', 'right)')
  s = s:gsub('\\left%[', 'left['):gsub('\\right%]', 'right]')
  s = s:gsub('\\left\\{', 'left lbrace '):gsub('\\right\\}', 'right rbrace ')
  local symbols = {
    {'\\geq','>='},{'\\leq','<='},{'\\neq','<>'},
    {'\\times','times'},{'\\cdot','cdot'},{'\\cdots','cdots'},
    {'\\ldots','ldots'},{'\\infty','inf'},{'\\pm','+-'},
    {'\\mp','-+'},{'\\approx','approx'},{'\\equiv','equiv'},
    {'\\partial','partial'},{'\\nabla','nabla'},
    {'\\rightarrow','rightarrow'},{'\\leftarrow','leftarrow'},
    {'\\Rightarrow','Rightarrow'},{'\\Leftarrow','Leftarrow'},
  }
  for _, pair in ipairs(symbols) do
    s = s:gsub(pair[1]:gsub('\\', '\\\\'), pair[2])
  end
  s = s:gsub('\\([a-zA-Z]+)', '%1')
  return s
end

local function make_equation_xml(latex_str)
  local script = latex_to_hwp_script(latex_str)
  local safe = xml_escape(script)
  return '<hp:equation version="eqEdit" baseLine="0"'
    .. ' textColor="#000000" baseUnit="1000" lineMode="0" font="">'
    .. '<hp:script>' .. safe .. '</hp:script>'
    .. '</hp:equation>'
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 6: Lineseg Calculator
-- ══════════════════════════════════════════════════════════════════════

local function compute_lineseg_xml(text, char_height, horzsize)
  char_height = char_height or CHAR_HEIGHT_NORMAL
  horzsize = horzsize or PAGE_TEXT_WIDTH
  local vertsize = char_height
  local spacing = math.floor(char_height * (LINE_SPACING_PCT - 100) / 100)
  local line_height = vertsize + spacing
  local baseline = math.floor(char_height * 0.85)

  if not text or text == '' then
    return '<hp:linesegarray>'
      .. '<hp:lineseg textpos="0" vertpos="0" vertsize="' .. vertsize .. '"'
      .. ' textheight="' .. vertsize .. '" baseline="' .. baseline .. '"'
      .. ' spacing="' .. spacing .. '" horzpos="0" horzsize="' .. horzsize .. '"'
      .. ' flags="393216"/>'
      .. '</hp:linesegarray>'
  end

  local line_starts = {0}
  local current_width = 0
  local len = utf8.len(text) or #text
  local i = 0
  for _, code in utf8.codes(text) do
    if code > 0x2000 then
      current_width = current_width + char_height
    else
      current_width = current_width + math.floor(char_height / 2)
    end
    i = i + 1
    if current_width > horzsize and i < len then
      line_starts[#line_starts + 1] = i
      current_width = 0
    end
  end

  local num_lines = #line_starts
  local parts = {'<hp:linesegarray>'}
  for idx, textpos in ipairs(line_starts) do
    local vertpos = (idx - 1) * line_height
    local flags
    if num_lines == 1 then flags = 393216
    elseif idx == 1 then flags = 131072
    elseif idx == num_lines then flags = 262144
    else flags = 0 end
    parts[#parts+1] = '<hp:lineseg textpos="' .. textpos .. '" vertpos="' .. vertpos .. '"'
      .. ' vertsize="' .. vertsize .. '" textheight="' .. vertsize .. '"'
      .. ' baseline="' .. baseline .. '" spacing="' .. spacing .. '"'
      .. ' horzpos="0" horzsize="' .. horzsize .. '" flags="' .. flags .. '"/>'
  end
  parts[#parts+1] = '</hp:linesegarray>'
  return table.concat(parts)
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 7: XML Builders
-- ══════════════════════════════════════════════════════════════════════

local function make_paragraph_xml(text, char_pr_id, style_id, para_pr_id)
  char_pr_id = char_pr_id or '0'
  style_id = style_id or '0'
  para_pr_id = para_pr_id or '0'
  local pid = next_para_id()
  local safe_text = xml_escape(text)
  local ch = CHAR_HEIGHT_MAP[tonumber(char_pr_id) or 0] or CHAR_HEIGHT_NORMAL
  local lineseg = compute_lineseg_xml(text, ch)
  return '<hp:p id="' .. pid .. '" paraPrIDRef="' .. para_pr_id .. '"'
    .. ' styleIDRef="' .. style_id .. '"'
    .. ' pageBreak="0" columnBreak="0" merged="0">'
    .. '<hp:run charPrIDRef="' .. char_pr_id .. '">'
    .. '<hp:t>' .. safe_text .. '</hp:t></hp:run>'
    .. lineseg
    .. '</hp:p>'
end

local function make_rich_paragraph_xml(runs_xml, lineseg_text, style_id, para_pr_id)
  style_id = style_id or '0'
  para_pr_id = para_pr_id or '0'
  local pid = next_para_id()
  local lineseg = ''
  if lineseg_text then
    lineseg = compute_lineseg_xml(lineseg_text)
  end
  return '<hp:p id="' .. pid .. '" paraPrIDRef="' .. para_pr_id .. '"'
    .. ' styleIDRef="' .. style_id .. '"'
    .. ' pageBreak="0" columnBreak="0" merged="0">'
    .. runs_xml .. lineseg .. '</hp:p>'
end

local function make_charpr_xml(cpr_id, height, opts)
  opts = opts or {}
  local bold_attr = opts.bold and ' bold="1"' or ''
  local italic_attr = opts.italic and ' italic="1"' or ''
  local color = opts.text_color or '#000000'
  local ul_type = opts.underline and 'BOTTOM' or 'NONE'
  local ul_color = opts.text_color or '#000000'
  local so_shape = opts.strikeout and 'SOLID' or 'NONE'
  local font_ref = opts.font_ref or 0
  return '<hh:charPr id="' .. cpr_id .. '" height="' .. height .. '"'
    .. ' textColor="' .. color .. '" shadeColor="none"'
    .. ' useFontSpace="0" useKerning="0" symMark="NONE"'
    .. ' borderFillIDRef="2"' .. bold_attr .. italic_attr .. '>'
    .. '<hh:fontRef hangul="' .. font_ref .. '" latin="' .. font_ref .. '"'
    .. ' hanja="' .. font_ref .. '" japanese="' .. font_ref .. '"'
    .. ' other="' .. font_ref .. '" symbol="' .. font_ref .. '" user="' .. font_ref .. '"/>'
    .. '<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    .. '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    .. '<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
    .. '<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
    .. '<hh:underline type="' .. ul_type .. '" shape="SOLID" color="' .. ul_color .. '"/>'
    .. '<hh:strikeout shape="' .. so_shape .. '" color="#000000"/>'
    .. '<hh:outline type="NONE"/>'
    .. '<hh:shadow type="NONE" color="#C0C0C0" offsetX="10" offsetY="10"/>'
    .. '</hh:charPr>'
end

local function make_font_xml(font_id, face_name)
  return '<hh:font id="' .. font_id .. '" face="' .. face_name .. '" type="TTF" isEmbedded="0">'
    .. '<hh:typeInfo familyType="FCAT_GOTHIC" weight="6" proportion="4" contrast="0"'
    .. ' strokeVariation="1" armStyle="1" letterform="1" midline="1" xHeight="1"/>'
    .. '</hh:font>'
end

local function make_table_borderfill_xml()
  return '<hh:borderFill id="' .. TABLE_BORDER_FILL_ID .. '" threeD="0"'
    .. ' shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
    .. '<hh:slash type="NONE" Crooked="0" isCounter="0"/>'
    .. '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
    .. '<hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>'
    .. '<hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>'
    .. '<hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>'
    .. '<hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>'
    .. '<hh:diagonal type="NONE" width="0.12 mm" color="#000000"/>'
    .. '</hh:borderFill>'
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 8: CharPr Management (built-in mode only)
-- ══════════════════════════════════════════════════════════════════════

local function formats_key(base_id, formats)
  local sorted = {}
  for fmt in pairs(formats) do sorted[#sorted+1] = fmt end
  table.sort(sorted)
  return base_id .. ':' .. table.concat(sorted, ',')
end

local function get_builtin_char_pr_id(base_id, active_formats)
  if not active_formats or not next(active_formats) then
    return tostring(base_id)
  end
  local key = formats_key(tostring(base_id), active_formats)
  if char_pr_cache[key] then
    return char_pr_cache[key].id
  end
  max_char_pr_id = max_char_pr_id + 1
  local new_id = tostring(max_char_pr_id)
  char_pr_cache[key] = {
    id = new_id,
    base_id = tostring(base_id),
    formats = active_formats,
  }
  return new_id
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 9: Plain Text Extraction
-- ══════════════════════════════════════════════════════════════════════

local function get_plain_text(inlines)
  if not inlines then return '' end
  local parts = {}
  for _, item in ipairs(inlines) do
    local t = item.t
    if t == 'Str' then
      parts[#parts+1] = item.text
    elseif t == 'Space' then
      parts[#parts+1] = ' '
    elseif t == 'SoftBreak' then
      parts[#parts+1] = ' '
    elseif t == 'LineBreak' then
      parts[#parts+1] = '\n'
    elseif t == 'Strong' or t == 'Emph' or t == 'Strikeout'
        or t == 'Superscript' or t == 'Subscript'
        or t == 'SmallCaps' or t == 'Underline' then
      parts[#parts+1] = get_plain_text(item.content)
    elseif t == 'Code' then
      parts[#parts+1] = item.text
    elseif t == 'Link' then
      parts[#parts+1] = get_plain_text(item.content)
    elseif t == 'Image' then
      parts[#parts+1] = get_plain_text(item.content)
    elseif t == 'Quoted' then
      local qt = item.quotetype
      local q1 = qt == 'DoubleQuote' and '\u{201c}' or '\u{2018}'
      local q2 = qt == 'DoubleQuote' and '\u{201d}' or '\u{2019}'
      parts[#parts+1] = q1 .. get_plain_text(item.content) .. q2
    elseif t == 'Cite' then
      parts[#parts+1] = get_plain_text(item.content)
    elseif t == 'Math' then
      parts[#parts+1] = item.text
    elseif t == 'Span' then
      parts[#parts+1] = get_plain_text(item.content)
    end
  end
  return table.concat(parts)
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 10: Hyperlink / Footnote
-- ══════════════════════════════════════════════════════════════════════

local last_field_id = '0'

local function create_field_begin(url)
  local fid = unique_id()
  last_field_id = fid
  local command_url = url:gsub(':', '\\:'):gsub('%?', '\\?')
  local command_str = command_url .. ';1;5;-1;'
  return '<hp:run charPrIDRef="0"><hp:ctrl>'
    .. '<hp:fieldBegin id="' .. fid .. '" type="HYPERLINK" name=""'
    .. ' editable="0" dirty="1" zorder="-1" fieldid="' .. fid .. '" metaTag="">'
    .. '<hp:parameters cnt="6" name="">'
    .. '<hp:integerParam name="Prop">0</hp:integerParam>'
    .. '<hp:stringParam name="Command">' .. command_str .. '</hp:stringParam>'
    .. '<hp:stringParam name="Path">' .. xml_escape(url) .. '</hp:stringParam>'
    .. '<hp:stringParam name="Category">HWPHYPERLINK_TYPE_URL</hp:stringParam>'
    .. '<hp:stringParam name="TargetType">HWPHYPERLINK_TARGET_HYPERLINK</hp:stringParam>'
    .. '<hp:stringParam name="DocOpenType">HWPHYPERLINK_JUMP_DONTCARE</hp:stringParam>'
    .. '</hp:parameters>'
    .. '</hp:fieldBegin>'
    .. '</hp:ctrl></hp:run>'
end

local function create_field_end()
  return '<hp:run charPrIDRef="0"><hp:ctrl>'
    .. '<hp:fieldEnd beginIDRef="' .. last_field_id .. '" fieldid="' .. last_field_id .. '"/>'
    .. '</hp:ctrl></hp:run>'
end

-- forward declarations
local process_blocks

local function create_footnote(blocks)
  local body_parts = process_blocks(blocks, 0)
  local body_xml = table.concat(body_parts, '\n')
  local inst_id = unique_id()
  return '<hp:run charPrIDRef="0"><hp:ctrl>'
    .. '<hp:footNote number="0" instId="' .. inst_id .. '">'
    .. '<hp:autoNum num="0" numType="FOOTNOTE"/>'
    .. '<hp:subList id="' .. inst_id .. '" textDirection="HORIZONTAL"'
    .. ' lineWrap="BREAK" vertAlign="TOP" linkListIDRef="0"'
    .. ' linkListNextIDRef="0" textWidth="0" textHeight="0"'
    .. ' hasTextRef="0" hasNumRef="0">'
    .. body_xml
    .. '</hp:subList>'
    .. '</hp:footNote>'
    .. '</hp:ctrl></hp:run>'
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 11: Image Handling
-- ══════════════════════════════════════════════════════════════════════

local input_dir = './'

local function parse_dimension(val_str)
  if not val_str or val_str == '' then return nil end
  local s = val_str:lower():match('^%s*(.-)%s*$')
  local val, unit = s:match('^([0-9%.]+)([a-z%%]*)$')
  if not val then return nil end
  val = tonumber(val)
  if not val then return nil end
  local mm_val
  if unit == '' or unit == 'px' then mm_val = val * (25.4/96.0)
  elseif unit == 'in' then mm_val = val * 25.4
  elseif unit == 'cm' then mm_val = val * 10.0
  elseif unit == 'mm' then mm_val = val
  elseif unit == 'pt' then mm_val = val * (25.4/72.0)
  elseif unit == '%' then mm_val = val * 1.5
  else mm_val = val * (25.4/96.0)
  end
  return math.floor(mm_val * LUNIT_PER_MM)
end

local function resolve_image_path(target_url)
  if target_url:match('^/') and file_exists(target_url) then
    return target_url
  end
  local candidate = input_dir .. target_url
  if file_exists(candidate) then return candidate end
  if file_exists(target_url) then return target_url end
  return nil
end

local function handle_image(img_inline, char_pr_id)
  char_pr_id = char_pr_id or '0'
  local target_url = img_inline.src
  local attrs_map = {}
  if img_inline.attr and img_inline.attr.attributes then
    for k, v in pairs(img_inline.attr.attributes) do
      attrs_map[k] = v
    end
  end

  local width_hwp, height_hwp = 8504, 8504
  local w_parsed = parse_dimension(attrs_map.width)
  local h_parsed = parse_dimension(attrs_map.height)

  local image_path = resolve_image_path(target_url)
  local px_w, px_h = get_image_dimensions(image_path)

  if px_w and px_h then
    local LUNIT_PER_PX = (25.4 * LUNIT_PER_MM) / 96.0
    if w_parsed and h_parsed then
      width_hwp, height_hwp = w_parsed, h_parsed
    elseif w_parsed then
      width_hwp = w_parsed
      height_hwp = math.floor(w_parsed * px_h / math.max(px_w, 1))
    elseif h_parsed then
      height_hwp = h_parsed
      width_hwp = math.floor(h_parsed * px_w / math.max(px_h, 1))
    else
      width_hwp = math.floor(px_w * LUNIT_PER_PX)
      height_hwp = math.floor(px_h * LUNIT_PER_PX)
    end
  else
    if w_parsed then width_hwp = w_parsed end
    if h_parsed then height_hwp = h_parsed end
  end

  if width_hwp > PAGE_TEXT_WIDTH then
    local ratio = PAGE_TEXT_WIDTH / width_hwp
    width_hwp = PAGE_TEXT_WIDTH
    height_hwp = math.floor(height_hwp * ratio)
  end

  local binary_item_id = 'img_' .. tostring(math.floor(os.clock()*1000000)) .. '_' .. tostring(math.random(0, 1000000))
  local ext = 'png'
  local lower = target_url:lower()
  if lower:match('%.jpe?g$') then ext = 'jpg'
  elseif lower:match('%.gif$') then ext = 'gif'
  elseif lower:match('%.bmp$') then ext = 'bmp'
  end

  images[#images+1] = {
    id = binary_item_id,
    path = target_url,
    resolved_path = image_path,
    ext = ext,
  }

  local pic_id = unique_id()
  local inst_id = tostring(math.random(10000000, 99999999))
  local w, h = width_hwp, height_hwp

  return '<hp:run charPrIDRef="' .. char_pr_id .. '">'
    .. '<hp:pic id="' .. pic_id .. '" zOrder="0" numberingType="NONE"'
    .. ' textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0"'
    .. ' dropcapstyle="None" href="" groupLevel="0"'
    .. ' instid="' .. inst_id .. '" reverse="0">'
    .. '<hp:offset x="0" y="0"/>'
    .. '<hp:orgSz width="' .. w .. '" height="' .. h .. '"/>'
    .. '<hp:curSz width="' .. w .. '" height="' .. h .. '"/>'
    .. '<hp:flip horizontal="0" vertical="0"/>'
    .. '<hp:rotationInfo angle="0" centerX="0" centerY="0" rotateimage="1"/>'
    .. '<hp:renderingInfo>'
    .. '<hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
    .. '<hc:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
    .. '<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
    .. '</hp:renderingInfo>'
    .. '<hc:img binaryItemIDRef="' .. binary_item_id .. '" bright="0"'
    .. ' contrast="0" effect="REAL_PIC" alpha="0"/>'
    .. '<hp:imgRect>'
    .. '<hc:pt0 x="0" y="0"/><hc:pt1 x="' .. w .. '" y="0"/>'
    .. '<hc:pt2 x="' .. w .. '" y="' .. h .. '"/><hc:pt3 x="0" y="' .. h .. '"/>'
    .. '</hp:imgRect>'
    .. '<hp:imgClip left="0" right="0" top="0" bottom="0"/>'
    .. '<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
    .. '<hp:imgDim dimwidth="0" dimheight="0"/>'
    .. '<hp:effects/>'
    .. '<hp:sz width="' .. w .. '" widthRelTo="ABSOLUTE"'
    .. ' height="' .. h .. '" heightRelTo="ABSOLUTE" protect="0"/>'
    .. '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1"'
    .. ' allowOverlap="1" holdAnchorAndSO="0" vertRelTo="PARA"'
    .. ' horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT"'
    .. ' vertOffset="0" horzOffset="0"/>'
    .. '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
    .. '<hp:shapeComment/>'
    .. '</hp:pic>'
    .. '</hp:run>'
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 12: Inline Processing
-- ══════════════════════════════════════════════════════════════════════

local function process_inlines(inlines, base_char_pr_id, active_formats)
  base_char_pr_id = base_char_pr_id or '0'
  active_formats = active_formats or {}
  local xml_parts = {}
  local text_parts = {}

  local function get_current_id()
    return get_builtin_char_pr_id(base_char_pr_id, active_formats)
  end

  for _, item in ipairs(inlines) do
    local t = item.t

    if t == 'Str' then
      local cid = get_current_id()
      xml_parts[#xml_parts+1] = '<hp:run charPrIDRef="' .. cid .. '"><hp:t>' .. xml_escape(item.text) .. '</hp:t></hp:run>'
      text_parts[#text_parts+1] = item.text

    elseif t == 'Space' then
      local cid = get_current_id()
      xml_parts[#xml_parts+1] = '<hp:run charPrIDRef="' .. cid .. '"><hp:t> </hp:t></hp:run>'
      text_parts[#text_parts+1] = ' '

    elseif t == 'SoftBreak' then
      local cid = get_current_id()
      xml_parts[#xml_parts+1] = '<hp:run charPrIDRef="' .. cid .. '"><hp:t> </hp:t></hp:run>'
      text_parts[#text_parts+1] = ' '

    elseif t == 'LineBreak' then
      local cid = get_current_id()
      xml_parts[#xml_parts+1] = '<hp:run charPrIDRef="' .. cid .. '"><hp:t><hp:lineBreak/></hp:t></hp:run>'
      text_parts[#text_parts+1] = '\n'

    elseif t == 'Strong' then
      local new_fmts = {}; for k,v in pairs(active_formats) do new_fmts[k]=v end; new_fmts['BOLD']=true
      local runs, txt = process_inlines(item.content, base_char_pr_id, new_fmts)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt

    elseif t == 'Emph' then
      local new_fmts = {}; for k,v in pairs(active_formats) do new_fmts[k]=v end; new_fmts['ITALIC']=true
      local runs, txt = process_inlines(item.content, base_char_pr_id, new_fmts)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt

    elseif t == 'Underline' then
      local new_fmts = {}; for k,v in pairs(active_formats) do new_fmts[k]=v end; new_fmts['UNDERLINE']=true
      local runs, txt = process_inlines(item.content, base_char_pr_id, new_fmts)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt

    elseif t == 'Strikeout' then
      local new_fmts = {}; for k,v in pairs(active_formats) do new_fmts[k]=v end; new_fmts['STRIKEOUT']=true
      local runs, txt = process_inlines(item.content, base_char_pr_id, new_fmts)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt

    elseif t == 'Superscript' then
      local new_fmts = {}; for k,v in pairs(active_formats) do new_fmts[k]=v end; new_fmts['SUPERSCRIPT']=true
      local runs, txt = process_inlines(item.content, base_char_pr_id, new_fmts)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt

    elseif t == 'Subscript' then
      local new_fmts = {}; for k,v in pairs(active_formats) do new_fmts[k]=v end; new_fmts['SUBSCRIPT']=true
      local runs, txt = process_inlines(item.content, base_char_pr_id, new_fmts)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt

    elseif t == 'Code' then
      xml_parts[#xml_parts+1] = '<hp:run charPrIDRef="' .. CODE_CHAR_PR_ID .. '"><hp:t>' .. xml_escape(item.text) .. '</hp:t></hp:run>'
      text_parts[#text_parts+1] = item.text

    elseif t == 'Link' then
      xml_parts[#xml_parts+1] = create_field_begin(item.target)
      local new_fmts = {}; for k,v in pairs(active_formats) do new_fmts[k]=v end
      new_fmts['UNDERLINE']=true; new_fmts['COLOR_BLUE']=true
      local runs, txt = process_inlines(item.content, base_char_pr_id, new_fmts)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt
      xml_parts[#xml_parts+1] = create_field_end()

    elseif t == 'Image' then
      local img_xml = handle_image(item, get_current_id())
      xml_parts[#xml_parts+1] = img_xml
      text_parts[#text_parts+1] = '[image]'

    elseif t == 'Note' then
      xml_parts[#xml_parts+1] = create_footnote(item.content)

    elseif t == 'Math' then
      local eq_xml = make_equation_xml(item.text)
      local cid = get_current_id()
      xml_parts[#xml_parts+1] = '<hp:run charPrIDRef="' .. cid .. '">' .. eq_xml .. '</hp:run>'
      text_parts[#text_parts+1] = item.text

    elseif t == 'Quoted' then
      local qt = item.quotetype
      local q1 = qt == 'DoubleQuote' and '\u{201c}' or '\u{2018}'
      local q2 = qt == 'DoubleQuote' and '\u{201d}' or '\u{2019}'
      local cid = get_current_id()
      xml_parts[#xml_parts+1] = '<hp:run charPrIDRef="' .. cid .. '"><hp:t>' .. q1 .. '</hp:t></hp:run>'
      local runs, txt = process_inlines(item.content, base_char_pr_id, active_formats)
      xml_parts[#xml_parts+1] = runs
      xml_parts[#xml_parts+1] = '<hp:run charPrIDRef="' .. cid .. '"><hp:t>' .. q2 .. '</hp:t></hp:run>'
      text_parts[#text_parts+1] = q1 .. txt .. q2

    elseif t == 'Cite' then
      local runs, txt = process_inlines(item.content, base_char_pr_id, active_formats)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt

    elseif t == 'Span' then
      local runs, txt = process_inlines(item.content, base_char_pr_id, active_formats)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt

    elseif t == 'SmallCaps' then
      local runs, txt = process_inlines(item.content, base_char_pr_id, active_formats)
      xml_parts[#xml_parts+1] = runs; text_parts[#text_parts+1] = txt

    -- RawInline: skip
    end
  end

  return table.concat(xml_parts), table.concat(text_parts)
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 13: Block Processing
-- ══════════════════════════════════════════════════════════════════════

local function handle_para_or_plain(inlines, indent_prefix)
  indent_prefix = indent_prefix or ''
  local parts = {}

  -- Standalone DisplayMath
  if #inlines == 1 and inlines[1].t == 'Math' then
    local mtype = inlines[1].mathtype
    if mtype == 'DisplayMath' then
      local pid = next_para_id()
      local eq_xml = make_equation_xml(inlines[1].text)
      parts[#parts+1] = '<hp:p id="' .. pid .. '" paraPrIDRef="0" styleIDRef="0"'
        .. ' pageBreak="0" columnBreak="0" merged="0">'
        .. '<hp:run charPrIDRef="0">' .. eq_xml .. '</hp:run>'
        .. '<hp:linesegarray>'
        .. '<hp:lineseg textpos="0" vertpos="0" vertsize="1600"'
        .. ' textheight="1600" baseline="1360" spacing="400"'
        .. ' horzpos="0" horzsize="42520" flags="393216"/>'
        .. '</hp:linesegarray></hp:p>'
      return parts
    end
  end

  -- Standalone Image
  if #inlines == 1 and inlines[1].t == 'Image' then
    local img_xml = handle_image(inlines[1])
    parts[#parts+1] = make_rich_paragraph_xml(img_xml, nil)
    return parts
  end

  -- Normal paragraph with inline formatting
  local runs_xml, plain_text = process_inlines(inlines, '0')
  if indent_prefix ~= '' then
    plain_text = indent_prefix .. plain_text
    runs_xml = '<hp:run charPrIDRef="0"><hp:t>' .. indent_prefix .. '</hp:t></hp:run>' .. runs_xml
  end

  local lineseg = compute_lineseg_xml(plain_text)
  local pid = next_para_id()
  parts[#parts+1] = '<hp:p id="' .. pid .. '" paraPrIDRef="0" styleIDRef="0"'
    .. ' pageBreak="0" columnBreak="0" merged="0">'
    .. runs_xml .. lineseg .. '</hp:p>'
  return parts
end

local function handle_header(block)
  local level = block.level
  local hs = HEADING_STYLE[level] or {style=0, para=0, char=0}
  local sid = tostring(hs.style)
  local pid_ref = tostring(hs.para)
  local base_cid = tostring(hs.char)

  local runs_xml, plain_text = process_inlines(block.content, base_cid)
  local ch = CHAR_HEIGHT_MAP[tonumber(base_cid) or 0] or CHAR_HEIGHT_NORMAL
  local lineseg = compute_lineseg_xml(plain_text, ch)

  local pid = next_para_id()
  return '<hp:p id="' .. pid .. '" paraPrIDRef="' .. pid_ref .. '"'
    .. ' styleIDRef="' .. sid .. '"'
    .. ' pageBreak="0" columnBreak="0" merged="0">'
    .. runs_xml .. lineseg .. '</hp:p>'
end

local function handle_code_block(block, indent_prefix)
  indent_prefix = indent_prefix or ''
  local parts = {}
  for line in (block.text .. '\n'):gmatch('([^\n]*)\n') do
    parts[#parts+1] = make_paragraph_xml(indent_prefix .. line, tostring(CODE_CHAR_PR_ID))
  end
  return parts
end

-- ── Table handling ──────────────────────────────────────────────────

local function render_cell_content(cell_blocks, cell_width)
  if not cell_blocks or #cell_blocks == 0 then
    return make_paragraph_xml('')
  end
  local cell_parts = {}
  for _, block in ipairs(cell_blocks) do
    if block.t == 'Para' or block.t == 'Plain' then
      local runs_xml, plain_text = process_inlines(block.content, '0')
      local lineseg = compute_lineseg_xml(plain_text, CHAR_HEIGHT_NORMAL, cell_width)
      local pid = next_para_id()
      cell_parts[#cell_parts+1] = '<hp:p id="' .. pid .. '" paraPrIDRef="0" styleIDRef="0"'
        .. ' pageBreak="0" columnBreak="0" merged="0">'
        .. runs_xml .. lineseg .. '</hp:p>'
    else
      local sub = process_blocks({block}, 0)
      for _, s in ipairs(sub) do cell_parts[#cell_parts+1] = s end
    end
  end
  if #cell_parts == 0 then return make_paragraph_xml('') end
  return table.concat(cell_parts, '\n')
end

local function handle_table(block)
  local caption = block.caption
  local colspecs = block.colspecs
  local head = block.head
  local bodies = block.bodies
  local foot = block.foot

  local all_rows = {}
  local head_row_count = 0
  if head and head.rows then
    for _, row in ipairs(head.rows) do
      all_rows[#all_rows+1] = row
      head_row_count = head_row_count + 1
    end
  end
  if bodies then
    for _, body in ipairs(bodies) do
      if body.head then
        for _, row in ipairs(body.head) do all_rows[#all_rows+1] = row end
      end
      if body.body then
        for _, row in ipairs(body.body) do all_rows[#all_rows+1] = row end
      end
    end
  end
  if foot and foot.rows then
    for _, row in ipairs(foot.rows) do all_rows[#all_rows+1] = row end
  end

  if #all_rows == 0 then return '' end

  local row_cnt = #all_rows
  local col_cnt = colspecs and #colspecs or 0
  if col_cnt == 0 and all_rows[1] and all_rows[1].cells then
    col_cnt = #all_rows[1].cells
  end
  if col_cnt == 0 then return '' end

  local col_widths = {}
  local base_w = math.floor(PAGE_TEXT_WIDTH / col_cnt)
  for i = 1, col_cnt do col_widths[i] = base_w end
  local remainder = PAGE_TEXT_WIDTH - base_w * col_cnt
  for i = 1, remainder do col_widths[((i-1) % col_cnt) + 1] = col_widths[((i-1) % col_cnt) + 1] + 1 end

  local row_height = 1800
  local total_height = row_height * row_cnt
  local bfid = tostring(TABLE_BORDER_FILL_ID)

  local parts = {}

  -- Caption
  if caption and caption.long and #caption.long > 0 then
    local cap_text = pandoc.utils.stringify(caption.long)
    if cap_text ~= '' then parts[#parts+1] = make_paragraph_xml(cap_text) end
  end

  -- Table wrapper
  local pid = next_para_id()
  local tbl_id = unique_id()

  parts[#parts+1] = '<hp:p id="' .. pid .. '" paraPrIDRef="0" styleIDRef="0"'
    .. ' pageBreak="0" columnBreak="0" merged="0">'
    .. '<hp:run charPrIDRef="0">'
    .. '<hp:tbl id="' .. tbl_id .. '" zOrder="0" numberingType="TABLE"'
    .. ' textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0"'
    .. ' dropcapstyle="None" pageBreak="CELL" repeatHeader="1"'
    .. ' rowCnt="' .. row_cnt .. '" colCnt="' .. col_cnt .. '"'
    .. ' cellSpacing="0" borderFillIDRef="' .. bfid .. '" noAdjust="0">'
    .. '<hp:sz width="' .. PAGE_TEXT_WIDTH .. '" widthRelTo="ABSOLUTE"'
    .. ' height="' .. total_height .. '" heightRelTo="ABSOLUTE" protect="0"/>'
    .. '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1"'
    .. ' allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA"'
    .. ' horzRelTo="COLUMN" vertAlign="TOP" horzAlign="CENTER"'
    .. ' vertOffset="0" horzOffset="0"/>'
    .. '<hp:outMargin left="0" right="0" top="141" bottom="141"/>'
    .. '<hp:inMargin left="0" right="0" top="0" bottom="0"/>'

  local occupied = {}
  local function is_occupied(r, c) return occupied[r .. ',' .. c] end
  local function mark_occupied(r, c) occupied[r .. ',' .. c] = true end

  for row_idx, row in ipairs(all_rows) do
    local curr_row = row_idx - 1
    parts[#parts+1] = '<hp:tr>'
    local curr_col = 0
    local cells = row.cells or {}
    for _, cell in ipairs(cells) do
      while is_occupied(curr_row, curr_col) do curr_col = curr_col + 1 end
      local actual_col = curr_col
      local rowspan = cell.row_span or 1
      local colspan = cell.col_span or 1
      local cell_blocks = cell.contents or {}

      for r = 0, rowspan-1 do
        for c = 0, colspan-1 do
          mark_occupied(curr_row + r, actual_col + c)
        end
      end

      local cell_width = 0
      for i = 0, colspan-1 do
        local idx = actual_col + i + 1
        cell_width = cell_width + (col_widths[idx] or base_w)
      end

      local header_flag = curr_row < head_row_count and '1' or '0'
      local cell_content = render_cell_content(cell_blocks, cell_width)
      local sublist_id = unique_id()

      parts[#parts+1] = '<hp:tc name="" header="' .. header_flag .. '" hasMargin="0"'
        .. ' protect="0" editable="0" dirty="0" borderFillIDRef="' .. bfid .. '">'
        .. '<hp:subList id="' .. sublist_id .. '"'
        .. ' textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER"'
        .. ' linkListIDRef="0" linkListNextIDRef="0" textWidth="0"'
        .. ' textHeight="0" hasTextRef="0" hasNumRef="0">'
        .. cell_content
        .. '</hp:subList>'
        .. '<hp:cellAddr colAddr="' .. actual_col .. '" rowAddr="' .. curr_row .. '"/>'
        .. '<hp:cellSpan colSpan="' .. colspan .. '" rowSpan="' .. rowspan .. '"/>'
        .. '<hp:cellSz width="' .. cell_width .. '" height="' .. row_height .. '"/>'
        .. '<hp:cellMargin left="141" right="141" top="141" bottom="141"/>'
        .. '</hp:tc>'

      curr_col = curr_col + colspan
    end
    parts[#parts+1] = '</hp:tr>'
  end

  parts[#parts+1] = '</hp:tbl>'
  parts[#parts+1] = '<hp:t></hp:t></hp:run></hp:p>'
  return table.concat(parts, '\n')
end

-- ── Lists ────────────────────────────────────────────────────────────

local function handle_bullet_list(items, indent_level)
  local results = {}
  for _, item_blocks in ipairs(items) do
    local item_parts = process_blocks(item_blocks, indent_level)
    if #item_parts > 0 then
      item_parts[1] = item_parts[1]:gsub('<hp:t>', '<hp:t>\u{2022} ', 1)
    end
    for _, p in ipairs(item_parts) do results[#results+1] = p end
  end
  return results
end

local function handle_ordered_list(block, indent_level)
  local start_num = block.listAttributes and block.listAttributes.start or 1
  local results = {}
  for idx, item_blocks in ipairs(block.content) do
    local item_parts = process_blocks(item_blocks, indent_level)
    if #item_parts > 0 then
      local num = start_num + idx - 1
      item_parts[1] = item_parts[1]:gsub('<hp:t>', '<hp:t>' .. num .. '. ', 1)
    end
    for _, p in ipairs(item_parts) do results[#results+1] = p end
  end
  return results
end

-- ── Main block processor ─────────────────────────────────────────────

process_blocks = function(blocks, indent_level)
  indent_level = indent_level or 0
  local indent_prefix = ('\u{3000}'):rep(indent_level)
  local xml_parts = {}

  for _, block in ipairs(blocks) do
    local t = block.t

    if t == 'Para' or t == 'Plain' then
      local pp = handle_para_or_plain(block.content, indent_prefix)
      for _, p in ipairs(pp) do xml_parts[#xml_parts+1] = p end

    elseif t == 'Header' then
      xml_parts[#xml_parts+1] = handle_header(block)

    elseif t == 'CodeBlock' then
      local pp = handle_code_block(block, indent_prefix)
      for _, p in ipairs(pp) do xml_parts[#xml_parts+1] = p end

    elseif t == 'BulletList' then
      local pp = handle_bullet_list(block.content, indent_level)
      for _, p in ipairs(pp) do xml_parts[#xml_parts+1] = p end

    elseif t == 'OrderedList' then
      local pp = handle_ordered_list(block, indent_level)
      for _, p in ipairs(pp) do xml_parts[#xml_parts+1] = p end

    elseif t == 'BlockQuote' then
      local pp = process_blocks(block.content, indent_level + 1)
      for _, p in ipairs(pp) do xml_parts[#xml_parts+1] = p end

    elseif t == 'Table' then
      xml_parts[#xml_parts+1] = handle_table(block)

    elseif t == 'HorizontalRule' then
      xml_parts[#xml_parts+1] = make_paragraph_xml(('\u{2501}'):rep(30))

    elseif t == 'Div' then
      -- All Divs are pass-through (including Quarto cell wrappers)
      local pp = process_blocks(block.content, indent_level)
      for _, p in ipairs(pp) do xml_parts[#xml_parts+1] = p end

    elseif t == 'DefinitionList' then
      for _, item in ipairs(block.content) do
        local term_text = get_plain_text(item[1])
        xml_parts[#xml_parts+1] = make_paragraph_xml(indent_prefix .. term_text)
        for _, def_blocks in ipairs(item[2]) do
          local pp = process_blocks(def_blocks, indent_level + 1)
          for _, p in ipairs(pp) do xml_parts[#xml_parts+1] = p end
        end
      end

    elseif t == 'LineBlock' then
      for _, line_inlines in ipairs(block.content) do
        local line_text = get_plain_text(line_inlines)
        xml_parts[#xml_parts+1] = make_paragraph_xml(indent_prefix .. line_text)
      end

    -- RawBlock: skip
    end
  end

  return xml_parts
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 14: Title Block and TOC
-- ══════════════════════════════════════════════════════════════════════

local function extract_metadata(doc)
  local meta = doc.meta or {}
  local title = meta.title and pandoc.utils.stringify(meta.title) or ''
  local subtitle = meta.subtitle and pandoc.utils.stringify(meta.subtitle) or ''
  local author = meta.author and pandoc.utils.stringify(meta.author) or ''
  local date_str = meta.date and pandoc.utils.stringify(meta.date) or ''
  return title, subtitle, author, date_str
end

local function build_title_block(title, subtitle, author, date_str)
  local parts = {}
  if title ~= '' then
    parts[#parts+1] = make_paragraph_xml(title, '7')
  end
  if subtitle ~= '' then
    parts[#parts+1] = make_paragraph_xml(subtitle, '8')
  end
  if author ~= '' or date_str ~= '' then
    local meta_parts = {}
    if author ~= '' then meta_parts[#meta_parts+1] = author end
    if date_str ~= '' then meta_parts[#meta_parts+1] = date_str end
    parts[#parts+1] = make_paragraph_xml(table.concat(meta_parts, ' | '))
  end
  if #parts > 0 then
    parts[#parts+1] = make_paragraph_xml('')
  end
  return parts
end

local function collect_headings(blocks)
  local headings = {}
  for _, block in ipairs(blocks) do
    if block.t == 'Header' then
      headings[#headings+1] = {
        level = block.level,
        text = get_plain_text(block.content),
      }
    elseif block.t == 'Div' then
      local sub = collect_headings(block.content)
      for _, h in ipairs(sub) do headings[#headings+1] = h end
    end
  end
  return headings
end

local function build_toc_block(blocks)
  local headings = collect_headings(blocks)
  if #headings == 0 then return {} end

  local parts = {}
  parts[#parts+1] = make_paragraph_xml('\u{BAA9}  \u{CC28}', '8')
  parts[#parts+1] = make_paragraph_xml('')

  local min_level = 999
  for _, h in ipairs(headings) do
    if h.level < min_level then min_level = h.level end
  end

  for _, h in ipairs(headings) do
    local relative = h.level - min_level
    local indent = ('\u{3000}'):rep(relative)
    if relative == 0 then
      local bold_id = get_builtin_char_pr_id('0', {BOLD=true})
      parts[#parts+1] = make_paragraph_xml(indent .. h.text, bold_id)
    else
      parts[#parts+1] = make_paragraph_xml(indent .. h.text)
    end
  end

  parts[#parts+1] = make_paragraph_xml('')
  parts[#parts+1] = make_paragraph_xml(('\u{2501}'):rep(30))
  parts[#parts+1] = make_paragraph_xml('')
  return parts
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 15: XML Assembly
-- ══════════════════════════════════════════════════════════════════════

local function build_section_xml(original, body_xml)
  local sec_start = original:find('<hs:sec')
  local sec_end = original:find('>', sec_start) + 1
  local header_and_open = original:sub(1, sec_end)

  local p_start = original:find('<hp:p ')
  local p_end = original:find('</hp:p>') + #'</hp:p>'
  local first_paragraph = original:sub(p_start, p_end)

  return header_and_open .. first_paragraph .. '\n' .. body_xml .. '\n</hs:sec>'
end

local function replace_fontface_block(match_text)
  local lang = match_text:match('lang="(%w+)"')
  local primary_font = LANG_FONT_MAP[lang] or 'NimbusSanL'
  return '<hh:fontface lang="' .. lang .. '" fontCnt="3">'
    .. make_font_xml(0, primary_font)
    .. make_font_xml(1, primary_font)
    .. make_font_xml(2, 'D2Coding')
    .. '</hh:fontface>'
end

local function update_header_xml(header_xml)
  -- Replace fontface blocks
  header_xml = header_xml:gsub(
    '<hh:fontface lang="%w+"[^>]*>.-</hh:fontface>',
    replace_fontface_block)

  -- Add heading charPr entries
  local new_charpr = ''
  for _, cp in ipairs(HEADING_CHAR_PROPS) do
    new_charpr = new_charpr .. make_charpr_xml(cp.id, cp.height, {bold=cp.bold, font_ref=cp.font_ref})
  end

  -- Code charPr
  new_charpr = new_charpr .. make_charpr_xml(CODE_CHAR_PR_ID, 1000, {font_ref=CODE_FONT_REF})

  -- Dynamic format charPr entries
  for _, entry in pairs(char_pr_cache) do
    local base_id = tonumber(entry.base_id) or 0
    local base_height = CHAR_HEIGHT_MAP[base_id] or 1000
    local base_font_ref = (base_id == CODE_CHAR_PR_ID) and CODE_FONT_REF or 0
    local fmts = entry.formats
    new_charpr = new_charpr .. make_charpr_xml(tonumber(entry.id), base_height, {
      bold = fmts['BOLD'] or (base_id == 7) or (base_id == 8),
      italic = fmts['ITALIC'],
      underline = fmts['UNDERLINE'],
      strikeout = fmts['STRIKEOUT'],
      text_color = fmts['COLOR_BLUE'] and '#0000FF' or nil,
      font_ref = base_font_ref,
    })
  end

  header_xml = header_xml:gsub('</hh:charProperties>', new_charpr .. '</hh:charProperties>')

  -- Update itemCnt
  local cache_count = 0
  for _ in pairs(char_pr_cache) do cache_count = cache_count + 1 end
  local total = 7 + #HEADING_CHAR_PROPS + 1 + cache_count
  header_xml = header_xml:gsub(
    '(<hh:charProperties%s+itemCnt=")%d+(")', '%1' .. total .. '%2')

  -- Table borderFill
  header_xml = header_xml:gsub('</hh:borderFillList>',
    make_table_borderfill_xml() .. '</hh:borderFillList>')
  header_xml = header_xml:gsub(
    '(<hh:borderFillList%s+itemCnt=")%d+(")', '%13%2')

  -- Heading spacing
  for para_pr_id, prev_val in pairs(HEADING_SPACING) do
    header_xml = header_xml:gsub(
      '(<hh:paraPr%s+id="' .. para_pr_id .. '"[^>]*>.-)<hc:prev%s+value="0"',
      '%1<hc:prev value="' .. prev_val .. '"')
  end

  return header_xml
end

local function update_content_hpf(hpf_xml, title, author, date_str)
  local now = os.date('!%Y-%m-%dT%H:%M:%SZ')

  if title ~= '' then
    hpf_xml = hpf_xml:gsub(
      '(<opf:title)(/?>.-</opf:title>)',
      '%1>' .. xml_escape(title) .. '</opf:title>')
    hpf_xml = hpf_xml:gsub('<opf:title/>', '<opf:title>' .. xml_escape(title) .. '</opf:title>')
  end

  if author ~= '' then
    local safe = xml_escape(author)
    hpf_xml = hpf_xml:gsub(
      '(<opf:meta name="creator" content="text")>.-</opf:meta>',
      '%1>' .. safe .. '</opf:meta>')
    hpf_xml = hpf_xml:gsub(
      '(<opf:meta name="lastsaveby" content="text")>.-</opf:meta>',
      '%1>' .. safe .. '</opf:meta>')
  end

  hpf_xml = hpf_xml:gsub(
    '(<opf:meta name="ModifiedDate" content="text")>.-</opf:meta>',
    '%1>' .. now .. '</opf:meta>')

  if date_str ~= '' then
    hpf_xml = hpf_xml:gsub(
      '(<opf:meta name="date" content="text")>.-</opf:meta>',
      '%1>' .. xml_escape(date_str) .. '</opf:meta>')
  end

  -- Add image items to manifest
  if #images > 0 then
    local new_items = {}
    for _, img in ipairs(images) do
      local mime = 'image/png'
      if img.ext == 'jpg' then mime = 'image/jpeg'
      elseif img.ext == 'gif' then mime = 'image/gif' end
      new_items[#new_items+1] = '<opf:item id="' .. img.id .. '" href="BinData/' .. img.id .. '.' .. img.ext .. '"'
        .. ' media-type="' .. mime .. '" isEmbeded="1"/>'
    end
    local insert_str = table.concat(new_items, '\n') .. '\n'
    hpf_xml = hpf_xml:gsub('</opf:manifest>', insert_str .. '</opf:manifest>')
  end

  return hpf_xml
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 16: ZIP Assembly
-- ══════════════════════════════════════════════════════════════════════

local function write_hwpx(output_path, section_xml, header_xml, hpf_xml)
  local template_path = SCRIPT_DIR .. 'templates/blank.hwpx'
  if not file_exists(template_path) then
    io.stderr:write('[hwpx] ERROR: Template not found: ' .. template_path .. '\n')
    return false
  end

  local tmpdir = os.tmpname() .. '_hwpx'
  os.execute('mkdir -p ' .. shell_escape(tmpdir))

  -- Extract template
  local unzip_cmd = 'unzip -o -q ' .. shell_escape(template_path) .. ' -d ' .. shell_escape(tmpdir)
  local ok = os.execute(unzip_cmd)
  if not ok then
    io.stderr:write('[hwpx] ERROR: Failed to extract template (is unzip installed?)\n')
    os.execute('rm -rf ' .. shell_escape(tmpdir))
    return false
  end

  -- Write modified XML files
  write_file(tmpdir .. '/Contents/section0.xml', section_xml)
  write_file(tmpdir .. '/Contents/header.xml', header_xml)
  write_file(tmpdir .. '/Contents/content.hpf', hpf_xml)

  -- Copy images to BinData/
  if #images > 0 then
    os.execute('mkdir -p ' .. shell_escape(tmpdir .. '/BinData'))
    for _, img in ipairs(images) do
      local resolved = img.resolved_path
      if resolved and file_exists(resolved) then
        local dest = tmpdir .. '/BinData/' .. img.id .. '.' .. img.ext
        os.execute('cp ' .. shell_escape(resolved) .. ' ' .. shell_escape(dest))
      else
        io.stderr:write('[hwpx] WARNING: Image not found: ' .. (img.path or '?') .. '\n')
      end
    end
  end

  -- Create HWPX ZIP
  local zip_cmd = 'cd ' .. shell_escape(tmpdir) .. ' && zip -r -q '
    .. shell_escape(output_path) .. ' .'
  ok = os.execute(zip_cmd)

  -- Cleanup
  os.execute('rm -rf ' .. shell_escape(tmpdir))

  if ok then
    io.stderr:write('[hwpx] Successfully created ' .. output_path .. '\n')
    return true
  else
    io.stderr:write('[hwpx] ERROR: Failed to create ZIP (is zip installed?)\n')
    return false
  end
end

-- ══════════════════════════════════════════════════════════════════════
-- PART 17: Main Pandoc(doc) Entry Point
-- ══════════════════════════════════════════════════════════════════════

function Pandoc(doc)
  -- Run citeproc first
  if doc.meta and doc.meta.bibliography then
    io.stderr:write('[hwpx] Running citeproc for bibliography...\n')
    doc = pandoc.utils.citeproc(doc)
  end

  -- Determine output path
  local output_file = PANDOC_STATE.output_file
  if not output_file or output_file == '' then
    io.stderr:write('[hwpx] WARNING: no output_file detected, skipping HWPX generation\n')
    return doc
  end
  local hwpx_path = output_file:gsub('%.docx$', '.hwpx')

  -- Make output path absolute
  if not hwpx_path:match('^/') then
    local cwd = io.popen('pwd'):read('*l')
    hwpx_path = cwd .. '/' .. hwpx_path
  end

  -- Determine input directory
  input_dir = './'
  if PANDOC_STATE.input_files and #PANDOC_STATE.input_files > 0 then
    input_dir = PANDOC_STATE.input_files[1]:match('(.*[/\\])') or './'
  end

  -- Detect TOC
  local has_toc = false
  if PANDOC_WRITER_OPTIONS and PANDOC_WRITER_OPTIONS.table_of_contents then
    has_toc = true
  elseif doc.meta and doc.meta.toc then
    has_toc = pandoc.utils.stringify(doc.meta.toc) == 'true'
  end

  io.stderr:write('[hwpx] Generating ' .. hwpx_path .. ' (pure Lua engine)...\n')
  if has_toc then io.stderr:write('[hwpx] TOC enabled\n') end

  -- Reset state for this conversion
  para_id_counter = 3121190098
  max_char_pr_id = CODE_CHAR_PR_ID
  char_pr_cache = {}
  images = {}
  math.randomseed(os.time())

  -- Extract metadata
  local title, subtitle, author, date_str = extract_metadata(doc)

  -- Load template XML
  local template_path = SCRIPT_DIR .. 'templates/blank.hwpx'
  local tmpdir_tpl = os.tmpname() .. '_tpl'
  os.execute('mkdir -p ' .. shell_escape(tmpdir_tpl))
  os.execute('unzip -o -q ' .. shell_escape(template_path) .. ' -d ' .. shell_escape(tmpdir_tpl))
  local section0_raw = read_file(tmpdir_tpl .. '/Contents/section0.xml') or ''
  local header_xml_raw = read_file(tmpdir_tpl .. '/Contents/header.xml') or ''
  local hpf_xml_raw = read_file(tmpdir_tpl .. '/Contents/content.hpf') or ''
  os.execute('rm -rf ' .. shell_escape(tmpdir_tpl))

  -- Build body
  local body_parts = {}

  -- Title block
  local title_parts = build_title_block(title, subtitle, author, date_str)
  for _, p in ipairs(title_parts) do body_parts[#body_parts+1] = p end

  -- TOC
  if has_toc then
    local toc_parts = build_toc_block(doc.blocks)
    for _, p in ipairs(toc_parts) do body_parts[#body_parts+1] = p end
  end

  -- Content blocks
  local content_parts = process_blocks(doc.blocks, 0)
  for _, p in ipairs(content_parts) do body_parts[#body_parts+1] = p end

  if #body_parts == 0 then
    body_parts[#body_parts+1] = make_paragraph_xml('')
  end

  local body_xml = table.concat(body_parts, '\n')

  -- Assemble XML files
  local section_xml = build_section_xml(section0_raw, body_xml)
  local header_xml = update_header_xml(header_xml_raw)
  local hpf_xml = update_content_hpf(hpf_xml_raw, title, author, date_str)

  -- Write HWPX
  local success = write_hwpx(hwpx_path, section_xml, header_xml, hpf_xml)

  if success then
    -- Schedule .docx cleanup
    local marker_path = output_file .. '.hwpx-cleanup'
    local marker = io.open(marker_path, 'w')
    if marker then
      marker:write(output_file)
      marker:close()
    end
  end

  return doc
end

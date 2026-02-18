-- hwpx-filter.lua
-- Pandoc Lua filter: serialize AST to JSON, invoke pandoc_hwpx to produce .hwpx

function Pandoc(doc)
  -- Run citeproc first to resolve citations and generate bibliography
  -- (Our filter runs before Pandoc's built-in citeproc, so we must do it here)
  if doc.meta and doc.meta.bibliography then
    io.stderr:write("[hwpx] Running citeproc for bibliography...\n")
    doc = pandoc.utils.citeproc(doc)
  end

  -- Serialize entire AST to JSON
  local json_ast = pandoc.write(doc, 'json')

  -- Determine output path: replace .docx with .hwpx
  local output_file = PANDOC_STATE.output_file
  if not output_file or output_file == "" then
    io.stderr:write("[hwpx] WARNING: no output_file detected, skipping HWPX generation\n")
    return doc
  end

  local hwpx_path = output_file:gsub("%.docx$", ".hwpx")

  -- Determine input directory for image path resolution
  local input_dir = "./"
  if PANDOC_STATE.input_files and #PANDOC_STATE.input_files > 0 then
    input_dir = PANDOC_STATE.input_files[1]:match("(.*[/\\])") or "./"
  end

  -- Detect TOC option
  local has_toc = false
  if PANDOC_WRITER_OPTIONS and PANDOC_WRITER_OPTIONS.table_of_contents then
    has_toc = true
  elseif doc.meta and doc.meta.toc then
    has_toc = pandoc.utils.stringify(doc.meta.toc) == "true"
  end

  io.stderr:write("[hwpx] Generating " .. hwpx_path .. " via pandoc_hwpx ...\n")

  -- Build arguments
  local args = {'-m', 'pandoc_hwpx', '-o', hwpx_path, '--input-dir', input_dir}
  if has_toc then
    table.insert(args, '--toc')
    io.stderr:write("[hwpx] TOC enabled\n")
  end

  -- Call python -m pandoc_hwpx with JSON AST on stdin
  local ok, result_or_err = pcall(function()
    return pandoc.pipe('python3', args, json_ast)
  end)

  if ok then
    io.stderr:write("[hwpx] Successfully created " .. hwpx_path .. "\n")
    -- Schedule .docx cleanup via marker file
    local marker_path = output_file .. ".hwpx-cleanup"
    local marker = io.open(marker_path, "w")
    if marker then
      marker:write(output_file)
      marker:close()
    end
  else
    io.stderr:write("[hwpx] ERROR: pandoc_hwpx failed: " .. tostring(result_or_err) .. "\n")
    io.stderr:write("[hwpx] The .docx file is preserved at " .. output_file .. "\n")
  end

  return doc
end

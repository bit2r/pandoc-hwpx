"""Main HWPX conversion engine.

Combines pypandoc-hwpx architecture (dynamic charPr, inline formatting,
images, tables with rowspan/colspan, hyperlinks, footnotes, native lists,
reference document support) with quarto-hwpx features (math equations,
D2Coding code blocks, linesegarray, Korean typography, BlockQuote,
HorizontalRule, DefinitionList, Div, LineBlock, title block rendering).

Reads Pandoc JSON AST from stdin, generates HWPX output.
Uses raw XML strings to preserve namespace prefixes (hp:, hs:, hc:, hh:)
required by HWP Mac compatibility.
"""

import copy
import io
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape
import xml.etree.ElementTree as ET

try:
    from PIL import Image
except ImportError:
    Image = None

from .math_converter import latex_to_hwp_script, make_equation_xml
from .lineseg import compute_lineseg_xml, PAGE_TEXT_WIDTH, CHAR_HEIGHT_NORMAL

# ── Per-language font face mapping ────────────────────────────────────────
LANG_FONT_MAP = {
    'HANGUL':   'NanumSquareOTF',
    'LATIN':    'NimbusSanL',
    'HANJA':    'Noto Sans CJK KR',
    'JAPANESE': 'Noto Sans CJK KR',
    'OTHER':    'NimbusSanL',
    'SYMBOL':   'STIX Two Text',
    'USER':     'NimbusSanL',
}

# ── Style IDs for headings in Skeleton.hwpx ──────────────────────────────
HEADING_STYLE = {
    1: (2, 2, 7),    # styleIDRef, paraPrIDRef, charPrIDRef
    2: (3, 3, 8),
    3: (4, 4, 9),
    4: (5, 5, 0),
    5: (6, 6, 0),
    6: (7, 7, 0),
}

HEADING_CHAR_PROPS = [
    (7, 2200, True, 0),   # H1: 22pt, bold
    (8, 1600, True, 0),   # H2: 16pt, bold
    (9, 1300, False, 0),  # H3: 13pt
]

HEADING_SPACING = {
    2: 800,   # H1: 8pt space before
    3: 600,   # H2: 6pt space before
    4: 400,   # H3: 4pt space before
}

CODE_CHAR_PR_ID = 10
CODE_FONT_REF = 2

# charPr id -> height for lineseg
CHAR_HEIGHT_MAP = {
    0: 1000,
    7: 2200,
    8: 1600,
    9: 1300,
    10: 1000,
}

TABLE_BORDER_FILL_ID = 3

# ── Paragraph ID generator ───────────────────────────────────────────────
_para_id_counter = 3121190098

def _next_para_id():
    global _para_id_counter
    _para_id_counter += 1
    return str(_para_id_counter)

def _unique_id():
    return str(int(time.time() * 1000) % 100000000 + random.randint(0, 10000))


# ── XML Namespaces ────────────────────────────────────────────────────────
NS = {
    'hh': 'http://www.hancom.co.kr/hwpml/2011/head',
    'hp': 'http://www.hancom.co.kr/hwpml/2011/paragraph',
    'hc': 'http://www.hancom.co.kr/hwpml/2011/core',
    'hs': 'http://www.hancom.co.kr/hwpml/2011/section',
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


class PandocHwpxConverter:
    """Converts Pandoc JSON AST to HWPX document format."""

    def __init__(self, json_ast, reference_path=None, input_dir=None, toc=False):
        """Initialize converter.

        Args:
            json_ast: Parsed Pandoc JSON AST dictionary.
            reference_path: Path to reference .hwpx template. If None, uses
                built-in blank.hwpx.
            input_dir: Base directory for resolving relative image paths.
            toc: Whether to generate a table of contents.
        """
        self.ast = json_ast
        self.input_dir = input_dir or os.getcwd()
        self.toc = toc
        self.images = []  # collected image metadata for embedding

        # Dynamic style system (from pypandoc-hwpx)
        self.header_tree = None
        self.header_root = None
        self.char_pr_cache = {}
        self.max_char_pr_id = 0
        self.max_para_pr_id = 0

        # Style mappings
        self.dynamic_style_map = {}
        self.outline_style_ids = {}
        self.normal_style_id = '0'
        self.normal_para_pr_id = '0'
        self.normal_char_pr_id = '0'
        self.table_border_fill_id = str(TABLE_BORDER_FILL_ID)

        # Use-reference-doc vs built-in
        self.use_reference = reference_path is not None
        self.reference_path = reference_path

        # Determine template path
        if reference_path and os.path.exists(reference_path):
            self.template_path = reference_path
        else:
            self.template_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'templates', 'blank.hwpx'
            )

        # Read template contents
        self._load_template()

        # Extract metadata
        self.title = ''
        self.subtitle = ''
        self.author = ''
        self.date_str = ''
        self._extract_metadata()

    def _load_template(self):
        """Load template HWPX and read header.xml, section0.xml."""
        with zipfile.ZipFile(self.template_path, 'r') as z:
            self.template_names = z.namelist()
            self.header_xml_raw = z.read('Contents/header.xml').decode('utf-8')
            self.section0_raw = z.read('Contents/section0.xml').decode('utf-8')
            self.hpf_xml_raw = z.read('Contents/content.hpf').decode('utf-8')

        if self.use_reference:
            self._parse_reference_header(self.header_xml_raw)
        else:
            self._init_default_styles()

    def _init_default_styles(self):
        """Set up default style mappings for built-in blank.hwpx template."""
        self.normal_style_id = '0'
        self.normal_para_pr_id = '0'
        self.normal_char_pr_id = '0'
        self.max_char_pr_id = max(c[0] for c in HEADING_CHAR_PROPS)
        self.max_char_pr_id = max(self.max_char_pr_id, CODE_CHAR_PR_ID)

    def _parse_reference_header(self, header_xml):
        """Parse header.xml from reference document for dynamic style mapping.

        Extracts outline levels, style IDs, charPr/paraPr IDs.
        (Ported from pypandoc-hwpx _parse_styles_and_init_xml)
        """
        try:
            self.header_tree = ET.ElementTree(ET.fromstring(header_xml))
            self.header_root = self.header_tree.getroot()
            root = self.header_root

            # Find max IDs
            for char_pr in root.findall('.//hh:charPr', NS):
                c_id = int(char_pr.get('id', 0))
                if c_id > self.max_char_pr_id:
                    self.max_char_pr_id = c_id

            for para_pr in root.findall('.//hh:paraPr', NS):
                p_id = int(para_pr.get('id', 0))
                if p_id > self.max_para_pr_id:
                    self.max_para_pr_id = p_id

            # Find Normal Style
            normal_style_node = root.find('.//hh:style[@id="0"]', NS)
            if normal_style_node is None:
                all_styles = root.findall('.//hh:style', NS)
                if all_styles:
                    normal_style_node = all_styles[0]

            if normal_style_node is not None:
                self.normal_style_id = normal_style_node.get('id', '0')
                self.normal_para_pr_id = normal_style_node.get('paraPrIDRef', '0')
                self.normal_char_pr_id = normal_style_node.get('charPrIDRef', '0')

            # Map Outline Levels -> paraPr
            level_to_para_pr = {}
            for para_pr in root.findall('.//hh:paraPr', NS):
                p_id = para_pr.get('id')
                for heading in para_pr.findall('.//hh:heading', NS):
                    if heading.get('type') == 'OUTLINE':
                        level_str = heading.get('level')
                        if level_str is not None:
                            level = int(level_str)
                            if level not in level_to_para_pr:
                                level_to_para_pr[level] = p_id

            # Map paraPr -> style info
            para_pr_to_style_info = {}
            for style in root.findall('.//hh:style', NS):
                s_id = style.get('id')
                p_ref = style.get('paraPrIDRef')
                c_ref = style.get('charPrIDRef')
                if p_ref not in para_pr_to_style_info:
                    para_pr_to_style_info[p_ref] = {
                        'style_id': s_id,
                        'char_pr_id': c_ref,
                    }

            # Combine
            for level, p_id in level_to_para_pr.items():
                if p_id in para_pr_to_style_info:
                    info = para_pr_to_style_info[p_id]
                    self.dynamic_style_map[level] = {
                        'style_id': info['style_id'],
                        'para_pr_id': p_id,
                        'char_pr_id': info['char_pr_id'],
                    }
                    self.outline_style_ids[level] = info['style_id']

            # Init numbering structure
            self._init_numbering_structure(root)

            # Ensure table border fill
            self._ensure_table_border_fill(root)

        except Exception as e:
            print(f"[Warn] Failed to parse reference header.xml: {e}",
                  file=sys.stderr)
            self.use_reference = False
            self._init_default_styles()

    def _ensure_table_border_fill(self, root):
        """Add a solid-border borderFill for table cells."""
        border_fills = root.find('.//hh:borderFills', NS)
        if border_fills is None:
            return

        max_id = 0
        for bf in border_fills.findall('hh:borderFill', NS):
            bid = int(bf.get('id', 0))
            if bid > max_id:
                max_id = bid

        self.table_border_fill_id = str(max_id + 1)
        xml_str = (
            f'<hh:borderFill id="{self.table_border_fill_id}" threeD="0" shadow="0"'
            f' centerLine="NONE" breakCellSeparateLine="0"'
            f' xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"'
            f' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
            f'<hh:slash type="NONE" Crooked="0" isCounter="0"/>'
            f'<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
            f'<hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>'
            f'<hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>'
            f'<hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>'
            f'<hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>'
            f'<hh:diagonal type="NONE" width="0.12 mm" color="#000000"/>'
            f'</hh:borderFill>'
        )
        border_fills.append(ET.fromstring(xml_str))

    def _init_numbering_structure(self, root):
        """Ensure hh:numberings element exists in header."""
        if root.find('.//hh:numberings', NS) is None:
            ET.SubElement(root, '{http://www.hancom.co.kr/hwpml/2011/head}numberings')

    def _extract_metadata(self):
        """Extract title, subtitle, author, date from AST metadata."""
        meta = self.ast.get('meta', {})
        self.title = self._extract_meta_text(meta.get('title'))
        self.subtitle = self._extract_meta_text(meta.get('subtitle'))
        self.author = self._extract_meta_text(meta.get('author'))
        self.date_str = self._extract_meta_text(meta.get('date'))

    @staticmethod
    def _extract_meta_text(meta_val):
        """Extract plain text from a Pandoc Meta value."""
        if meta_val is None:
            return ''
        t = meta_val.get('t', '')
        c = meta_val.get('c')
        if t == 'MetaString':
            return c
        elif t == 'MetaInlines':
            return PandocHwpxConverter._get_plain_text_static(c)
        elif t == 'MetaList':
            parts = []
            for item in c:
                parts.append(PandocHwpxConverter._extract_meta_text(item))
            return ', '.join(p for p in parts if p)
        return ''

    @staticmethod
    def _get_plain_text_static(inlines):
        """Extract plain text from inline elements (static helper)."""
        if not isinstance(inlines, list):
            return ''
        parts = []
        for item in inlines:
            t = item.get('t', '')
            c = item.get('c')
            if t == 'Str':
                parts.append(c)
            elif t == 'Space':
                parts.append(' ')
            elif t == 'SoftBreak':
                parts.append(' ')
            elif t == 'LineBreak':
                parts.append('\n')
            elif t in ('Strong', 'Emph', 'Strikeout', 'Superscript',
                       'Subscript', 'SmallCaps', 'Underline'):
                parts.append(PandocHwpxConverter._get_plain_text_static(c))
            elif t == 'Code':
                parts.append(c[1])
            elif t == 'Link':
                parts.append(PandocHwpxConverter._get_plain_text_static(c[1]))
            elif t == 'Image':
                parts.append(PandocHwpxConverter._get_plain_text_static(c[1]))
            elif t == 'Quoted':
                qtype = c[0].get('t', 'DoubleQuote') if isinstance(c[0], dict) else c[0]
                q1 = '\u201c' if qtype == 'DoubleQuote' else '\u2018'
                q2 = '\u201d' if qtype == 'DoubleQuote' else '\u2019'
                parts.append(q1 + PandocHwpxConverter._get_plain_text_static(c[1]) + q2)
            elif t == 'Cite':
                parts.append(PandocHwpxConverter._get_plain_text_static(c[1]))
            elif t == 'Math':
                parts.append(c[1])
            elif t == 'Span':
                parts.append(PandocHwpxConverter._get_plain_text_static(c[1]))
        return ''.join(parts)

    # ── Conversion entry point ────────────────────────────────────────────

    def convert(self, output_path):
        """Run full conversion and write .hwpx output file."""
        blocks = self.ast.get('blocks', [])

        # Build section0.xml body
        body_parts = []

        # Title block
        body_parts.extend(self._build_title_block())

        # Table of contents
        if self.toc:
            body_parts.extend(self._build_toc_block(blocks))

        # Content blocks
        body_parts.extend(self._process_blocks(blocks))

        if not body_parts:
            body_parts.append(self._make_paragraph_xml(''))

        body_xml = '\n'.join(body_parts)

        # Build section0.xml
        section_xml = self._build_section_xml(body_xml)

        # Update header.xml
        updated_header = self._update_header_xml()

        # Update content.hpf
        updated_hpf = self._update_content_hpf()

        # Write output
        self._write_hwpx(output_path, section_xml, updated_header, updated_hpf)

    def _build_title_block(self):
        """Build title block paragraphs from document metadata."""
        parts = []
        if self.title:
            if self.use_reference and self.header_root is not None:
                # Use dynamic styles from reference
                parts.append(self._make_paragraph_xml(
                    self.title, style_id=self.normal_style_id,
                    para_pr_id=self.normal_para_pr_id,
                    char_pr_id=self._get_format_char_pr_id(
                        self.normal_char_pr_id, {'BOLD'})))
            else:
                parts.append(self._make_paragraph_xml(
                    self.title, char_pr_id=7))  # 22pt bold
        if self.subtitle:
            if self.use_reference and self.header_root is not None:
                parts.append(self._make_paragraph_xml(
                    self.subtitle, style_id=self.normal_style_id,
                    para_pr_id=self.normal_para_pr_id,
                    char_pr_id=self._get_format_char_pr_id(
                        self.normal_char_pr_id, {'BOLD'})))
            else:
                parts.append(self._make_paragraph_xml(
                    self.subtitle, char_pr_id=8))  # 16pt bold
        if self.author or self.date_str:
            meta_line = ' | '.join(p for p in [self.author, self.date_str] if p)
            parts.append(self._make_paragraph_xml(meta_line))
        if parts:
            parts.append(self._make_paragraph_xml(''))  # blank separator
        return parts

    # ── Table of Contents ───────────────────────────────────────────────

    def _collect_headings(self, blocks):
        """Scan blocks recursively and collect all Header elements."""
        headings = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            t = block.get('t', '')
            c = block.get('c')
            if t == 'Header':
                level = c[0]
                attr = c[1]
                heading_id = attr[0] if attr else ''
                inlines = c[2]
                text = self._get_plain_text_static(inlines)
                headings.append({
                    'level': level, 'id': heading_id, 'text': text
                })
            elif t == 'Div':
                if len(c) > 1:
                    headings.extend(self._collect_headings(c[1]))
        return headings

    def _build_toc_block(self, blocks):
        """Build table of contents paragraphs from collected headings."""
        headings = self._collect_headings(blocks)
        if not headings:
            return []

        parts = []

        # TOC title (16pt bold, like H2)
        parts.append(self._make_paragraph_xml('목  차', char_pr_id='8'))
        parts.append(self._make_paragraph_xml(''))

        min_level = min(h['level'] for h in headings)

        for h in headings:
            level = h['level']
            text = h['text']
            relative_level = level - min_level
            indent = '\u3000' * relative_level

            if relative_level == 0:
                # Top-level: bold
                if self.use_reference and self.header_root is not None:
                    bold_id = self._get_format_char_pr_id(
                        self.normal_char_pr_id, {'BOLD'})
                else:
                    bold_id = self._get_builtin_char_pr_id('0', {'BOLD'})
                parts.append(self._make_paragraph_xml(
                    indent + text, char_pr_id=bold_id))
            else:
                # Sub-level: normal with indent
                parts.append(self._make_paragraph_xml(indent + text))

        # Separator
        parts.append(self._make_paragraph_xml(''))
        parts.append(self._make_paragraph_xml('\u2501' * 30))
        parts.append(self._make_paragraph_xml(''))

        return parts

    # ── Paragraph XML builders ────────────────────────────────────────────

    def _make_paragraph_xml(self, text, style_id='0', para_pr_id='0',
                            char_pr_id='0', lineseg=True):
        """Build a <hp:p> XML string with optional linesegarray."""
        pid = _next_para_id()
        safe_text = xml_escape(text) if text else ''

        char_height = CHAR_HEIGHT_MAP.get(int(char_pr_id) if str(char_pr_id).isdigit() else 0,
                                          CHAR_HEIGHT_NORMAL)
        lineseg_xml = compute_lineseg_xml(text, char_height=char_height) if lineseg else ''

        return (
            f'<hp:p id="{pid}" paraPrIDRef="{para_pr_id}"'
            f' styleIDRef="{style_id}"'
            f' pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{char_pr_id}">'
            f'<hp:t>{safe_text}</hp:t></hp:run>'
            f'{lineseg_xml}'
            f'</hp:p>'
        )

    def _make_rich_paragraph_xml(self, runs_xml, style_id='0',
                                 para_pr_id='0', lineseg_text=''):
        """Build a <hp:p> with pre-built run content (for inline formatting)."""
        pid = _next_para_id()
        lineseg_xml = compute_lineseg_xml(lineseg_text) if lineseg_text is not None else ''
        return (
            f'<hp:p id="{pid}" paraPrIDRef="{para_pr_id}"'
            f' styleIDRef="{style_id}"'
            f' pageBreak="0" columnBreak="0" merged="0">'
            f'{runs_xml}'
            f'{lineseg_xml}'
            f'</hp:p>'
        )

    # ── Inline processing (from pypandoc-hwpx) ───────────────────────────

    def _process_inlines(self, inlines, base_char_pr_id='0',
                         active_formats=None):
        """Process inline elements preserving formatting.

        Each formatting change (bold, italic, underline, etc.) creates a
        new charPr in header.xml if using reference doc, or uses appropriate
        raw XML attributes for built-in template.
        """
        if not isinstance(inlines, list):
            return '', ''
        if active_formats is None:
            active_formats = set()

        def get_current_id():
            if self.use_reference:
                return self._get_format_char_pr_id(base_char_pr_id, active_formats)
            else:
                return self._get_builtin_char_pr_id(base_char_pr_id, active_formats)

        xml_parts = []
        text_parts = []  # for lineseg calculation

        for item in inlines:
            i_type = item.get('t', '')
            i_content = item.get('c')

            if i_type == 'Str':
                cid = get_current_id()
                xml_parts.append(
                    f'<hp:run charPrIDRef="{cid}">'
                    f'<hp:t>{xml_escape(i_content)}</hp:t></hp:run>')
                text_parts.append(i_content)

            elif i_type == 'Space':
                cid = get_current_id()
                xml_parts.append(
                    f'<hp:run charPrIDRef="{cid}">'
                    f'<hp:t> </hp:t></hp:run>')
                text_parts.append(' ')

            elif i_type == 'SoftBreak':
                cid = get_current_id()
                xml_parts.append(
                    f'<hp:run charPrIDRef="{cid}">'
                    f'<hp:t> </hp:t></hp:run>')
                text_parts.append(' ')

            elif i_type == 'LineBreak':
                cid = get_current_id()
                xml_parts.append(
                    f'<hp:run charPrIDRef="{cid}">'
                    f'<hp:t><hp:lineBreak/></hp:t></hp:run>')
                text_parts.append('\n')

            elif i_type == 'Strong':
                new_fmts = active_formats | {'BOLD'}
                runs, text = self._process_inlines(
                    i_content, base_char_pr_id, new_fmts)
                xml_parts.append(runs)
                text_parts.append(text)

            elif i_type == 'Emph':
                new_fmts = active_formats | {'ITALIC'}
                runs, text = self._process_inlines(
                    i_content, base_char_pr_id, new_fmts)
                xml_parts.append(runs)
                text_parts.append(text)

            elif i_type == 'Underline':
                new_fmts = active_formats | {'UNDERLINE'}
                runs, text = self._process_inlines(
                    i_content, base_char_pr_id, new_fmts)
                xml_parts.append(runs)
                text_parts.append(text)

            elif i_type == 'Strikeout':
                new_fmts = active_formats | {'STRIKEOUT'}
                runs, text = self._process_inlines(
                    i_content, base_char_pr_id, new_fmts)
                xml_parts.append(runs)
                text_parts.append(text)

            elif i_type == 'Superscript':
                new_fmts = active_formats | {'SUPERSCRIPT'}
                runs, text = self._process_inlines(
                    i_content, base_char_pr_id, new_fmts)
                xml_parts.append(runs)
                text_parts.append(text)

            elif i_type == 'Subscript':
                new_fmts = active_formats | {'SUBSCRIPT'}
                runs, text = self._process_inlines(
                    i_content, base_char_pr_id, new_fmts)
                xml_parts.append(runs)
                text_parts.append(text)

            elif i_type == 'Code':
                # Inline code with D2Coding font
                code_text = i_content[1]
                code_cid = str(CODE_CHAR_PR_ID)
                xml_parts.append(
                    f'<hp:run charPrIDRef="{code_cid}">'
                    f'<hp:t>{xml_escape(code_text)}</hp:t></hp:run>')
                text_parts.append(code_text)

            elif i_type == 'Link':
                # Link = [attr, [text_inlines], [target, title]]
                text_inlines = i_content[1]
                target_url = i_content[2][0]

                # Field begin
                xml_parts.append(self._create_field_begin(target_url))

                # Link text with blue + underline
                new_fmts = active_formats | {'UNDERLINE', 'COLOR_BLUE'}
                runs, text = self._process_inlines(
                    text_inlines, base_char_pr_id, new_fmts)
                xml_parts.append(runs)
                text_parts.append(text)

                # Field end
                xml_parts.append(self._create_field_end())

            elif i_type == 'Image':
                # Image = [attr, [caption], [target, title]]
                img_xml = self._handle_image(i_content, char_pr_id=get_current_id())
                xml_parts.append(img_xml)
                text_parts.append('[image]')

            elif i_type == 'Note':
                # Footnote: content is list of blocks
                xml_parts.append(self._create_footnote(i_content))

            elif i_type == 'Math':
                math_type = i_content[0]
                latex_str = i_content[1]
                if isinstance(math_type, dict):
                    math_type = math_type.get('t', 'InlineMath')
                # Inline math -> equation element
                eq_xml = make_equation_xml(latex_str)
                cid = get_current_id()
                xml_parts.append(
                    f'<hp:run charPrIDRef="{cid}">{eq_xml}</hp:run>')
                text_parts.append(latex_str)

            elif i_type == 'Quoted':
                qtype = i_content[0]
                if isinstance(qtype, dict):
                    qtype = qtype.get('t', 'DoubleQuote')
                q1 = '\u201c' if qtype == 'DoubleQuote' else '\u2018'
                q2 = '\u201d' if qtype == 'DoubleQuote' else '\u2019'
                cid = get_current_id()
                xml_parts.append(
                    f'<hp:run charPrIDRef="{cid}">'
                    f'<hp:t>{q1}</hp:t></hp:run>')
                runs, text = self._process_inlines(
                    i_content[1], base_char_pr_id, active_formats)
                xml_parts.append(runs)
                xml_parts.append(
                    f'<hp:run charPrIDRef="{cid}">'
                    f'<hp:t>{q2}</hp:t></hp:run>')
                text_parts.append(q1 + text + q2)

            elif i_type == 'Cite':
                runs, text = self._process_inlines(
                    i_content[1], base_char_pr_id, active_formats)
                xml_parts.append(runs)
                text_parts.append(text)

            elif i_type == 'Span':
                # Check for Quarto cross-reference
                attrs = i_content[0]
                classes = attrs[1] if len(attrs) > 1 else []
                runs, text = self._process_inlines(
                    i_content[1], base_char_pr_id, active_formats)
                xml_parts.append(runs)
                text_parts.append(text)

            elif i_type == 'SmallCaps':
                runs, text = self._process_inlines(
                    i_content, base_char_pr_id, active_formats)
                xml_parts.append(runs)
                text_parts.append(text)

            elif i_type == 'RawInline':
                # Skip raw inline (HTML etc.)
                pass

        return ''.join(xml_parts), ''.join(text_parts)

    # ── CharPr management ─────────────────────────────────────────────────

    def _get_builtin_char_pr_id(self, base_id, active_formats):
        """Get charPr ID for built-in template (no dynamic creation).

        For the built-in template, we create new charPr entries by injecting
        them into header.xml during update. We cache the mapping.
        """
        if not active_formats:
            return str(base_id)

        cache_key = (str(base_id), frozenset(active_formats))
        if cache_key in self.char_pr_cache:
            return self.char_pr_cache[cache_key]

        # Allocate new ID
        self.max_char_pr_id += 1
        new_id = str(self.max_char_pr_id)
        self.char_pr_cache[cache_key] = new_id
        return new_id

    def _get_format_char_pr_id(self, base_id, active_formats):
        """Get or create a charPr ID with given formats applied.

        For reference-doc mode: clones the base charPr node in the
        ElementTree, applies format modifications, caches result.
        (Ported from pypandoc-hwpx _get_char_pr_id)
        """
        if not active_formats:
            return str(base_id)

        base_id = str(base_id)
        cache_key = (base_id, frozenset(active_formats))
        if cache_key in self.char_pr_cache:
            return self.char_pr_cache[cache_key]

        if self.header_root is None:
            return base_id

        base_node = self.header_root.find(
            f'.//hh:charPr[@id="{base_id}"]', NS)
        if base_node is None:
            base_node = self.header_root.find('.//hh:charPr[@id="0"]', NS)
            if base_node is None:
                return base_id

        new_node = copy.deepcopy(base_node)
        self.max_char_pr_id += 1
        new_id = str(self.max_char_pr_id)
        new_node.set('id', new_id)

        HH = '{http://www.hancom.co.kr/hwpml/2011/head}'

        if 'BOLD' in active_formats:
            if new_node.find('hh:bold', NS) is None:
                ET.SubElement(new_node, f'{HH}bold')

        if 'ITALIC' in active_formats:
            if new_node.find('hh:italic', NS) is None:
                ET.SubElement(new_node, f'{HH}italic')

        if 'UNDERLINE' in active_formats:
            ul = new_node.find('hh:underline', NS)
            if ul is None:
                ul = ET.SubElement(new_node, f'{HH}underline')
            ul.set('type', 'BOTTOM')
            ul.set('shape', 'SOLID')
            ul.set('color', '#000000')

        if 'STRIKEOUT' in active_formats:
            so = new_node.find('hh:strikeout', NS)
            if so is None:
                so = ET.SubElement(new_node, f'{HH}strikeout')
            so.set('shape', 'SOLID')
            so.set('color', '#000000')

        if 'COLOR_BLUE' in active_formats:
            new_node.set('textColor', '#0000FF')
            ul = new_node.find('hh:underline', NS)
            if ul is not None:
                ul.set('color', '#0000FF')

        if 'SUPERSCRIPT' in active_formats:
            sub = new_node.find('hh:subscript', NS)
            if sub is not None:
                new_node.remove(sub)
            if new_node.find('hh:supscript', NS) is None:
                ET.SubElement(new_node, f'{HH}supscript')

        elif 'SUBSCRIPT' in active_formats:
            sup = new_node.find('hh:supscript', NS)
            if sup is not None:
                new_node.remove(sup)
            if new_node.find('hh:subscript', NS) is None:
                ET.SubElement(new_node, f'{HH}subscript')

        char_props = self.header_root.find('.//hh:charProperties', NS)
        if char_props is not None:
            char_props.append(new_node)

        self.char_pr_cache[cache_key] = new_id
        return new_id

    # ── Block processing ──────────────────────────────────────────────────

    def _process_blocks(self, blocks, indent_level=0):
        """Convert Pandoc AST blocks to list of XML strings."""
        xml_parts = []
        indent_prefix = '\u3000' * indent_level

        for block in blocks:
            if not isinstance(block, dict):
                continue
            t = block.get('t', '')
            c = block.get('c')

            if t in ('Para', 'Plain'):
                xml_parts.extend(self._handle_para_or_plain(
                    c, indent_prefix, indent_level))

            elif t == 'Header':
                xml_parts.append(self._handle_header(c))

            elif t == 'CodeBlock':
                xml_parts.extend(self._handle_code_block(c, indent_prefix))

            elif t == 'BulletList':
                xml_parts.extend(self._handle_bullet_list(c, indent_level))

            elif t == 'OrderedList':
                xml_parts.extend(self._handle_ordered_list(c, indent_level))

            elif t == 'BlockQuote':
                child_parts = self._process_blocks(c, indent_level + 1)
                xml_parts.extend(child_parts)

            elif t == 'Table':
                xml_parts.append(self._handle_table(c))

            elif t == 'HorizontalRule':
                xml_parts.append(self._make_paragraph_xml('\u2501' * 30))

            elif t == 'Div':
                xml_parts.extend(self._handle_div(c, indent_level))

            elif t == 'DefinitionList':
                for item in c:
                    term_text = self._get_plain_text_static(item[0])
                    xml_parts.append(self._make_paragraph_xml(
                        indent_prefix + term_text))
                    for def_blocks in item[1]:
                        xml_parts.extend(self._process_blocks(
                            def_blocks, indent_level + 1))

            elif t == 'LineBlock':
                for line_inlines in c:
                    line_text = self._get_plain_text_static(line_inlines)
                    xml_parts.append(self._make_paragraph_xml(
                        indent_prefix + line_text))

            elif t == 'RawBlock':
                # Skip raw blocks (HTML, etc.)
                pass

        return xml_parts

    def _handle_para_or_plain(self, inlines, indent_prefix='', indent_level=0):
        """Handle Para or Plain block with full inline processing."""
        parts = []

        # Check for standalone math equation
        if len(inlines) == 1 and inlines[0].get('t') == 'Math':
            math_type = inlines[0]['c'][0]
            if isinstance(math_type, dict):
                math_type = math_type.get('t', 'InlineMath')
            if math_type == 'DisplayMath':
                latex_str = inlines[0]['c'][1]
                parts.append(self._make_equation_paragraph(latex_str))
                return parts

        # Check for standalone image
        if len(inlines) == 1 and inlines[0].get('t') == 'Image':
            img_content = inlines[0]['c']
            # Image in its own paragraph
            img_xml = self._handle_image(img_content)
            para_xml = self._make_rich_paragraph_xml(img_xml)
            parts.append(para_xml)
            return parts

        # Normal paragraph with inline formatting
        if self.use_reference and self.header_root is not None:
            base_cid = self.normal_char_pr_id
            sid = self.normal_style_id
            pid = self.normal_para_pr_id
        else:
            base_cid = '0'
            sid = '0'
            pid = '0'

        runs_xml, plain_text = self._process_inlines(inlines, base_cid)
        if indent_prefix:
            plain_text = indent_prefix + plain_text
            runs_xml = (
                f'<hp:run charPrIDRef="{base_cid}">'
                f'<hp:t>{indent_prefix}</hp:t></hp:run>' + runs_xml)

        lineseg_xml = compute_lineseg_xml(plain_text)
        para_pid = _next_para_id()
        para = (
            f'<hp:p id="{para_pid}" paraPrIDRef="{pid}"'
            f' styleIDRef="{sid}"'
            f' pageBreak="0" columnBreak="0" merged="0">'
            f'{runs_xml}{lineseg_xml}</hp:p>'
        )
        parts.append(para)
        return parts

    def _make_equation_paragraph(self, latex_str):
        """Build a paragraph containing an equation object."""
        pid = _next_para_id()
        eq_xml = make_equation_xml(latex_str)
        return (
            f'<hp:p id="{pid}" paraPrIDRef="0" styleIDRef="0"'
            f' pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="0">{eq_xml}</hp:run>'
            f'<hp:linesegarray>'
            f'<hp:lineseg textpos="0" vertpos="0" vertsize="1600"'
            f' textheight="1600" baseline="1360" spacing="400"'
            f' horzpos="0" horzsize="42520" flags="393216"/>'
            f'</hp:linesegarray>'
            f'</hp:p>'
        )

    def _handle_header(self, content):
        """Handle Header block."""
        level = content[0]
        # attr = content[1]
        inlines = content[2]

        if self.use_reference:
            hwpx_level = level - 1
            if hwpx_level in self.dynamic_style_map:
                info = self.dynamic_style_map[hwpx_level]
                sid = info['style_id']
                pid = info['para_pr_id']
                base_cid = info['char_pr_id']
            else:
                sid, pid, cid = HEADING_STYLE.get(level, (0, 0, 0))
                sid, pid, base_cid = str(sid), str(pid), str(cid)
        else:
            sid, pid, base_cid = HEADING_STYLE.get(level, (0, 0, 0))
            sid, pid, base_cid = str(sid), str(pid), str(base_cid)

        runs_xml, plain_text = self._process_inlines(inlines, base_cid)
        lineseg_xml = compute_lineseg_xml(
            plain_text,
            char_height=CHAR_HEIGHT_MAP.get(int(base_cid) if str(base_cid).isdigit() else 0,
                                            CHAR_HEIGHT_NORMAL))

        para_pid = _next_para_id()
        return (
            f'<hp:p id="{para_pid}" paraPrIDRef="{pid}"'
            f' styleIDRef="{sid}"'
            f' pageBreak="0" columnBreak="0" merged="0">'
            f'{runs_xml}{lineseg_xml}</hp:p>'
        )

    def _handle_code_block(self, content, indent_prefix=''):
        """Handle CodeBlock with D2Coding font, line-by-line paragraphs."""
        # content = [attr, code_text]
        # attr = [id, classes, key-val pairs]
        attrs = content[0]
        code_text = content[1]
        classes = attrs[1] if len(attrs) > 1 else []

        parts = []
        for line in code_text.split('\n'):
            parts.append(self._make_paragraph_xml(
                indent_prefix + line,
                char_pr_id=str(CODE_CHAR_PR_ID)))
        return parts

    def _handle_bullet_list(self, items, indent_level=0):
        """Handle BulletList with native HWPX numbering or text prefix."""
        if self.use_reference and self.header_root is not None:
            return self._handle_bullet_list_native(items, indent_level)

        # Fallback: text prefix bullets
        results = []
        for item_blocks in items:
            item_parts = self._process_blocks(item_blocks, indent_level)
            if item_parts:
                item_parts[0] = item_parts[0].replace(
                    '<hp:t>', '<hp:t>\u2022 ', 1)
            results.extend(item_parts)
        return results

    def _handle_bullet_list_native(self, items, level=0):
        """Handle BulletList with HWPX native numbering definitions."""
        num_id = self._create_numbering('BULLET')
        results = []
        for item_blocks in items:
            for block in item_blocks:
                b_type = block.get('t')
                b_content = block.get('c')
                if b_type in ('Para', 'Plain'):
                    list_para_pr = self._get_list_para_pr(num_id, level)
                    runs_xml, plain_text = self._process_inlines(
                        b_content, self.normal_char_pr_id)
                    lineseg_xml = compute_lineseg_xml(plain_text)
                    pid = _next_para_id()
                    xml = (
                        f'<hp:p id="{pid}" paraPrIDRef="{list_para_pr}"'
                        f' styleIDRef="{self.normal_style_id}"'
                        f' pageBreak="0" columnBreak="0" merged="0">'
                        f'{runs_xml}{lineseg_xml}</hp:p>'
                    )
                    results.append(xml)
                elif b_type == 'BulletList':
                    results.extend(self._handle_bullet_list_native(
                        b_content, level + 1))
                elif b_type == 'OrderedList':
                    results.extend(self._handle_ordered_list_native(
                        b_content, level + 1))
                else:
                    results.extend(self._process_blocks([block]))
        return results

    def _handle_ordered_list(self, content, indent_level=0):
        """Handle OrderedList."""
        if self.use_reference and self.header_root is not None:
            return self._handle_ordered_list_native(content, indent_level)

        # Fallback: text prefix numbering
        start_num = content[0][0]
        results = []
        for idx, item_blocks in enumerate(content[1]):
            item_parts = self._process_blocks(item_blocks, indent_level)
            if item_parts:
                num = start_num + idx
                item_parts[0] = item_parts[0].replace(
                    '<hp:t>', f'<hp:t>{num}. ', 1)
            results.extend(item_parts)
        return results

    def _handle_ordered_list_native(self, content, level=0):
        """Handle OrderedList with HWPX native numbering."""
        attrs = content[0]
        start_num = attrs[0]
        items = content[1]

        num_id = self._create_numbering('ORDERED', start_num)
        results = []
        for item_blocks in items:
            for block in item_blocks:
                b_type = block.get('t')
                b_content = block.get('c')
                if b_type in ('Para', 'Plain'):
                    list_para_pr = self._get_list_para_pr(num_id, level)
                    runs_xml, plain_text = self._process_inlines(
                        b_content, self.normal_char_pr_id)
                    lineseg_xml = compute_lineseg_xml(plain_text)
                    pid = _next_para_id()
                    xml = (
                        f'<hp:p id="{pid}" paraPrIDRef="{list_para_pr}"'
                        f' styleIDRef="{self.normal_style_id}"'
                        f' pageBreak="0" columnBreak="0" merged="0">'
                        f'{runs_xml}{lineseg_xml}</hp:p>'
                    )
                    results.append(xml)
                elif b_type == 'BulletList':
                    results.extend(self._handle_bullet_list_native(
                        b_content, level + 1))
                elif b_type == 'OrderedList':
                    results.extend(self._handle_ordered_list_native(
                        b_content, level + 1))
                else:
                    results.extend(self._process_blocks([block]))
        return results

    def _create_numbering(self, num_type='ORDERED', start_num=1):
        """Create a numbering definition in header.xml."""
        root = self.header_root
        max_num_id = 0
        for num in root.findall('.//hh:numbering', NS):
            nid = int(num.get('id', 0))
            if nid > max_num_id:
                max_num_id = nid

        new_id = str(max_num_id + 1)
        HH_NS = 'http://www.hancom.co.kr/hwpml/2011/head'

        if num_type == 'ORDERED':
            template = (
                f'<hh:numbering id="{new_id}" start="{start_num}"'
                f' xmlns:hh="{HH_NS}">'
                f'<hh:paraHead start="1" level="1" align="LEFT"'
                f' useInstWidth="1" autoIndent="0" widthAdjust="0"'
                f' textOffsetType="PERCENT" textOffset="50"'
                f' numFormat="DIGIT" charPrIDRef="4294967295"'
                f' checkable="0">^1.</hh:paraHead>'
                f'</hh:numbering>'
            )
        else:
            template = (
                f'<hh:numbering id="{new_id}" start="1"'
                f' xmlns:hh="{HH_NS}">'
                f'<hh:paraHead start="1" level="1" align="LEFT"'
                f' useInstWidth="1" autoIndent="0" widthAdjust="0"'
                f' textOffsetType="PERCENT" textOffset="50"'
                f' numFormat="DIGIT" charPrIDRef="4294967295"'
                f' checkable="0">\u25cf</hh:paraHead>'
                f'</hh:numbering>'
            )

        numberings = root.find('.//hh:numberings', NS)
        if numberings is None:
            self._init_numbering_structure(root)
            numberings = root.find('.//hh:numberings', NS)
        numberings.append(ET.fromstring(template))
        return new_id

    def _get_list_para_pr(self, num_id, level):
        """Create a paraPr for list items with numbering reference."""
        root = self.header_root
        base_id = self.normal_para_pr_id
        base_node = root.find(f'.//hh:paraPr[@id="{base_id}"]', NS)
        if base_node is None:
            return base_id

        new_node = copy.deepcopy(base_node)
        self.max_para_pr_id += 1
        new_id = str(self.max_para_pr_id)
        new_node.set('id', new_id)

        heading = new_node.find('hh:heading', NS)
        if heading is None:
            heading = ET.SubElement(
                new_node,
                '{http://www.hancom.co.kr/hwpml/2011/head}heading')
        heading.set('type', 'NUMBER')
        heading.set('idRef', str(num_id))
        heading.set('level', str(level))

        indent_per_level = 2000
        for left_node in new_node.findall('.//hc:left', NS):
            val = (level + 1) * indent_per_level
            left_node.set('value', str(val))
        for intent_node in new_node.findall('.//hc:intent', NS):
            intent_node.set('value', str(-indent_per_level))

        para_props = root.find('.//hh:paraProperties', NS)
        if para_props is not None:
            para_props.append(new_node)
        return new_id

    def _handle_div(self, content, indent_level):
        """Handle Div block, with special handling for Quarto output wrappers."""
        attrs = content[0]
        blocks = content[1]
        classes = attrs[1] if len(attrs) > 1 else []

        # Quarto cell wrappers - transparent pass-through
        quarto_passthrough = [
            'cell', 'cell-output-display', 'cell-output',
            'quarto-layout-panel', 'quarto-layout-row',
            'quarto-layout-cell', 'quarto-figure',
        ]

        if any(cls in classes for cls in quarto_passthrough):
            return self._process_blocks(blocks, indent_level)

        # cell-output-stdout: render contained CodeBlocks as output style
        if 'cell-output-stdout' in classes:
            return self._process_blocks(blocks, indent_level)

        # cell-output-stderr: optionally skip
        if 'cell-output-stderr' in classes:
            # Render as code output (could be configurable to skip)
            return self._process_blocks(blocks, indent_level)

        # Default: transparent pass-through
        return self._process_blocks(blocks, indent_level)

    # ── Table handling (with rowspan/colspan from pypandoc-hwpx) ──────────

    def _handle_table(self, content):
        """Handle Table block with full rowspan/colspan support."""
        # content = [attr, caption, specs, table_head, table_bodies, table_foot]
        caption = content[1]
        specs = content[2]
        table_head = content[3]
        table_bodies = content[4]
        table_foot = content[5]

        # Flatten all rows
        all_rows = []
        head_rows = table_head[1] if len(table_head) > 1 else []
        for row in head_rows:
            all_rows.append(row)

        for body in table_bodies:
            inter_headers = body[2] if len(body) > 2 else []
            main_rows = body[3] if len(body) > 3 else []
            for row in inter_headers:
                all_rows.append(row)
            for row in main_rows:
                all_rows.append(row)

        foot_rows = table_foot[1] if len(table_foot) > 1 else []
        for row in foot_rows:
            all_rows.append(row)

        if not all_rows:
            return ''

        row_cnt = len(all_rows)
        col_cnt = len(specs) if specs else 0
        if col_cnt == 0:
            # Infer from first row
            first_cells = all_rows[0][1] if len(all_rows[0]) > 1 else []
            col_cnt = len(first_cells)
        if col_cnt == 0:
            return ''

        # Calculate widths
        page_width = PAGE_TEXT_WIDTH
        col_widths = [page_width // col_cnt] * col_cnt
        # Distribute remainder
        remainder = page_width - sum(col_widths)
        for i in range(remainder):
            col_widths[i % col_cnt] += 1

        row_height = 1800
        total_height = row_height * row_cnt
        bfid = self.table_border_fill_id

        parts = []

        # Caption
        cap_text = ''
        if caption and len(caption) > 1 and caption[1]:
            for cb in caption[1]:
                if cb.get('t') in ('Para', 'Plain'):
                    cap_text += self._get_plain_text_static(cb.get('c', []))
        if cap_text:
            parts.append(self._make_paragraph_xml(cap_text))

        # Table wrapper paragraph
        pid = _next_para_id()
        tbl_id = _unique_id()

        parts.append(
            f'<hp:p id="{pid}" paraPrIDRef="0" styleIDRef="0"'
            f' pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="0">'
            f'<hp:tbl id="{tbl_id}" zOrder="0" numberingType="TABLE"'
            f' textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0"'
            f' dropcapstyle="None" pageBreak="CELL" repeatHeader="1"'
            f' rowCnt="{row_cnt}" colCnt="{col_cnt}"'
            f' cellSpacing="0" borderFillIDRef="{bfid}" noAdjust="0">'
            f'<hp:sz width="{page_width}" widthRelTo="ABSOLUTE"'
            f' height="{total_height}" heightRelTo="ABSOLUTE" protect="0"/>'
            f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1"'
            f' allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA"'
            f' horzRelTo="COLUMN" vertAlign="TOP" horzAlign="CENTER"'
            f' vertOffset="0" horzOffset="0"/>'
            f'<hp:outMargin left="0" right="0" top="141" bottom="141"/>'
            f'<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
        )

        # Rows with occupied-cell tracking for rowspan/colspan
        occupied_cells = set()
        curr_row_addr = 0

        for row in all_rows:
            cells = row[1] if len(row) > 1 else []
            parts.append('<hp:tr>')

            curr_col_addr = 0
            for cell in cells:
                while (curr_row_addr, curr_col_addr) in occupied_cells:
                    curr_col_addr += 1

                actual_col = curr_col_addr

                # Cell: [attr, align, rowspan, colspan, blocks]
                rowspan = cell[2] if len(cell) > 2 else 1
                colspan = cell[3] if len(cell) > 3 else 1
                cell_blocks = cell[4] if len(cell) > 4 else []

                # Mark occupied cells
                for r in range(rowspan):
                    for c_off in range(colspan):
                        occupied_cells.add(
                            (curr_row_addr + r, actual_col + c_off))

                # Cell width
                cell_width = 0
                for i in range(colspan):
                    idx = actual_col + i
                    if idx < len(col_widths):
                        cell_width += col_widths[idx]
                    else:
                        cell_width += page_width // col_cnt

                # Cell content
                header_flag = '1' if curr_row_addr < len(head_rows) else '0'
                cell_content = self._render_cell_content(cell_blocks, cell_width)

                sublist_id = _unique_id()
                parts.append(
                    f'<hp:tc name="" header="{header_flag}" hasMargin="0"'
                    f' protect="0" editable="0" dirty="0"'
                    f' borderFillIDRef="{bfid}">'
                    f'<hp:subList id="{sublist_id}"'
                    f' textDirection="HORIZONTAL" lineWrap="BREAK"'
                    f' vertAlign="CENTER" linkListIDRef="0"'
                    f' linkListNextIDRef="0" textWidth="0"'
                    f' textHeight="0" hasTextRef="0" hasNumRef="0">'
                    f'{cell_content}'
                    f'</hp:subList>'
                    f'<hp:cellAddr colAddr="{actual_col}"'
                    f' rowAddr="{curr_row_addr}"/>'
                    f'<hp:cellSpan colSpan="{colspan}"'
                    f' rowSpan="{rowspan}"/>'
                    f'<hp:cellSz width="{cell_width}"'
                    f' height="{row_height}"/>'
                    f'<hp:cellMargin left="141" right="141"'
                    f' top="141" bottom="141"/>'
                    f'</hp:tc>'
                )

                curr_col_addr += colspan

            parts.append('</hp:tr>')
            curr_row_addr += 1

        parts.append('</hp:tbl>')
        parts.append('<hp:t></hp:t></hp:run></hp:p>')

        return '\n'.join(parts)

    def _render_cell_content(self, cell_blocks, cell_width):
        """Render table cell blocks to XML."""
        if not cell_blocks:
            # Empty cell
            return self._make_paragraph_xml('')

        cell_parts = []
        for block in cell_blocks:
            if not isinstance(block, dict):
                continue
            bt = block.get('t', '')
            bc = block.get('c')

            if bt in ('Para', 'Plain'):
                if self.use_reference:
                    base_cid = self.normal_char_pr_id
                else:
                    base_cid = '0'
                runs_xml, plain_text = self._process_inlines(bc, base_cid)
                lineseg_xml = compute_lineseg_xml(
                    plain_text, horzsize=cell_width)
                pid = _next_para_id()
                cell_parts.append(
                    f'<hp:p id="{pid}" paraPrIDRef="0" styleIDRef="0"'
                    f' pageBreak="0" columnBreak="0" merged="0">'
                    f'{runs_xml}{lineseg_xml}</hp:p>')
            else:
                # Other block types in cells
                sub_parts = self._process_blocks([block])
                cell_parts.extend(sub_parts)

        if not cell_parts:
            return self._make_paragraph_xml('')
        return '\n'.join(cell_parts)

    # ── Hyperlink / Field handling (from pypandoc-hwpx) ──────────────────

    def _create_field_begin(self, url):
        """Create HYPERLINK field begin XML."""
        fid = _unique_id()
        self._last_field_id = fid
        command_url = url.replace(':', r'\:').replace('?', r'\?')
        command_str = f"{command_url};1;5;-1;"
        return (
            f'<hp:run charPrIDRef="0"><hp:ctrl>'
            f'<hp:fieldBegin id="{fid}" type="HYPERLINK" name=""'
            f' editable="0" dirty="1" zorder="-1" fieldid="{fid}"'
            f' metaTag="">'
            f'<hp:parameters cnt="6" name="">'
            f'<hp:integerParam name="Prop">0</hp:integerParam>'
            f'<hp:stringParam name="Command">{command_str}</hp:stringParam>'
            f'<hp:stringParam name="Path">{xml_escape(url)}</hp:stringParam>'
            f'<hp:stringParam name="Category">'
            f'HWPHYPERLINK_TYPE_URL</hp:stringParam>'
            f'<hp:stringParam name="TargetType">'
            f'HWPHYPERLINK_TARGET_HYPERLINK</hp:stringParam>'
            f'<hp:stringParam name="DocOpenType">'
            f'HWPHYPERLINK_JUMP_DONTCARE</hp:stringParam>'
            f'</hp:parameters>'
            f'</hp:fieldBegin>'
            f'</hp:ctrl></hp:run>'
        )

    def _create_field_end(self):
        """Create HYPERLINK field end XML."""
        fid = getattr(self, '_last_field_id', '0')
        return (
            f'<hp:run charPrIDRef="0"><hp:ctrl>'
            f'<hp:fieldEnd beginIDRef="{fid}" fieldid="{fid}"/>'
            f'</hp:ctrl></hp:run>'
        )

    # ── Footnote (from pypandoc-hwpx) ────────────────────────────────────

    def _create_footnote(self, blocks):
        """Create footnote XML with subList containing block content."""
        body_parts = self._process_blocks(blocks)
        body_xml = '\n'.join(body_parts)
        inst_id = _unique_id()
        return (
            f'<hp:run charPrIDRef="0"><hp:ctrl>'
            f'<hp:footNote number="0" instId="{inst_id}">'
            f'<hp:autoNum num="0" numType="FOOTNOTE"/>'
            f'<hp:subList id="{inst_id}" textDirection="HORIZONTAL"'
            f' lineWrap="BREAK" vertAlign="TOP" linkListIDRef="0"'
            f' linkListNextIDRef="0" textWidth="0" textHeight="0"'
            f' hasTextRef="0" hasNumRef="0">'
            f'{body_xml}'
            f'</hp:subList>'
            f'</hp:footNote>'
            f'</hp:ctrl></hp:run>'
        )

    # ── Image handling (from pypandoc-hwpx) ──────────────────────────────

    def _handle_image(self, content, char_pr_id='0'):
        """Handle Image inline element with Pillow-based auto-sizing."""
        # content = [attr, caption, [target, title]]
        attr = content[0]
        # caption = content[1]
        target = content[2]
        target_url = target[0]

        # Parse attributes for width/height
        attrs_map = dict(attr[2]) if len(attr) > 2 else {}
        width_attr = attrs_map.get('width')
        height_attr = attrs_map.get('height')

        # Default size
        width_hwp = 8504   # ~30mm
        height_hwp = 8504

        w_parsed = self._parse_dimension(width_attr)
        h_parsed = self._parse_dimension(height_attr)

        # Try reading image file for auto-sizing
        image_path = self._resolve_image_path(target_url)

        if Image is not None and image_path and os.path.exists(image_path):
            try:
                with Image.open(image_path) as im:
                    px_w, px_h = im.size
                    LUNIT_PER_PX = (25.4 * 283.465) / 96.0

                    if w_parsed and h_parsed:
                        width_hwp, height_hwp = w_parsed, h_parsed
                    elif w_parsed:
                        ratio = px_h / max(px_w, 1)
                        width_hwp = w_parsed
                        height_hwp = int(w_parsed * ratio)
                    elif h_parsed:
                        ratio = px_w / max(px_h, 1)
                        height_hwp = h_parsed
                        width_hwp = int(h_parsed * ratio)
                    else:
                        width_hwp = int(px_w * LUNIT_PER_PX)
                        height_hwp = int(px_h * LUNIT_PER_PX)
            except Exception:
                if w_parsed:
                    width_hwp = w_parsed
                if h_parsed:
                    height_hwp = h_parsed
        else:
            if w_parsed:
                width_hwp = w_parsed
            if h_parsed:
                height_hwp = h_parsed

        # Max width constraint (15cm = page text width)
        MAX_WIDTH = PAGE_TEXT_WIDTH
        if width_hwp > MAX_WIDTH:
            ratio = MAX_WIDTH / width_hwp
            width_hwp = MAX_WIDTH
            height_hwp = int(height_hwp * ratio)

        # Generate binary ID
        binary_item_id = f"img_{int(time.time() * 1000)}_{random.randint(0, 1000000)}"
        ext = 'png'
        lower = target_url.lower()
        if lower.endswith('.jpg') or lower.endswith('.jpeg'):
            ext = 'jpg'
        elif lower.endswith('.gif'):
            ext = 'gif'
        elif lower.endswith('.bmp'):
            ext = 'bmp'
        elif lower.endswith('.svg'):
            ext = 'png'  # SVG will be noted but not converted

        self.images.append({
            'id': binary_item_id,
            'path': target_url,
            'resolved_path': image_path,
            'ext': ext,
        })

        # Generate pic XML
        pic_id = _unique_id()
        inst_id = str(random.randint(10000000, 99999999))
        w, h = width_hwp, height_hwp

        return (
            f'<hp:run charPrIDRef="{char_pr_id}">'
            f'<hp:pic id="{pic_id}" zOrder="0" numberingType="NONE"'
            f' textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0"'
            f' dropcapstyle="None" href="" groupLevel="0"'
            f' instid="{inst_id}" reverse="0">'
            f'<hp:offset x="0" y="0"/>'
            f'<hp:orgSz width="{w}" height="{h}"/>'
            f'<hp:curSz width="{w}" height="{h}"/>'
            f'<hp:flip horizontal="0" vertical="0"/>'
            f'<hp:rotationInfo angle="0" centerX="0" centerY="0"'
            f' rotateimage="1"/>'
            f'<hp:renderingInfo>'
            f'<hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
            f'<hc:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
            f'<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
            f'</hp:renderingInfo>'
            f'<hc:img binaryItemIDRef="{binary_item_id}" bright="0"'
            f' contrast="0" effect="REAL_PIC" alpha="0"/>'
            f'<hp:imgRect>'
            f'<hc:pt0 x="0" y="0"/><hc:pt1 x="{w}" y="0"/>'
            f'<hc:pt2 x="{w}" y="{h}"/><hc:pt3 x="0" y="{h}"/>'
            f'</hp:imgRect>'
            f'<hp:imgClip left="0" right="0" top="0" bottom="0"/>'
            f'<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
            f'<hp:imgDim dimwidth="0" dimheight="0"/>'
            f'<hp:effects/>'
            f'<hp:sz width="{w}" widthRelTo="ABSOLUTE"'
            f' height="{h}" heightRelTo="ABSOLUTE" protect="0"/>'
            f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1"'
            f' allowOverlap="1" holdAnchorAndSO="0" vertRelTo="PARA"'
            f' horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT"'
            f' vertOffset="0" horzOffset="0"/>'
            f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
            f'<hp:shapeComment/>'
            f'</hp:pic>'
            f'</hp:run>'
        )

    def _resolve_image_path(self, target_url):
        """Resolve image path relative to input directory."""
        if os.path.isabs(target_url) and os.path.exists(target_url):
            return target_url

        # Try relative to input_dir
        candidate = os.path.join(self.input_dir, target_url)
        if os.path.exists(candidate):
            return candidate

        # Try CWD
        if os.path.exists(target_url):
            return os.path.abspath(target_url)

        return None

    @staticmethod
    def _parse_dimension(val_str):
        """Parse dimension string (e.g., '300px', '5cm') to HWPUNIT."""
        if not val_str:
            return None
        s = val_str.lower().strip()
        match = re.match(r'^([0-9.]+)([a-z%]+)?$', s)
        if not match:
            return None
        val = float(match.group(1))
        unit = match.group(2)
        LUNIT_PER_MM = 283.465

        if not unit or unit == 'px':
            mm_val = val * (25.4 / 96.0)
        elif unit == 'in':
            mm_val = val * 25.4
        elif unit == 'cm':
            mm_val = val * 10.0
        elif unit == 'mm':
            mm_val = val
        elif unit == 'pt':
            mm_val = val * (25.4 / 72.0)
        elif unit == '%':
            mm_val = val * 1.5  # % of ~150mm page width
        else:
            mm_val = val * (25.4 / 96.0)

        return int(mm_val * LUNIT_PER_MM)

    # ── Section XML assembly ──────────────────────────────────────────────

    def _build_section_xml(self, body_xml):
        """Build section0.xml from template + generated body."""
        original = self.section0_raw

        sec_tag_start = original.index('<hs:sec')
        sec_tag_end = original.index('>', sec_tag_start) + 1
        xml_header_and_open = original[:sec_tag_end]

        # Extract the first paragraph (contains page setup / secPr)
        first_p_start = original.index('<hp:p ')
        first_p_end = original.index('</hp:p>') + len('</hp:p>')
        first_paragraph = original[first_p_start:first_p_end]

        return (
            xml_header_and_open
            + first_paragraph
            + '\n'
            + body_xml
            + '\n</hs:sec>'
        )

    # ── Header.xml update ─────────────────────────────────────────────────

    def _update_header_xml(self):
        """Update header.xml with charPr, borderFill, fonts, spacing."""
        if self.use_reference and self.header_root is not None:
            return self._update_reference_header()
        else:
            return self._update_builtin_header()

    def _update_reference_header(self):
        """Serialize modified ElementTree for reference-doc mode."""
        root = self.header_root

        # Update itemCnt values
        for tag_name, child_tag in [
            ('charProperties', 'charPr'),
            ('paraProperties', 'paraPr'),
            ('numberings', 'numbering'),
            ('borderFills', 'borderFill'),
        ]:
            parent = root.find(f'.//hh:{tag_name}', NS)
            if parent is not None:
                count = len(parent.findall(f'hh:{child_tag}', NS))
                parent.set('itemCnt', str(count))

        return ET.tostring(root, encoding='unicode')

    def _update_builtin_header(self):
        """Update header.xml for built-in template mode."""
        header_xml = self.header_xml_raw

        # 0. Replace fontface blocks
        header_xml = re.sub(
            r'<hh:fontface lang="(\w+)"[^>]*>.*?</hh:fontface>',
            self._replace_fontface_block,
            header_xml,
            flags=re.DOTALL,
        )

        # 1. Add heading charPr entries
        new_charpr = ''
        for cpr_id, height, bold, font_ref in HEADING_CHAR_PROPS:
            new_charpr += self._make_charpr_xml(cpr_id, height, bold, font_ref)

        # Code block charPr
        new_charpr += self._make_charpr_xml(
            CODE_CHAR_PR_ID, 1000, False, CODE_FONT_REF)

        # Dynamic format charPr entries (from inline processing)
        for (base_id_str, formats_frozen), new_id_str in self.char_pr_cache.items():
            new_id = int(new_id_str)
            base_id = int(base_id_str) if base_id_str.isdigit() else 0
            base_height = CHAR_HEIGHT_MAP.get(base_id, 1000)
            base_font_ref = CODE_FONT_REF if base_id == CODE_CHAR_PR_ID else 0
            bold = 'BOLD' in formats_frozen or base_id in (7, 8)
            italic = 'ITALIC' in formats_frozen
            underline = 'UNDERLINE' in formats_frozen
            strikeout = 'STRIKEOUT' in formats_frozen
            color = '#0000FF' if 'COLOR_BLUE' in formats_frozen else None
            new_charpr += self._make_charpr_xml(
                new_id, base_height, bold, base_font_ref,
                italic=italic, underline=underline,
                strikeout=strikeout, text_color=color)

        marker = '</hh:charProperties>'
        header_xml = header_xml.replace(marker, new_charpr + marker)

        # Update charProperties itemCnt
        total_charpr = 7 + len(HEADING_CHAR_PROPS) + 1 + len(self.char_pr_cache)
        header_xml = re.sub(
            r'(<hh:charProperties\s+itemCnt=")\d+(")',
            rf'\g<1>{total_charpr}\2', header_xml)

        # 2. Add table borderFill
        bf_marker = '</hh:borderFillList>'
        header_xml = header_xml.replace(
            bf_marker, self._make_table_borderfill_xml() + bf_marker)
        header_xml = re.sub(
            r'(<hh:borderFillList\s+itemCnt=")\d+(")',
            r'\g<1>3\2', header_xml)

        # 3. Heading spacing
        for para_pr_id, prev_val in HEADING_SPACING.items():
            pattern = (
                rf'(<hh:paraPr\s+id="{para_pr_id}"[^>]*>.*?)'
                rf'(<hc:prev\s+value=")0(")'
            )
            header_xml = re.sub(
                pattern, rf'\g<1>\g<2>{prev_val}\3',
                header_xml, flags=re.DOTALL)

        return header_xml

    @staticmethod
    def _replace_fontface_block(match):
        """Replace font entries within a fontface block per language."""
        lang = match.group(1)
        primary_font = LANG_FONT_MAP.get(lang, 'NimbusSanL')
        return (
            f'<hh:fontface lang="{lang}" fontCnt="3">'
            + PandocHwpxConverter._make_font_xml(0, primary_font)
            + PandocHwpxConverter._make_font_xml(1, primary_font)
            + PandocHwpxConverter._make_font_xml(2, 'D2Coding')
            + '</hh:fontface>'
        )

    @staticmethod
    def _make_font_xml(font_id, face_name):
        """Build a single <hh:font> entry."""
        return (
            f'<hh:font id="{font_id}" face="{face_name}" type="TTF"'
            f' isEmbedded="0">'
            f'<hh:typeInfo familyType="FCAT_GOTHIC" weight="6"'
            f' proportion="4" contrast="0" strokeVariation="1"'
            f' armStyle="1" letterform="1" midline="1" xHeight="1"/>'
            f'</hh:font>'
        )

    @staticmethod
    def _make_charpr_xml(cpr_id, height, bold=False, font_ref=0,
                         italic=False, underline=False, strikeout=False,
                         text_color=None):
        """Build a <hh:charPr> XML string."""
        bold_attr = ' bold="1"' if bold else ''
        italic_attr = ' italic="1"' if italic else ''
        color = text_color or '#000000'
        ul_type = 'BOTTOM' if underline else 'NONE'
        ul_color = text_color or '#000000'
        so_shape = 'SOLID' if strikeout else 'NONE'
        return (
            f'<hh:charPr id="{cpr_id}" height="{height}"'
            f' textColor="{color}" shadeColor="none"'
            f' useFontSpace="0" useKerning="0" symMark="NONE"'
            f' borderFillIDRef="2"{bold_attr}{italic_attr}>'
            f'<hh:fontRef hangul="{font_ref}" latin="{font_ref}"'
            f' hanja="{font_ref}" japanese="{font_ref}"'
            f' other="{font_ref}" symbol="{font_ref}" user="{font_ref}"/>'
            f'<hh:ratio hangul="100" latin="100" hanja="100"'
            f' japanese="100" other="100" symbol="100" user="100"/>'
            f'<hh:spacing hangul="0" latin="0" hanja="0"'
            f' japanese="0" other="0" symbol="0" user="0"/>'
            f'<hh:relSz hangul="100" latin="100" hanja="100"'
            f' japanese="100" other="100" symbol="100" user="100"/>'
            f'<hh:offset hangul="0" latin="0" hanja="0"'
            f' japanese="0" other="0" symbol="0" user="0"/>'
            f'<hh:underline type="{ul_type}" shape="SOLID"'
            f' color="{ul_color}"/>'
            f'<hh:strikeout shape="{so_shape}" color="#000000"/>'
            f'<hh:outline type="NONE"/>'
            f'<hh:shadow type="NONE" color="#C0C0C0"'
            f' offsetX="10" offsetY="10"/>'
            f'</hh:charPr>'
        )

    @staticmethod
    def _make_table_borderfill_xml():
        """Build a borderFill with solid borders for table cells."""
        return (
            f'<hh:borderFill id="{TABLE_BORDER_FILL_ID}" threeD="0"'
            f' shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
            f'<hh:slash type="NONE" Crooked="0" isCounter="0"/>'
            f'<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
            f'<hh:leftBorder type="SOLID" width="0.12 mm"'
            f' color="#000000"/>'
            f'<hh:rightBorder type="SOLID" width="0.12 mm"'
            f' color="#000000"/>'
            f'<hh:topBorder type="SOLID" width="0.12 mm"'
            f' color="#000000"/>'
            f'<hh:bottomBorder type="SOLID" width="0.12 mm"'
            f' color="#000000"/>'
            f'<hh:diagonal type="NONE" width="0.12 mm"'
            f' color="#000000"/>'
            f'</hh:borderFill>'
        )

    # ── Content.hpf update ────────────────────────────────────────────────

    def _update_content_hpf(self):
        """Update metadata and image manifest in content.hpf."""
        hpf_xml = self.hpf_xml_raw
        now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        if self.title:
            hpf_xml = re.sub(
                r'(<opf:title)(?:/>|>(.*?)</opf:title>)',
                rf'\1>{xml_escape(self.title)}</opf:title>',
                hpf_xml)

        if self.author:
            safe_author = xml_escape(self.author)
            hpf_xml = re.sub(
                r'(<opf:meta name="creator" content="text")(?:/>|>(.*?)</opf:meta>)',
                rf'\1>{safe_author}</opf:meta>',
                hpf_xml)
            hpf_xml = re.sub(
                r'(<opf:meta name="lastsaveby" content="text")(?:/>|>(.*?)</opf:meta>)',
                rf'\1>{safe_author}</opf:meta>',
                hpf_xml)

        hpf_xml = re.sub(
            r'(<opf:meta name="ModifiedDate" content="text")(?:/>|>(.*?)</opf:meta>)',
            rf'\1>{now}</opf:meta>',
            hpf_xml)

        if self.date_str:
            hpf_xml = re.sub(
                r'(<opf:meta name="date" content="text")(?:/>|>(.*?)</opf:meta>)',
                rf'\1>{xml_escape(self.date_str)}</opf:meta>',
                hpf_xml)

        # Add image items to manifest
        if self.images:
            new_items = []
            for img in self.images:
                i_id = img['id']
                i_ext = img['ext']
                mime = 'image/png'
                if i_ext == 'jpg':
                    mime = 'image/jpeg'
                elif i_ext == 'gif':
                    mime = 'image/gif'
                new_items.append(
                    f'<opf:item id="{i_id}" href="BinData/{i_id}.{i_ext}"'
                    f' media-type="{mime}" isEmbeded="1"/>')

            insert_pos = hpf_xml.find('</opf:manifest>')
            if insert_pos != -1:
                hpf_xml = (hpf_xml[:insert_pos]
                           + '\n'.join(new_items) + '\n'
                           + hpf_xml[insert_pos:])

        return hpf_xml

    # ── Write final HWPX ──────────────────────────────────────────────────

    def _write_hwpx(self, output_path, section_xml, header_xml, hpf_xml):
        """Assemble final HWPX ZIP file."""
        with tempfile.NamedTemporaryFile(suffix='.hwpx', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with zipfile.ZipFile(self.template_path, 'r') as src_zip:
                with zipfile.ZipFile(tmp_path, 'w',
                                     zipfile.ZIP_DEFLATED) as dst_zip:
                    for item in src_zip.infolist():
                        if item.filename == 'Contents/section0.xml':
                            dst_zip.writestr(item,
                                             section_xml.encode('utf-8'))
                        elif item.filename == 'Contents/header.xml':
                            dst_zip.writestr(item,
                                             header_xml.encode('utf-8'))
                        elif item.filename == 'Contents/content.hpf':
                            dst_zip.writestr(item,
                                             hpf_xml.encode('utf-8'))
                        else:
                            dst_zip.writestr(item,
                                             src_zip.read(item.filename))

                    # Embed images
                    for img in self.images:
                        resolved = img.get('resolved_path')
                        if resolved and os.path.exists(resolved):
                            bindata_name = f"BinData/{img['id']}.{img['ext']}"
                            dst_zip.write(resolved, bindata_name)
                        else:
                            print(f"[Warn] Image not found: {img['path']}",
                                  file=sys.stderr)

            shutil.move(tmp_path, output_path)
            print(f"HWPX written to {output_path}", file=sys.stderr)

        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

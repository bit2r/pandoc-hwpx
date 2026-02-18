"""Linesegarray computation for HWPX layout cache.

Ported from quarto-hwpx hwpx_writer.py (lines 172-226).

HWP Mac requires linesegarray in each <hp:p> for proper layout rendering.
Without it, the document may display as blank or with incorrect line breaks.
"""

# Layout constants
PAGE_TEXT_WIDTH = 42520   # page width minus margins (A4)
CHAR_HEIGHT_NORMAL = 1000  # 10pt in HWPUNIT
LINE_SPACING_PCT = 160     # 160% line spacing


def compute_lineseg_xml(
    text: str,
    char_height: int = CHAR_HEIGHT_NORMAL,
    line_spacing_pct: int = LINE_SPACING_PCT,
    horzsize: int = PAGE_TEXT_WIDTH,
) -> str:
    """Build <hp:linesegarray> XML with multi-line entries based on text length.

    Uses character-width estimation:
    - CJK characters (U+2000+): full width = char_height
    - Latin/ASCII characters: half width = char_height // 2

    Args:
        text: The paragraph text content.
        char_height: Character height in HWPUNIT.
        line_spacing_pct: Line spacing percentage (e.g., 160 = 160%).
        horzsize: Horizontal text area width in HWPUNIT.

    Returns:
        XML string for <hp:linesegarray> element.
    """
    vertsize = char_height
    spacing = int(char_height * (line_spacing_pct - 100) / 100)
    line_height = vertsize + spacing
    baseline = int(char_height * 0.85)

    if not text:
        return (
            f'<hp:linesegarray>'
            f'<hp:lineseg textpos="0" vertpos="0" vertsize="{vertsize}"'
            f' textheight="{vertsize}" baseline="{baseline}"'
            f' spacing="{spacing}" horzpos="0" horzsize="{horzsize}"'
            f' flags="393216"/>'
            f'</hp:linesegarray>'
        )

    line_starts = [0]
    current_width = 0

    for i, ch in enumerate(text):
        if ord(ch) > 0x2000:
            current_width += char_height
        else:
            current_width += char_height // 2

        if current_width > horzsize and (i + 1) < len(text):
            line_starts.append(i + 1)
            current_width = 0

    num_lines = len(line_starts)

    parts = ['<hp:linesegarray>']
    for idx, textpos in enumerate(line_starts):
        vertpos = idx * line_height
        if num_lines == 1:
            flags = 393216   # 0x60000: first + last
        elif idx == 0:
            flags = 131072   # 0x20000: first only
        elif idx == num_lines - 1:
            flags = 262144   # 0x40000: last only
        else:
            flags = 0

        parts.append(
            f'<hp:lineseg textpos="{textpos}" vertpos="{vertpos}"'
            f' vertsize="{vertsize}" textheight="{vertsize}"'
            f' baseline="{baseline}" spacing="{spacing}"'
            f' horzpos="0" horzsize="{horzsize}" flags="{flags}"/>'
        )
    parts.append('</hp:linesegarray>')

    return ''.join(parts)

"""LaTeX to HWP equation script converter.

Ported from quarto-hwpx hwpx_writer.py (lines 81-100, 245-265).
"""

import re
from xml.sax.saxutils import escape as xml_escape


def latex_to_hwp_script(latex: str) -> str:
    """Convert LaTeX math to HWP equation script.

    Transforms LaTeX notation to the native HWP equation format used
    by the Hancom Office equation editor.
    """
    s = latex.strip().strip('$')
    # \frac{a}{b} -> {a} over {b}
    s = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'{\1} over {\2}', s)
    # \sum_{x}^{y} -> sum from{x} to{y}
    s = re.sub(r'\\sum_\{([^}]*)\}\^\{([^}]*)\}', r'sum from{\1} to{\2}', s)
    # \int_{x}^{y} -> int from{x} to{y}
    s = re.sub(r'\\int_\{([^}]*)\}\^\{([^}]*)\}', r'int from{\1} to{\2}', s)
    # \sqrt{x} -> sqrt{x}
    s = re.sub(r'\\sqrt\{([^}]*)\}', r'sqrt{\1}', s)
    # \left( \right) -> left( right)
    s = s.replace(r'\left(', 'left(').replace(r'\right)', 'right)')
    s = s.replace(r'\left[', 'left[').replace(r'\right]', 'right]')
    s = s.replace(r'\left\{', 'left lbrace ').replace(r'\right\}', 'right rbrace ')
    # Specific symbol replacements
    for cmd, repl in [
        (r'\geq', '>='), (r'\leq', '<='), (r'\neq', '<>'),
        (r'\times', 'times'), (r'\cdot', 'cdot'), (r'\cdots', 'cdots'),
        (r'\ldots', 'ldots'), (r'\infty', 'inf'), (r'\pm', '+-'),
        (r'\mp', '-+'), (r'\approx', 'approx'), (r'\equiv', 'equiv'),
        (r'\partial', 'partial'), (r'\nabla', 'nabla'),
        (r'\rightarrow', 'rightarrow'), (r'\leftarrow', 'leftarrow'),
        (r'\Rightarrow', 'Rightarrow'), (r'\Leftarrow', 'Leftarrow'),
    ]:
        s = s.replace(cmd, repl)
    # Subscript/superscript: _ -> _ and ^ -> ^ (preserved as-is in HWP script)
    # \hat{x} -> hat{x}, \bar{x} -> bar{x}, \vec{x} -> vec{x}
    # Remaining \command -> command (Greek letters etc.)
    s = re.sub(r'\\([a-zA-Z]+)', r'\1', s)
    return s


def make_equation_xml(latex_str: str) -> str:
    """Build <hp:equation> XML element from LaTeX source.

    Returns the XML string for embedding within an <hp:run> element.
    """
    script = latex_to_hwp_script(latex_str)
    safe_script = xml_escape(script)
    return (
        '<hp:equation version="eqEdit" baseLine="0"'
        ' textColor="#000000" baseUnit="1000" lineMode="0" font="">'
        f'<hp:script>{safe_script}</hp:script>'
        '</hp:equation>'
    )

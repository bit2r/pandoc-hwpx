"""CLI entry point for pandoc-hwpx.

Usage:
    pandoc input.qmd -t json | python -m pandoc_hwpx -o output.hwpx
    pandoc input.md -t json | python -m pandoc_hwpx -o output.hwpx --input-dir /path/to/input
    pandoc input.md -t json | python -m pandoc_hwpx -o output.hwpx --reference-doc ref.hwpx

Or from a Lua filter:
    pandoc.pipe('python3', {'-m', 'pandoc_hwpx', '-o', path, '--input-dir', dir}, json_ast)
"""

import argparse
import json
import os
import sys

from .converter import PandocHwpxConverter


def main():
    parser = argparse.ArgumentParser(
        description='Convert Pandoc JSON AST to HWPX document')
    parser.add_argument(
        '-o', '--output', required=True,
        help='Output .hwpx file path')
    parser.add_argument(
        '--input-dir', default=None,
        help='Base directory for resolving relative image paths')
    parser.add_argument(
        '--reference-doc', default=None,
        help='Reference .hwpx document for style/page setup inheritance')
    parser.add_argument(
        '--toc', action='store_true', default=False,
        help='Generate table of contents')
    args = parser.parse_args()

    # Read JSON AST from stdin
    json_input = sys.stdin.read()
    if not json_input.strip():
        print("Error: No JSON AST received on stdin", file=sys.stderr)
        sys.exit(1)

    try:
        ast = json.loads(json_input)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON AST: {e}", file=sys.stderr)
        sys.exit(1)

    # Resolve input directory
    input_dir = args.input_dir
    if input_dir is None:
        input_dir = os.getcwd()

    # Run converter
    converter = PandocHwpxConverter(
        json_ast=ast,
        reference_path=args.reference_doc,
        input_dir=input_dir,
        toc=args.toc,
    )
    converter.convert(args.output)


if __name__ == '__main__':
    main()

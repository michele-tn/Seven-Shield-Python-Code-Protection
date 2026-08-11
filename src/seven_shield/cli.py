"""Command-line interface for Seven Shield."""

from __future__ import annotations

import argparse
from pathlib import Path

from seven_shield.obfuscator import ObfuscationOptions, Obfuscator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Obfuscate a Python source file locally.")
    parser.add_argument("input", type=Path, help="input .py file")
    parser.add_argument("-o", "--output", type=Path, help="output file (default: <name>.protected.py)")
    parser.add_argument("--seed", type=int, help="repeatable output seed")
    for name in ("rename", "encrypt", "flatten", "hide-builtins", "hide-imports", "hide-attrs", "junk-code"):
        parser.add_argument(f"--no-{name}", action="store_true", help=f"disable {name}")
    return parser


def main() -> None:
    """Run the command-line application."""
    args = _parser().parse_args()
    destination = args.output or args.input.with_name(f"{args.input.stem}.protected.py")
    options = ObfuscationOptions(
        rename=not args.no_rename,
        encrypt=not args.no_encrypt,
        flatten=not args.no_flatten,
        hide_builtins=not args.no_hide_builtins,
        hide_imports=not args.no_hide_imports,
        hide_attrs=not args.no_hide_attrs,
        junk_code=not args.no_junk_code,
        seed=args.seed,
    )
    source = args.input.read_text(encoding="utf-8")
    destination.write_text(Obfuscator().obfuscate(source, options), encoding="utf-8")
    print(f"Protected file written to {destination}")


if __name__ == "__main__":
    main()


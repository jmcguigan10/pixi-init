#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def patch_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing file to patch: {path}")

    text = path.read_text()

    already_patched = re.search(
        r"bool\s+operator\s*\(\s*\)\s*\("
        r"\s*const\s+Node::Ptr\s*&\s*first\s*,"
        r"\s*const\s+Node::Ptr\s*&\s*second\s*"
        r"\)\s+const\s*[\{\n]",
        text,
    )

    if already_patched:
        print(f"Patch already applied: {path}")
        return

    pattern = re.compile(
        r"(bool\s+operator\s*\(\s*\)\s*\("
        r"\s*const\s+Node::Ptr\s*&\s*first\s*,"
        r"\s*const\s+Node::Ptr\s*&\s*second\s*"
        r"\))(\s*(?:\n\s*)?\{)",
        re.MULTILINE,
    )

    patched, count = pattern.subn(r"\1 const\2", text, count=1)

    if count != 1:
        if "uniqueLessThanCompareFn" in text:
            raise SystemExit(
                "Found uniqueLessThanCompareFn, but not the expected operator() signature. "
                "Inspect include/xqilla/ast/XQDocumentOrder.hpp manually."
            )

        raise SystemExit(
            "Could not find the XQilla comparator signature to patch."
        )

    path.write_text(patched)
    print(f"Applied GCC/libstdc++ comparator patch: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source_root",
        nargs="?",
        default=".",
        help="Path to XQilla source root.",
    )
    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    header = source_root / "include" / "xqilla" / "ast" / "XQDocumentOrder.hpp"

    patch_file(header)


if __name__ == "__main__":
    main()
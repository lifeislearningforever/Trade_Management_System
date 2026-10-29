#!/usr/bin/env python3
"""
Remove redundant `database='gmp_cis'` keyword arguments from execute_query /
execute_write / execute_write_async call sites.

Omitting `database=` already resolves to settings.IMPALA_CONFIG['DATABASE']
via the `db_name = database or config['DATABASE']` fallback in
core/repositories/impala_connection.py -- these explicit literals are
redundant and (as of the database.txt change) would silently ignore any
override if left in place.

Handles two call-site shapes, both confirmed to be the only ones present:
  1. Same line, preceded by another argument:
       foo(query, database='gmp_cis')          -> foo(query)
  2. On its own line (multi-line call):
       foo(
           query,
           database='gmp_cis'
       )                                        -> foo(\n    query,\n)
Does NOT touch commented-out lines, or `self.database = 'gmp_cis'` /
`DB = 'gmp_cis'` style constant assignments -- those are handled separately
(see docs/DATABASE_CONFIG_NORMALIZATION.md).

Usage:
    python3 scripts/remove_redundant_database_kwarg.py .            # dry run
    python3 scripts/remove_redundant_database_kwarg.py . --apply
"""
import re
import sys
from pathlib import Path

SAME_LINE_RE = re.compile(r",\s*database\s*=\s*['\"]gmp_cis['\"]")
STANDALONE_LINE_RE = re.compile(r"^\s*database\s*=\s*['\"]gmp_cis['\"]\s*,?\s*$")


def process_file(path: Path, apply: bool):
    text = path.read_text()
    lines = text.split("\n")
    out_lines = []
    changed = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            out_lines.append(line)
            continue
        if STANDALONE_LINE_RE.match(line):
            changed += 1
            continue  # drop the whole line
        new_line, n = SAME_LINE_RE.subn("", line)
        if n:
            changed += n
        out_lines.append(new_line)

    if not changed:
        print(f"  SKIP (no match): {path}")
        return

    new_text = "\n".join(out_lines)
    if apply:
        path.write_text(new_text)
        print(f"  APPLIED ({changed} removed): {path}")
    else:
        print(f"  WOULD CHANGE ({changed} removed): {path}")


def main():
    apply = "--apply" in sys.argv
    root_arg = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(root_arg[0]) if root_arg else Path.cwd()

    print(f"Root: {root}")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN (pass --apply to write changes)'}\n")

    pattern = re.compile(r"database\s*=\s*['\"]gmp_cis['\"]")
    skip_if_contains = re.compile(r"self\.database\s*=\s*['\"]gmp_cis['\"]")

    self_path = Path(__file__).resolve()
    for path in sorted(root.rglob("*.py")):
        if path.resolve() == self_path:
            continue
        text = path.read_text(errors="ignore")
        if not pattern.search(text):
            continue
        if skip_if_contains.search(text) and not SAME_LINE_RE.search(text) and not any(
            STANDALONE_LINE_RE.match(l) for l in text.split("\n")
        ):
            continue  # pure self.database = 'gmp_cis' file, nothing for this script to do
        process_file(path, apply)

    print("\nDone.")


if __name__ == "__main__":
    main()

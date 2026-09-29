#!/usr/bin/env python3
"""
CIS Trade Hive — Kudu Setup Runner
===================================
Substitutes {{KUDU_MASTERS}} in the consolidated DDL file and runs it
against Impala.  Works for local Docker and Cloudera CML (or any env).

Usage:
  # Local Docker (default)
  python sql/kudu_setup/run_setup.py --env docker

  # Cloudera CML (auto-detects from .env / environment variables)
  python sql/kudu_setup/run_setup.py --env cml

  # Explicit Kudu master override
  python sql/kudu_setup/run_setup.py --kudu-masters host1:7051,host2:7051

  # Dry-run: print substituted SQL without executing
  python sql/kudu_setup/run_setup.py --env docker --dry-run

  # Point at a different Impala host
  python sql/kudu_setup/run_setup.py --env docker --impala-host 192.168.1.10

Options:
  --env            docker | cml | prod  (selects preset kudu-masters)
  --kudu-masters   Explicit override: comma-separated host:port list
  --impala-host    Impala coordinator hostname  (default: localhost)
  --impala-port    Impala port                  (default: 21050)
  --database       Target database              (default: gmp_cis)
  --ddl-file       Path to DDL SQL file         (default: same dir as this script)
  --dry-run        Print SQL to stdout, do not execute
  --use-shell      Use impala-shell subprocess instead of PyHive (useful for
                   environments where PyHive auth is tricky)
  --verbose        Print each statement before running

Environment presets for --env:
  docker  → localhost:7051
  cml     → reads KUDU_MASTERS env var, falls back to IMPALA_HOST:7051
  prod    → same as cml
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------
PRESETS = {
    "docker": "localhost:7051",
    "cml":    None,   # read from env
    "prod":   None,   # read from env
}

DDL_FILENAME = "01_create_all_tables.sql"
PLACEHOLDER  = "{{KUDU_MASTERS}}"
DEFAULT_DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')


def resolve_kudu_masters(args) -> str:
    """Return the kudu.master_addresses string to substitute."""
    if args.kudu_masters:
        return args.kudu_masters

    env = (args.env or "docker").lower()
    if env == "docker":
        return PRESETS["docker"]

    # CML / prod: try env var KUDU_MASTERS first, then derive from IMPALA_HOST
    kudu_masters = os.environ.get("KUDU_MASTERS", "").strip()
    if kudu_masters:
        return kudu_masters

    impala_host = os.environ.get("IMPALA_HOST", "").strip()
    if impala_host:
        return f"{impala_host}:7051"

    print("[ERROR] Cannot determine kudu.master_addresses.")
    print("  Set --kudu-masters explicitly, or set KUDU_MASTERS / IMPALA_HOST env var.")
    sys.exit(1)


def resolve_impala_host(args) -> str:
    if args.impala_host:
        return args.impala_host
    env = (args.env or "docker").lower()
    if env == "docker":
        return "localhost"
    return os.environ.get("IMPALA_HOST", "localhost")


def resolve_impala_port(args) -> int:
    if args.impala_port:
        return int(args.impala_port)
    return int(os.environ.get("IMPALA_PORT", "21050"))


def build_sql(ddl_path: Path, kudu_masters: str) -> str:
    """Read DDL file and substitute the placeholder."""
    raw = ddl_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in raw:
        print(f"[WARN] Placeholder '{PLACEHOLDER}' not found in {ddl_path}")
    return raw.replace(PLACEHOLDER, kudu_masters)


def run_via_shell(sql: str, impala_host: str, impala_port: int, verbose: bool):
    """Execute SQL using the impala-shell subprocess."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sql", delete=False, encoding="utf-8"
    ) as f:
        f.write(sql)
        tmp_path = f.name

    cmd = [
        "impala-shell",
        "-i", f"{impala_host}:{impala_port}",
        "--var=KUDU_MASTERS=substituted",
        "-f", tmp_path,
    ]
    if verbose:
        print(f"[CMD] {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, check=True, text=True,
                                capture_output=(not verbose))
        if not verbose and result.stdout:
            print(result.stdout)
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] impala-shell exited with code {exc.returncode}")
        if exc.stderr:
            print(exc.stderr)
        sys.exit(exc.returncode)
    finally:
        os.unlink(tmp_path)


def run_via_pyhive(sql: str, impala_host: str, impala_port: int,
                   database: str, verbose: bool):
    """Execute SQL using PyHive (ImpalaDB/Impala connection)."""
    try:
        from impala.dbapi import connect
    except ImportError:
        print("[ERROR] impyla not installed.  Try: pip install impyla")
        print("  Or use --use-shell to run via impala-shell instead.")
        sys.exit(1)

    auth_mechanism = os.environ.get("IMPALA_AUTH", "NOSASL")

    print(f"[INFO] Connecting to Impala at {impala_host}:{impala_port} "
          f"(auth={auth_mechanism})")
    conn = connect(
        host=impala_host,
        port=impala_port,
        auth_mechanism=auth_mechanism,
        database=database,
    )
    cursor = conn.cursor()

    # Split on semicolons, skip empty/comment-only chunks
    statements = [s.strip() for s in sql.split(";")]
    total = len([s for s in statements if s and not s.startswith("--")])
    executed = 0

    for stmt in statements:
        # Skip blank and pure-comment statements
        if not stmt or all(
            line.strip().startswith("--") or line.strip() == ""
            for line in stmt.splitlines()
        ):
            continue

        if verbose:
            first_line = stmt.strip().splitlines()[0][:80]
            print(f"  [SQL] {first_line}...")

        try:
            cursor.execute(stmt)
            executed += 1
        except Exception as exc:
            first_line = stmt.strip().splitlines()[0][:120]
            print(f"[ERROR] Statement failed: {first_line}")
            print(f"        {exc}")
            # Continue on non-fatal errors (table already exists, etc.)

    cursor.close()
    conn.close()
    print(f"[DONE] {executed}/{total} statements executed.")


def main():
    parser = argparse.ArgumentParser(
        description="CIS Trade Hive Kudu setup runner"
    )
    parser.add_argument(
        "--env",
        choices=["docker", "cml", "prod"],
        default="docker",
        help="Environment preset (default: docker)",
    )
    parser.add_argument(
        "--kudu-masters",
        metavar="HOST:PORT[,...]",
        help="Explicit kudu.master_addresses override",
    )
    parser.add_argument(
        "--impala-host",
        metavar="HOST",
        help="Impala coordinator host (default: localhost for docker, "
             "IMPALA_HOST env var for cml)",
    )
    parser.add_argument(
        "--impala-port",
        metavar="PORT",
        type=int,
        help="Impala port (default: 21050)",
    )
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        help=f"Target database (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--ddl-file",
        metavar="PATH",
        help=f"Path to DDL file (default: <script_dir>/{DDL_FILENAME})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print substituted SQL to stdout without executing",
    )
    parser.add_argument(
        "--use-shell",
        action="store_true",
        help="Execute via impala-shell subprocess instead of PyHive",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each statement before executing",
    )

    args = parser.parse_args()

    # Resolve paths
    script_dir = Path(__file__).parent
    ddl_path = Path(args.ddl_file) if args.ddl_file else script_dir / DDL_FILENAME

    if not ddl_path.exists():
        print(f"[ERROR] DDL file not found: {ddl_path}")
        sys.exit(1)

    kudu_masters = resolve_kudu_masters(args)
    impala_host  = resolve_impala_host(args)
    impala_port  = resolve_impala_port(args)

    print(f"[CONFIG] env           = {args.env}")
    print(f"[CONFIG] kudu_masters  = {kudu_masters}")
    print(f"[CONFIG] impala_host   = {impala_host}:{impala_port}")
    print(f"[CONFIG] database      = {args.database}")
    print(f"[CONFIG] ddl_file      = {ddl_path}")

    sql = build_sql(ddl_path, kudu_masters)

    if args.dry_run:
        print("\n" + "=" * 72)
        print("DRY RUN — substituted SQL (not executed):")
        print("=" * 72)
        print(sql)
        return

    if args.use_shell:
        run_via_shell(sql, impala_host, impala_port, args.verbose)
    else:
        run_via_pyhive(sql, impala_host, impala_port,
                       args.database, args.verbose)


if __name__ == "__main__":
    main()

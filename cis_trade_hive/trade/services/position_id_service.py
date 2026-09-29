"""
Shared utilities for position identity across all writers:
  position_service, upload_service, refresh_positions, create_sod_snapshot.

position_id
-----------
Deterministic: abs(md5(portfolio|security_label|position_basis|position_date|src_system)) % 2^63

Same natural key always produces the same position_id regardless of which
writer creates it.  With the composite PK (position_id, position_type) on
cis_position, SOD/INT/EOD/CORR rows for the same natural key coexist as
separate rows — they share the same position_id and differ only by
position_type.  Re-running any writer for the same inputs is idempotent
via UPSERT on the composite PK.

position_basis values
---------------------
  TRADED   — position tracked on trade date  (was TRADE_DATE)
  SETTLED  — position tracked on settle date (was SETTLE_DATE)
"""

import hashlib


# Canonical position_basis values
TRADED  = 'TRADED'
SETTLED = 'SETTLED'
POSITION_BASIS_CHOICES = [TRADED, SETTLED]

# Human-readable labels for UI display
POSITION_BASIS_LABELS = {
    TRADED:  'Traded',
    SETTLED: 'Settled',
}


def position_id(
    portfolio: str,
    security_label: str,
    position_basis: str,
    position_date: str,
    src_system: str,
) -> int:
    """
    Deterministic position_id from natural key.

    Replicates Impala's fnv_hash(CONCAT_WS('|', ...)) semantics using MD5
    so Python writers produce the same id as Impala SQL writers.

    Returns a positive BIGINT-safe integer (< 2^63).
    """
    key = '|'.join([
        portfolio    or '',
        security_label or '',
        position_basis or '',
        position_date  or '',
        src_system   or '',
    ])
    digest = hashlib.md5(key.encode('utf-8')).hexdigest()
    return abs(int(digest, 16)) % (2 ** 63)


# Impala SQL expression for the same hash — use in UPSERT SELECT statements.
# Substitute {p}, {s}, {b}, {d}, {src} with escaped literal values.
POSITION_ID_SQL = (
    "ABS(CAST(fnv_hash(CONCAT_WS('|', "
    "COALESCE({p}, ''), COALESCE({s}, ''), COALESCE({b}, ''), "
    "COALESCE({d}, ''), COALESCE({src}, '')"
    ")) AS BIGINT))"
)


def position_id_sql_expr(
    portfolio_expr: str,
    security_expr: str,
    basis_expr: str,
    date_expr: str,
    src_expr: str,
) -> str:
    """
    Return the Impala SQL expression for position_id given column/literal
    expressions for each component.

    Example:
        position_id_sql_expr("s.portfolio", "s.security_label",
                             "s.position_basis", "CAST(s.reporting_date AS STRING)",
                             "s.src_system")
    """
    return (
        f"ABS(CAST(fnv_hash(CONCAT_WS('|', "
        f"COALESCE({portfolio_expr}, ''), "
        f"COALESCE({security_expr}, ''), "
        f"COALESCE({basis_expr}, ''), "
        f"COALESCE({date_expr}, ''), "
        f"COALESCE({src_expr}, '')"
        f")) AS BIGINT))"
    )

#!/usr/bin/env python
"""
Standalone AVP (Average Price Position) verification script.

Unlike trade/tests/test_avp_live_scenarios.py (which reuses pre-existing
SIT/UAT reference portfolios/securities), this script is fully self-contained:
it creates its OWN throwaway portfolio, security, counterparty, and equity
price, books a sequence of BUY/SELL trades (both current-date and backdated)
through the real trade_create view — the same code path a user hits from the
UI — waits for the real async pipeline (event queue -> trade event worker ->
position queue -> position worker) to process them, then compares the
resulting cis_trade_position rows against an independent reference AVP
calculator implemented directly in this script (not calling position_service
at all) to verify production behaviour is actually correct.

Everything this script creates is deleted at the end (portfolio, security,
counterparty, equity price, trades, positions, queue rows) unless --keep is
passed.

Requirements:
  - Run from cis_trade_hive/ with the project venv active.
  - The Django app's Impala/Kudu connection must be reachable (same as any
    manage.py command) — local Docker Kudu, or point at SIT/UAT via the usual
    CIS_ENV / IMPALA_* env vars.
  - The Trade Event Worker + Position Worker must actually be running
    somewhere against the same database (e.g. the deployed app, or run them
    locally — see config/cml_app.py's start_trade_event_worker /
    start_position_worker). This script only submits trades and polls for
    results; it does not process the queue itself.

Usage:
    python scripts/avp_verification_script.py
    python scripts/avp_verification_script.py --keep     # skip cleanup, inspect DB after
    python scripts/avp_verification_script.py --cleanup-only RUN_ID   # delete a prior run's leftovers
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.conf import settings
from django.test import Client
from django.urls import reverse

from core.repositories.impala_connection import impala_manager
from trade.tests.avp_live_fixtures import (
    get_authenticated_client, ui_create_trade, get_latest_position,
    POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS,
)

DATABASE = settings.IMPALA_CONFIG['DATABASE']
AVP_PRECISION = Decimal('0.00000001')

RESULTS = {'pass': [], 'fail': []}


def check(label, actual, expected, tolerance=Decimal('0.00000001')):
    actual = Decimal(str(actual))
    expected = Decimal(str(expected))
    ok = abs(actual - expected) <= tolerance
    if ok:
        RESULTS['pass'].append(label)
        print(f"  PASS  {label}: {actual}")
    else:
        RESULTS['fail'].append((label, actual, expected))
        print(f"  FAIL  {label}: got {actual}, expected {expected}")
    return ok


# =============================================================================
# Independent reference AVP calculator — deliberately NOT calling
# position_service. Mirrors the documented formula (CLAUDE.md "AVP Formulas"):
#   BUY:  new_avg_cost = (old_total_cost + qty*price) / new_qty   (charges excluded)
#   SELL: avg_cost unchanged; realized_pnl += (price - avg_cost) * qty
# Running the same trades through this and comparing to what the real system
# produced is the actual correctness check — a shared bug in this script and
# position_service would still be caught by manual review of the PASS/FAIL
# math below, since expected values are also printed.
# =============================================================================

class ShadowPosition:
    def __init__(self):
        self.qty = Decimal('0')
        self.total_cost = Decimal('0')
        self.avg_cost = Decimal('0')
        self.realized_pnl = Decimal('0')

    def apply_buy(self, qty, price):
        trade_cost = qty * price
        self.total_cost += trade_cost
        self.qty += qty
        self.avg_cost = (self.total_cost / self.qty).quantize(AVP_PRECISION, rounding=ROUND_HALF_UP)

    def apply_sell(self, qty, price):
        if qty > self.qty:
            raise ValueError(f"shadow calculator: short sell {qty} > {self.qty}")
        self.realized_pnl += (price - self.avg_cost) * qty
        self.qty -= qty
        self.total_cost = self.qty * self.avg_cost  # avg_cost unchanged


def replay_expected(trades):
    """trades: list of (trade_date, trade_type, qty, price) — replayed in
    chronological trade_date order, exactly like settlement_service's chain
    recalculation does."""
    pos = ShadowPosition()
    for _, ttype, qty, price in sorted(trades, key=lambda t: t[0]):
        if ttype == 'BUY':
            pos.apply_buy(qty, price)
        else:
            pos.apply_sell(qty, price)
    return pos


# =============================================================================
# Reference data setup / teardown
# =============================================================================

def now_ms():
    return int(time.time() * 1000)


def setup_reference_data(run_id, ccy='USD'):
    portfolio = f'AVPV_{run_id}'
    security = f'AVPV SEC {run_id}'
    security_id = int(run_id)
    party = f'AVPV_PARTY_{run_id}'
    marker = 'AVP_VERIFY_SCRIPT'
    ts = now_ms()

    print(f"== Creating throwaway reference data (run_id={run_id}) ==")

    impala_manager.execute_write(f"""
        UPSERT INTO {DATABASE}.cis_portfolio
        (name, currency, revaluation_status, src_system, status, is_active,
         created_by, created_at, updated_by, updated_at)
        VALUES ('{portfolio}', '{ccy}', 'NON-REVALUED', 'CIS', 'VALIDATED', true,
                '{marker}', '{ts}', '{marker}', '{ts}')
    """, database=DATABASE)

    impala_manager.execute_write(f"""
        UPSERT INTO {DATABASE}.cis_security
        (security_id, security_name, issuer, security_type, investment_type,
         currency_code, status, src_system, is_active, created_by, created_at,
         updated_by, updated_at)
        VALUES ({security_id}, '{security}', '{party}', 'EQUITY', '',
                '{ccy}', 'VALIDATED', 'CIS', true, '{marker}', '{ts}',
                '{marker}', '{ts}')
    """, database=DATABASE)

    impala_manager.execute_write(f"""
        UPSERT INTO {DATABASE}.cis_party
        (party_short_name, party_full_name, is_broker, is_custodian,
         is_issuer, status, src_system, is_active, created_by, created_at,
         updated_by, updated_at)
        VALUES ('{party}', '{party} Pte Ltd', true, false, true, 'VALIDATED',
                'CIS', true, '{marker}', '{ts}', '{marker}', '{ts}')
    """, database=DATABASE)

    impala_manager.execute_write(f"""
        UPSERT INTO {DATABASE}.cis_equity_price
        (currency_code, security_label, price_date, main_closing_price,
         price_timestamp, src_system, is_active, created_by, created_at,
         updated_by, updated_at)
        VALUES ('{ccy}', '{security}', '{datetime.now().date().isoformat()}',
                CAST(50.00 AS DECIMAL(18,6)), {ts}, 'CIS', true,
                '{marker}', {ts}, '{marker}', {ts})
    """, database=DATABASE)

    print(f"  portfolio={portfolio!r} security={security!r} counterparty={party!r}")
    return portfolio, security, party, ccy


def cleanup(run_id, verbose=True):
    portfolio = f'AVPV_{run_id}'
    security = f'AVPV SEC {run_id}'
    party = f'AVPV_PARTY_{run_id}'

    if verbose:
        print(f"== Cleaning up run_id={run_id} ==")

    statements = [
        ('cis_trade_position', f"DELETE FROM {DATABASE}.cis_trade_position WHERE portfolio_short_name = '{portfolio}'"),
        ('cis_position', f"DELETE FROM {DATABASE}.cis_position WHERE portfolio = '{portfolio}'"),
        ('cis_position_queue', f"DELETE FROM {DATABASE}.cis_position_queue WHERE portfolio_id = '{portfolio}'"),
        ('cis_settlement_queue', f"DELETE FROM {DATABASE}.cis_settlement_queue WHERE portfolio_id = '{portfolio}'"),
        ('cis_trade', f"DELETE FROM {DATABASE}.cis_trade WHERE portfolio_short_name = '{portfolio}'"),
        ('cis_trade_event_queue', f"DELETE FROM {DATABASE}.cis_trade_event_queue WHERE trade_id IN (SELECT trade_id FROM {DATABASE}.cis_trade WHERE portfolio_short_name = '{portfolio}')"),
        ('cis_equity_price', f"DELETE FROM {DATABASE}.cis_equity_price WHERE security_label = '{security}'"),
        ('cis_security', f"DELETE FROM {DATABASE}.cis_security WHERE security_name = '{security}'"),
        ('cis_party', f"DELETE FROM {DATABASE}.cis_party WHERE party_short_name = '{party}'"),
        ('cis_portfolio', f"DELETE FROM {DATABASE}.cis_portfolio WHERE name = '{portfolio}'"),
    ]
    for label, query in statements:
        ok = impala_manager.execute_write(query, database=DATABASE)
        if verbose:
            print(f"  {'OK' if ok else 'FAILED'}: {label}")


# =============================================================================
# Trade booking helper (mirrors avp_live_fixtures._settle_trade)
# =============================================================================

def book_and_wait(client, portfolio, security, ccy, trade_type, qty, price, trade_date):
    trade_id = ui_create_trade(
        client, portfolio_id=portfolio, security_id=security,
        trade_type=trade_type, quantity=qty, price=price,
        trade_date=trade_date, settle_date=trade_date, currency_code=ccy,
    )
    pos = get_latest_position(portfolio, security, 'TRADED', trade_date)
    if pos is None:
        raise RuntimeError(
            f"No TRADED position appeared for trade {trade_id} "
            f"({trade_type} {qty}@{price} on {trade_date}) within "
            f"{POLL_TIMEOUT_SECONDS}s — is the Trade Event Worker / Position "
            f"Worker running against this same database?"
        )
    print(f"  booked trade_id={trade_id}: {trade_type} {qty}@{price} on {trade_date}")
    return trade_id


# =============================================================================
# Main scenario
# =============================================================================

def run(run_id):
    portfolio, security, party, ccy = setup_reference_data(run_id)
    client = get_authenticated_client()
    today = datetime.now().date()

    def d(offset):
        return (today - timedelta(days=offset)).isoformat()

    trades_booked = []  # (trade_date, trade_type, qty, price) — for the shadow calculator

    print("\n== Booking trades (deliberately out of chronological order, to exercise backdated chain recalculation) ==")

    # 1. Baseline BUY, 20 days ago
    book_and_wait(client, portfolio, security, ccy, 'BUY', Decimal('100'), Decimal('50.00'), d(20))
    trades_booked.append((d(20), 'BUY', Decimal('100'), Decimal('50.00')))

    # 2. SELL, 10 days ago (after baseline)
    book_and_wait(client, portfolio, security, ccy, 'SELL', Decimal('40'), Decimal('60.00'), d(10))
    trades_booked.append((d(10), 'SELL', Decimal('40'), Decimal('60.00')))

    # 3. Backdated BUY, 25 days ago — BEFORE the baseline. Forces a chain
    #    recalculation that must reorder this trade ahead of both above.
    book_and_wait(client, portfolio, security, ccy, 'BUY', Decimal('20'), Decimal('40.00'), d(25))
    trades_booked.append((d(25), 'BUY', Decimal('20'), Decimal('40.00')))

    # 4. Backdated SELL, 15 days ago — BETWEEN the baseline BUY (day 20) and
    #    the SELL (day 10). Forces another chain recalculation.
    book_and_wait(client, portfolio, security, ccy, 'SELL', Decimal('15'), Decimal('45.00'), d(15))
    trades_booked.append((d(15), 'SELL', Decimal('15'), Decimal('45.00')))

    print("\n== Independent reference calculation (chronological replay) ==")
    expected = replay_expected(trades_booked)
    for td, tt, q, p in sorted(trades_booked, key=lambda t: t[0]):
        print(f"  {td}  {tt:4s} {q:>6} @ {p}")
    print(f"  Expected final: qty={expected.qty} avg_cost={expected.avg_cost} "
          f"total_cost={expected.total_cost} realized_pnl={expected.realized_pnl}")

    print("\n== Verifying actual system output (cis_trade_position, latest TRADED row) ==")
    final_pos = get_latest_position(portfolio, security, 'TRADED')
    if final_pos is None:
        print("  FAIL  no final position row found at all")
        RESULTS['fail'].append(('final position exists', None, 'a row'))
    else:
        check('final quantity', final_pos['quantity'], expected.qty)
        check('final average_cost_fc', final_pos['average_cost_fc'], expected.avg_cost)
        check('final total_cost_fc', final_pos['total_cost_fc'], expected.total_cost)
        check('final realized_pnl_fc', final_pos['realized_pnl_fc'], expected.realized_pnl)

    # Spot-check the position as-of the earliest backdated trade date too —
    # this specifically verifies the backdated BUY was correctly inserted
    # BEFORE the baseline in the chain, not just appended.
    print("\n== Verifying backdated insertion point (position as-of day-25, the earliest trade) ==")
    early_pos = get_latest_position(portfolio, security, 'TRADED', d(25))
    if early_pos is None:
        print("  FAIL  no position row found for the backdated BUY's own date")
        RESULTS['fail'].append(('backdated-date position exists', None, 'a row'))
    else:
        check('day-25 quantity (backdated BUY alone)', early_pos['quantity'], Decimal('20'))
        check('day-25 average_cost_fc (backdated BUY alone)', early_pos['average_cost_fc'], Decimal('40.00'))

    return portfolio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keep', action='store_true', help="Don't clean up test data after running")
    parser.add_argument('--cleanup-only', metavar='RUN_ID', help="Skip the test, just delete a prior run's leftovers")
    args = parser.parse_args()

    if args.cleanup_only:
        cleanup(args.cleanup_only)
        return

    run_id = datetime.now().strftime('%Y%m%d%H%M%S')
    print(f"AVP verification run_id={run_id}\n")

    try:
        run(run_id)
    finally:
        if args.keep:
            print(f"\n--keep passed: leaving test data in place (run_id={run_id}). "
                  f"Clean up later with: python scripts/avp_verification_script.py --cleanup-only {run_id}")
        else:
            print()
            cleanup(run_id)

    print(f"\n{'=' * 60}\nRESULT: {len(RESULTS['pass'])} passed, {len(RESULTS['fail'])} failed\n{'=' * 60}")
    if RESULTS['fail']:
        for label, actual, expected in RESULTS['fail']:
            print(f"  FAILED: {label} (got {actual}, expected {expected})")
        sys.exit(1)
    else:
        print("All AVP checks passed — BUY, SELL, and backdated BUY/SELL all produced correct AVP results.")
        sys.exit(0)


if __name__ == '__main__':
    main()

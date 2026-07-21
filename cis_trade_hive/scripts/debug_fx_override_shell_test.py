"""
Direct shell test for the open_fx_rate override propagation bug.

Bypasses cis_trade_event_queue / cis_position_queue and the async worker(s)
entirely — calls position_service.calculate_position() directly so there is
no ambiguity about which process/worker/log destination is involved.

Usage:
    python manage.py shell < scripts/debug_fx_override_shell_test.py

Expected output: average_cost_lc = 30.0 (gross_amount_lc=300 / quantity=10).
If a different value appears (e.g. a market-rate-derived value), the bug is
inside position_service.py itself. If this prints correctly, the bug is in
the worker/queue dispatch layer, not in the calculation logic.
"""

from decimal import Decimal
from trade.services.position_service import position_service

# Unique fake trade_id so this never collides with the idempotency guard
# against any real cis_trade_position row.
TEST_TRADE_ID = 999999000001

success, msg, position = position_service.calculate_position(
    portfolio_id='UOBS_IB_AC',
    security_id='Test_Prakash',
    trade_type='BUY',
    quantity=Decimal('10'),
    price=Decimal('100'),
    charges=Decimal('0'),
    position_date='2026-03-03',
    trade_id=TEST_TRADE_ID,
    updated_by='SHELL_TEST',
    security_currency='AOA',
    portfolio_currency='SGD',
    isin='SG1212121212',
    security_name='Test_Prakash',
    custodian='',
    sub_custodian='',
    trade_lc=Decimal('300'),
    gross_amount_lc=Decimal('300'),
)

print("=" * 60)
print(f"success = {success}")
print(f"msg = {msg}")
if position:
    print(f"average_cost_fc  = {position.get('average_cost_fc')}")
    print(f"average_cost_lc  = {position.get('average_cost_lc')}")
    print(f"total_cost_fc    = {position.get('total_cost_fc')}")
    print(f"total_cost_lc    = {position.get('total_cost_lc')}")
print("=" * 60)
print("EXPECTED: average_cost_lc = 30.0  (gross_amount_lc=300 / quantity=10)")

# Cleanup: remove the test row so it doesn't linger in cis_trade_position
from core.repositories.impala_connection import impala_manager
impala_manager.execute_write(
    f"DELETE FROM gmp_cis.cis_trade_position WHERE trade_id = {TEST_TRADE_ID}",
    database='gmp_cis'
)
print(f"Cleaned up test row for trade_id={TEST_TRADE_ID}")

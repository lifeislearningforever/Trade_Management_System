"""
Management command: backfill_zero_price_positions

Finds all BUY/SELL trades with price = 0.0 that have no row in cis_trade_position
(for either TRADED or SETTLED basis) and re-queues position calculation
for each gap trade.

Covers all trade statuses — the position calculation guard was blocking price=0
trades before the fix in commit 6194dce, so any settled trade with price=0 may
be missing its position rows regardless of current status.

Usage:
    # Dry run — lists gap trades, writes nothing
    python manage.py backfill_zero_price_positions --dry-run

    # Live run — queues position calculation for all gap trades
    python manage.py backfill_zero_price_positions --execute

    # Scope to one portfolio
    python manage.py backfill_zero_price_positions --execute --portfolio UOB-SG-TRADING

    # Scope to one specific trade
    python manage.py backfill_zero_price_positions --execute --trade-id 1782358002323

    # Save output log
    python manage.py backfill_zero_price_positions --execute --output result.txt
"""

import sys
import logging
import re
from decimal import Decimal
import os
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from lib.management_base import BaseCommand, CommandError, run_command
from lib.impala_connection import impala_manager
from lib.settlement_service import settlement_service
from lib.config import settings

logger = logging.getLogger(__name__)

DATABASE = settings.IMPALA_CONFIG['DATABASE']
TRADE_TABLE = f'{DATABASE}.cis_trade'
POSITION_TABLE = f'{DATABASE}.cis_trade_position'
PORTFOLIO_TABLE = f'{DATABASE}.cis_portfolio'

# Only these trade types affect position
POSITION_AFFECTING_TYPES = ('BUY', 'SELL')


class TeeWriter:
    def __init__(self, stdout, filepath=None):
        self._stdout = stdout
        self._file = open(filepath, 'w', encoding='utf-8') if filepath else None

    def write(self, msg: str):
        clean = re.sub(r'\x1b\[[0-9;]*m', '', msg)
        self._stdout.write(msg)
        if self._file:
            self._file.write(clean + '\n')
            self._file.flush()

    def close(self):
        if self._file:
            self._file.close()


class Command(BaseCommand):
    help = (
        'Backfill position rows for price=0.0 BUY/SELL trades that are missing '
        'from cis_trade_position. Dry-run unless --execute is passed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--execute',
            action='store_true',
            default=False,
            help='Actually queue position calculations. Without this flag the command is a dry run.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            dest='dry_run',
            help='Explicit dry-run flag. Overrides --execute.',
        )
        parser.add_argument(
            '--portfolio',
            default=None,
            metavar='PORTFOLIO',
            help='Limit to a specific portfolio_short_name.',
        )
        parser.add_argument(
            '--trade-id',
            default=None,
            metavar='TRADE_ID',
            help='Limit to a single trade_id.',
        )
        parser.add_argument(
            '--output',
            default=None,
            metavar='FILE',
            help='Save the full output log to this file.',
        )

    def handle(self, *args, **options):
        execute = options['execute'] and not options['dry_run']
        portfolio_filter = options['portfolio']
        trade_id_filter = options['trade_id']
        output_path = options['output']

        self._tee = TeeWriter(self.stdout, output_path)
        if output_path:
            self._tee.write(f'Output also saved to: {output_path}')

        mode = 'LIVE' if execute else 'DRY-RUN'
        self._tee.write(self.style.WARNING(
            f'\n=== backfill_zero_price_positions [{mode}] ===\n'
        ))

        trades = self._find_gap_trades(portfolio_filter, trade_id_filter)

        if not trades:
            self._tee.write(self.style.SUCCESS(
                'No gap trades found — all price=0.0 trades already have position rows.'
            ))
            self._tee.close()
            return

        self._tee.write(
            f'Found {len(trades)} trade(s) with price=0.0 and no position row:\n'
        )
        self._print_trade_table(trades)

        if not execute:
            self._tee.write(self.style.WARNING(
                '\nDRY-RUN — nothing queued. Re-run with --execute to backfill.\n'
            ))
            self._tee.close()
            return

        self._backfill(trades)
        self._tee.close()

    # ------------------------------------------------------------------

    def _find_gap_trades(self, portfolio_filter, trade_id_filter):
        """
        Return BUY/SELL trades where price=0 AND no row exists in cis_trade_position
        for either TRADED or SETTLED basis.
        """
        where_extra = ''
        if portfolio_filter:
            safe_pf = portfolio_filter.replace('\\', '\\\\').replace("'", "\\'")
            where_extra += f" AND t.portfolio_short_name = '{safe_pf}'"
        if trade_id_filter:
            where_extra += f" AND t.trade_id = {int(trade_id_filter)}"

        query = f"""
            SELECT
                t.trade_id,
                t.deal_number,
                t.trade_type,
                t.trade_status,
                t.portfolio_short_name,
                t.security_label,
                t.security_full_name,
                t.trade_date,
                t.settle_date,
                t.quantity,
                t.price,
                t.commission,
                t.sec_fee,
                t.other_charges,
                t.currency_code,
                t.custodian,
                t.udf_sub_custodian,
                s.isin,
                COALESCE(p.currency, t.currency_code) AS portfolio_currency
            FROM {TRADE_TABLE} t
            LEFT JOIN {PORTFOLIO_TABLE} p
                ON t.portfolio_short_name = p.name
               AND (p.is_active = true OR p.is_active IS NULL)
            LEFT JOIN {DATABASE}.cis_security s
                ON t.security_label = s.security_name
            WHERE t.trade_type IN ('BUY', 'SELL')
              AND (t.price = 0 OR t.price IS NULL)
              AND t.is_deleted = false
              AND t.trade_id NOT IN (
                  SELECT DISTINCT trade_id
                  FROM {POSITION_TABLE}
                  WHERE trade_id IS NOT NULL
              )
              {where_extra}
            ORDER BY t.trade_date, t.trade_id
        """
        try:
            return impala_manager.execute_query(query, database=DATABASE) or []
        except Exception as e:
            raise CommandError(f'Error querying gap trades: {e}')

    def _print_trade_table(self, trades):
        header = f'  {"TRADE_ID":<15} {"DEAL_NUMBER":<25} {"TYPE":<5} {"STATUS":<20} {"PORTFOLIO":<25} {"SECURITY":<35} {"TRADED":<12} {"SETTLED":<12}'
        self._tee.write(header)
        self._tee.write('  ' + '-' * 155)
        for t in trades:
            self._tee.write(
                f'  {str(t.get("trade_id", "")):<15} '
                f'{str(t.get("deal_number", "")):<25} '
                f'{str(t.get("trade_type", "")):<5} '
                f'{str(t.get("trade_status", "")):<20} '
                f'{str(t.get("portfolio_short_name", "")):<25} '
                f'{str(t.get("security_label", "")):<35} '
                f'{str(t.get("trade_date", "")):<12} '
                f'{str(t.get("settle_date", "")):<12}'
            )
        self._tee.write('')

    def _backfill(self, trades):
        queued = 0
        skipped = 0
        errors = []

        for t in trades:
            trade_id = t.get('trade_id')
            deal_number = t.get('deal_number', trade_id)
            try:
                charges = (
                    Decimal(str(t.get('commission') or 0)) +
                    Decimal(str(t.get('sec_fee') or 0)) +
                    Decimal(str(t.get('other_charges') or 0))
                )

                success, message, _ = settlement_service.process_trade_settlement(
                    trade_id=trade_id,
                    portfolio_id=t.get('portfolio_short_name', ''),
                    security_id=t.get('security_label', ''),
                    trade_type=t.get('trade_type', ''),
                    quantity=Decimal(str(t.get('quantity') or 0)),
                    price=Decimal(str(t.get('price') or 0)),
                    charges=charges,
                    trade_date=str(t.get('trade_date', '')),
                    settle_date=str(t.get('settle_date', '')),
                    updated_by='SYSTEM_BACKFILL',
                    security_currency=t.get('currency_code'),
                    portfolio_currency=t.get('portfolio_currency'),
                    isin=t.get('isin'),
                    security_name=t.get('security_full_name'),
                    custodian=t.get('custodian'),
                    sub_custodian=t.get('udf_sub_custodian'),
                    async_mode=True,
                    position_basis=None,  # dual: TRADED + SETTLED
                )

                if success:
                    queued += 1
                    self._tee.write(self.style.SUCCESS(
                        f'  QUEUED  trade_id={trade_id} ({deal_number}): {message}'
                    ))
                else:
                    skipped += 1
                    errors.append(f'trade_id={trade_id}: {message}')
                    self._tee.write(self.style.ERROR(
                        f'  FAILED  trade_id={trade_id} ({deal_number}): {message}'
                    ))

            except Exception as e:
                skipped += 1
                errors.append(f'trade_id={trade_id}: {e}')
                self._tee.write(self.style.ERROR(
                    f'  ERROR   trade_id={trade_id} ({deal_number}): {e}'
                ))

        self._tee.write('\n' + '=' * 60)
        self._tee.write(self.style.SUCCESS(
            f'Done. {queued} trade(s) queued for position backfill.'
        ))
        if skipped:
            self._tee.write(self.style.WARNING(f'       {skipped} trade(s) failed/skipped.'))

        if errors:
            self._tee.write(self.style.ERROR(f'\n{len(errors)} error(s):'))
            for e in errors:
                self._tee.write(self.style.ERROR(f'  • {e}'))
            sys.exit(1)


if __name__ == '__main__':
    run_command(Command)

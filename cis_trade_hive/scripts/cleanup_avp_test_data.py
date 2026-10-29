#!/usr/bin/env python
"""
Cleanup for the live AVP test suite (trade/tests/test_avp_live_scenarios.py).

Deletes every row that suite could have written — scoped to the 3 SIT/UAT
reference portfolio/security pairs plus the 'AVP_AUTOTEST' created_by marker
as defense-in-depth — across cis_trade, cis_trade_position, cis_position,
cis_position_queue, cis_settlement_queue, and cis_equity_price. Never touches
cis_portfolio/cis_security/cis_party — this suite doesn't create reference
data, so it has nothing of its own to delete there.

The test suite already runs this automatically at the end of every run
(pass or fail). Run it manually after a crashed/interrupted run, or any time
you just want to confirm the sandbox is clean:

    python scripts/cleanup_avp_test_data.py

Safe to run even if there's nothing to clean up — every DELETE is a no-op
in that case.
"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from trade.tests.avp_live_fixtures import cleanup_test_data, SIT_UAT_PAIRS


def main():
    print("=" * 70)
    print("AVP Test Data Cleanup")
    print("=" * 70)
    portfolios = [p[0] for p in SIT_UAT_PAIRS.values()]
    securities = [p[3] for p in SIT_UAT_PAIRS.values()]
    print(f"SIT/UAT portfolios: {portfolios}")
    print(f"SIT/UAT securities: {securities}")
    print("-" * 70)

    results = cleanup_test_data(verbose=True)

    print("-" * 70)
    failed = [table for table, ok in results.items() if not ok]
    if failed:
        print(f"DONE WITH WARNINGS — failed for: {failed}")
        print("(a table not existing in your environment is a common, "
              "harmless cause — e.g. cis_equity_price under a different name)")
        sys.exit(1)
    else:
        print("DONE — no AVP test data remains in the database.")
        sys.exit(0)


if __name__ == '__main__':
    main()

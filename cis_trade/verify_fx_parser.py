#!/usr/bin/env python
"""
Quick verification script for FX Rates Parser
"""

import sys
from pathlib import Path
from reference_data.services.fx_rates_parser import FXRatesParser, parse_fx_rates_file

def main():
    print("=" * 60)
    print("FX Rates Parser Verification")
    print("=" * 60)

    # Test 1: Parse sample text
    print("\n[Test 1] Parsing sample text...")
    parser = FXRatesParser()

    sample_text = """H|GMP|19800101|20251224111237
D|1|USD-AED|AED|20251124|3.6732|USD|3.6725|BOSET
D|1|USD-SGD|SGD|20251124|1.3085|USD|1.3082|BOSET
D|1|USD-EUR|EUR|20251124|0.86865|USD|0.86855|BOSET"""

    result = parser.parse_text(sample_text)
    print(f"  ✓ Headers: {result['headers_count']}")
    print(f"  ✓ Details: {result['details_count']}")
    print(f"  ✓ Errors: {result['errors_count']}")

    assert result['headers_count'] == 1, "Expected 1 header"
    assert result['details_count'] == 3, "Expected 3 details"
    assert result['errors_count'] == 0, "Expected no errors"

    # Test 2: Check mid rate calculation
    print("\n[Test 2] Checking mid rate calculation...")
    detail = parser.details[0]
    expected_mid = (detail.spot_rf_a + detail.spot_rf_b) / 2
    print(f"  Currency Pair: {detail.spot_ff0}")
    print(f"  Spot RF A: {detail.spot_rf_a}")
    print(f"  Spot RF B: {detail.spot_rf_b}")
    print(f"  Calculated Mid: {detail.mid_rate}")
    print(f"  Expected Mid: {expected_mid}")
    assert detail.mid_rate == expected_mid, "Mid rate calculation failed"
    print("  ✓ Mid rate calculation correct")

    # Test 3: Filter by currency pair
    print("\n[Test 3] Testing filter by currency pair...")
    sgd_rates = parser.filter_by_currency_pair('USD-SGD')
    print(f"  Found {len(sgd_rates)} USD-SGD rate(s)")
    assert len(sgd_rates) == 1, "Expected 1 USD-SGD rate"
    assert sgd_rates[0].base == 'SGD', "Expected base currency SGD"
    print("  ✓ Filter by currency pair works")

    # Test 4: Get summary
    print("\n[Test 4] Getting summary statistics...")
    summary = parser.get_summary()
    print(f"  Total records: {summary['total_records']}")
    print(f"  Unique currencies: {summary['unique_currencies']}")
    print(f"  Currency list: {', '.join(summary['currencies'])}")
    print(f"  Date range: {summary['date_range']}")
    assert summary['total_records'] == 3, "Expected 3 total records"
    print("  ✓ Summary statistics correct")

    # Test 5: Convert to dict
    print("\n[Test 5] Converting to dictionaries...")
    dicts = parser.get_details_as_dicts()
    print(f"  Converted {len(dicts)} records")
    assert len(dicts) == 3, "Expected 3 dictionaries"
    assert all('mid_rate' in d for d in dicts), "All dicts should have mid_rate"
    print("  ✓ Dictionary conversion works")

    # Test 6: Parse sample file
    sample_file = Path('sql/sample_data/07_fx_rates_sample.txt')
    if sample_file.exists():
        print(f"\n[Test 6] Parsing sample file: {sample_file}")
        result = parse_fx_rates_file(str(sample_file))
        print(f"  Total lines: {result['total_lines']}")
        print(f"  Headers: {result['headers_count']}")
        print(f"  Details: {result['details_count']}")
        print(f"  Errors: {result['errors_count']}")
        assert result['details_count'] > 0, "Expected some detail records"
        print("  ✓ File parsing works")

        # Show first few records
        print("\n  Sample records:")
        parser2 = FXRatesParser()
        parser2.parse_file(str(sample_file))
        for i, detail in enumerate(parser2.details[:5], 1):
            print(f"    {i}. {detail.spot_ff0:12s} | {detail.trade_date} | Mid: {detail.mid_rate:10.6f}")
    else:
        print(f"\n[Test 6] Sample file not found: {sample_file}")
        print("  ⚠ Skipping file test")

    print("\n" + "=" * 60)
    print("✓ All tests passed successfully!")
    print("=" * 60)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

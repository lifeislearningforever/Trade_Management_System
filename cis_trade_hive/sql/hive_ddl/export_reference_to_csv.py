#!/usr/bin/env python3
"""
Export Reference Data from Excel to CSV files for Hive loading

Usage:
    python export_reference_to_csv.py
"""

import pandas as pd
import os

EXCEL_FILE = '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/kudu_ddl/Reference_Data.xlsx'
OUTPUT_DIR = '/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/sql/hive_ddl/reference_csv'

print("=" * 70)
print("Exporting Reference Data from Excel to CSV")
print("=" * 70)
print()

# Create output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"Output directory: {OUTPUT_DIR}")
print()

try:
    xl = pd.ExcelFile(EXCEL_FILE)
    total_rows = 0

    for sheet_name in xl.sheet_names:
        print(f"Processing: {sheet_name}")
        df = pd.read_excel(xl, sheet_name=sheet_name)

        # Convert boolean to lowercase strings
        for col in df.columns:
            if df[col].dtype == 'bool':
                df[col] = df[col].apply(lambda x: str(x).lower())

        # Save to CSV (pipe-delimited, no header)
        output_file = f"{OUTPUT_DIR}/{sheet_name}.csv"
        df.to_csv(output_file, sep='|', index=False, header=False, na_rep='')
        print(f"  ✓ Exported {len(df):,} rows to {sheet_name}.csv")
        total_rows += len(df)

    print()
    print("=" * 70)
    print(f"✓ SUCCESS! Exported {total_rows:,} total rows")
    print("=" * 70)
    print()
    print("Files created:")
    for sheet_name in xl.sheet_names:
        print(f"  - {OUTPUT_DIR}/{sheet_name}.csv")

except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    import sys
    sys.exit(1)

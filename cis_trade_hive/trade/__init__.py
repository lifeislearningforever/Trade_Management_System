"""
Trade Management Module

Handles all trade-related operations including:
- Buy, Sell, Add Long, Deliver Long
- Reduction Basis, Income, Split Transaction
- Position tracking and P&L calculation
- Four-Eyes (Maker-Checker) workflow
- Full audit trail

All data operations use Kudu via Impala (no Django ORM).
"""

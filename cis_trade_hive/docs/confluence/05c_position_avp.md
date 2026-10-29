# Position & AVP (Average Price Position)

> **Audience:** User, BA, SA, Developer, Support
> **Read time:** ~12 minutes

---

## Plain English: What Is a Position?

A **position** is how many units of a security a portfolio currently holds, and at what average cost.

**Example:**
- Portfolio `UOB-SG` bought 100 shares of AAPL at $175. Position: 100 shares, avg cost $175.
- Next month, they bought 50 more at $180. Position: 150 shares, avg cost $176.67.
- Next month, they sold 30. Position: 120 shares, avg cost still $176.67 (avg cost doesn't change on a sell).

This running calculation of average cost is called **AVP — Average Price Position** (also known as weighted average cost).

---

## Why Does It Matter?

The average cost tells you:
- **Unrealised P&L:** If AAPL is now at $190 and you hold 120 shares at avg cost $176.67, your unrealised gain is ($190 - $176.67) × 120 = $1,600.
- **Realised P&L on sells:** When you sell, profit = (sell price − avg cost) × qty sold.

---

## AVP Formula

### When You BUY (or ADD_LONG):
```
new_avg_cost = (old_total_cost + trade_cost + charges) / new_total_qty

where:
  old_total_cost = old_avg_cost × old_qty
  trade_cost     = qty × price
  charges        = commission + sec_fee + other_charges
  new_total_qty  = old_qty + trade_qty
```

### When You SELL:
```
avg_cost = UNCHANGED  (avg cost stays the same)
realized_pnl = (sell_price - avg_cost) × qty_sold
new_qty = old_qty - qty_sold
```

### Worked Example:
```
Starting position: 0 shares

Trade 1 — BUY 100 @ $175.00, Commission $10.00
  new_avg_cost = (0 + 100×175 + 10) / 100 = $175.10
  Position: 100 shares, avg cost $175.10

Trade 2 — BUY 50 @ $180.00, Commission $5.00
  old_total_cost = 100 × $175.10 = $17,510.00
  new_avg_cost = ($17,510 + 50×$180 + $5) / 150 = $176.77
  Position: 150 shares, avg cost $176.77

Trade 3 — SELL 30 @ $185.00
  avg_cost = $176.77 (unchanged)
  realized_pnl = ($185.00 - $176.77) × 30 = $246.90
  Position: 120 shares, avg cost $176.77
```

---

## How CIS Calculates Positions (Technical Flow)

Position calculation is **asynchronous** — it does not block the user. When a trade is settled:

```
1. Trade status changes to SETTLED
   │
2. Position event enqueued
   INSERT INTO gmp_cis.cis_position_queue
   {event_type: 'SETTLEMENT', trade_id: ..., status: 'PENDING'}
   │
3. Background worker (position_worker_daemon) polls every 10 seconds
   SELECT * FROM cis_position_queue WHERE status='PENDING' LIMIT 100
   │
4. PositionService.calculate_position(trade)
   │
   ├── Get last position BEFORE this trade's trade_date
   │     (handles backdated trades correctly)
   │
   ├── Apply formula (BUY or SELL)
   │
   ├── Insert into cis_trade_position (versioned history)
   │     Every settlement creates a new version row
   │
   └── Mark queue entry as PROCESSED
   │
SLA: < 5 minutes from settlement to position update
```

**Idempotency guard:** If the same trade is processed twice (e.g. due to a retry), the system detects the duplicate and skips it.

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `cis_trade_position` | Versioned position history — one row per settled trade per portfolio/security |
| `cis_position_queue` | Async queue — pending position calculation events |
| `cis_settlement_queue` | Trades awaiting future settle date processing |

### cis_trade_position Key Columns

| Column | Description |
|--------|-------------|
| `position_id` | Unique ID |
| `trade_id` | The trade that caused this position change |
| `portfolio_short_name` | Portfolio |
| `security_label` | Security |
| `position_date` | Date of this position snapshot |
| `quantity` | Holding after this trade |
| `average_cost` | Weighted average cost after this trade (DECIMAL 20,8) |
| `total_cost` | `quantity × average_cost` |
| `realized_pnl` | Realised P&L from this trade (SELL only) |
| `trade_basis` | TRADED or SETTLED basis |
| `version` | Incremented each time position is updated |
| `status` | OPEN or CLOSED |

---

## Two Position Bases

Each settled trade creates **two position records**:

| Basis | Description |
|-------|-------------|
| `TRADED` | Position as of the trade execution date |
| `SETTLED` | Position as of the actual settlement date |

This matters for T+1 / T+2 trades: the position exists on trade date but cash doesn't move until settle date.

---

## Settlement Date Logic

| Scenario | What happens |
|----------|-------------|
| Settle date = today (T+0) | Position calculated immediately after VALIDATED |
| Settle date = future (T+1, T+2) | Trade goes into `cis_settlement_queue`; EOD job processes it on settle date |
| Settle date = past (backdated) | Allowed — triggers position recalculation for all subsequent trades in the chain (to maintain correct cumulative avg cost) |

---

## Multi-Currency Support

When a security trades in a different currency than the portfolio's base currency:

```
Security: AAPL (trades in USD)
Portfolio: UOB-SG (base currency: SGD)

FX rate: 1 USD = 1.35 SGD (from gmp_cis_sta_dly_fx_rates)

total_amount_fc = 100 × $175 = $17,500 USD
total_amount_lc = $17,500 × 1.35 = SGD 23,625

AVP calculation uses the LC amount for consistency.
FX impact is included in the P&L (not separated).
```

FX rate used: floating (latest available rate, not locked to trade date).

---

## For Users: Viewing Positions

1. Go to **Trade → Positions**
2. Filter by portfolio and/or security
3. See current holding, average cost, unrealised P&L
4. Click on any position to see the full version history

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `trade/services/position_service.py` | Core AVP calculation (743 lines) |
| `trade/services/settlement_service.py` | Settlement date logic and EOD processing |
| `trade/services/position_queue_service.py` | Async queue processing |
| `trade/services/multicurrency_service.py` | FX conversion (FC→LC) |
| `trade/repositories/position_repository.py` | SQL on `cis_trade_position` |
| `trade/views_position.py` | Position views |
| `trade/management/commands/refresh_positions.py` | Manual position recalculation command |
| `trade/management/commands/process_settlements.py` | EOD settlement command |
| `scripts/position_worker_daemon.sh` | Long-running worker process |
| `sql/ddl/13_avp_tables_kudu.sql` | AVP DDL |
| `sql/ddl/22_position_queue_add_basis_columns.sql` | Position basis DDL |

### Recalculate positions manually
```bash
# Recalculate positions for a specific portfolio from a date
python manage.py refresh_positions --portfolio UOB-SG --from-date 2026-01-01

# Process pending settlements
python manage.py process_settlements
```

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| Position not showing after trade settled | Check `cis_position_queue` — is entry PENDING or FAILED? |
| Position shows wrong avg cost | A backdated trade may have been entered — recalculate from that date |
| Position shows 0 but trades exist | Position worker may be down — check `scripts/position_worker_daemon.sh` process |
| Negative position | Short selling rejected by validation, but if it appears, a backdated delete/cancel may have occurred — check trade history |

### Useful diagnostic queries
```sql
-- Check queue status
SELECT status, COUNT(*) FROM gmp_cis.cis_position_queue
GROUP BY status ORDER BY 2 DESC;

-- Check position for a portfolio/security
SELECT position_date, quantity, average_cost, trade_basis, version
FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'UOB-SG'
  AND security_label = 'AAPL'
ORDER BY position_date DESC, version DESC
LIMIT 20;
```

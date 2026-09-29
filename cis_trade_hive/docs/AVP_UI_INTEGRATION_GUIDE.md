# AVP UI Integration Guide

## Document Info
| Field | Value |
|-------|-------|
| **Module** | Trade Position / AVP |
| **Version** | 1.1 |
| **Created** | 2026-03-04 |
| **Updated** | 2026-03-04 |
| **Purpose** | Step-by-step guide for integrating AVP with cis_trade UI |

---

## Overview

This guide shows how to integrate the AVP position calculation services with the existing cis_trade UI workflow.

**Key Point:** AVP calculation is triggered at **trade creation** (INITIAL status), with processing based on settle date:
- **T+0 (settle_date = today):** Position calculated immediately
- **T+1/T+2 (settle_date > today):** Trade queued for future settlement
- **Backdated (settle_date < today):** Validated and position recalculated

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TRADE WORKFLOW WITH AVP INTEGRATION                       │
└─────────────────────────────────────────────────────────────────────────────┘

  TRADE CREATION                        SETTLEMENT LOGIC
  ──────────────                        ────────────────
  ┌──────────────┐
  │ CREATE Trade │ ◄── AVP TRIGGERED HERE (at INITIAL status)
  │   (INITIAL)  │
  └──────────────┘
         │
         ├──── settle_date = today ────────► Position calculated IMMEDIATELY
         │                                   (output to position_master)
         │
         ├──── settle_date > today ────────► Trade QUEUED for settlement
         │     (T+1, T+2, etc.)              (processed when date arrives)
         │
         └──── settle_date < today ────────► BACKDATED validation
               (backdated)                   (recalculate chain if valid)

  WORKFLOW CONTINUES (independent of AVP):
  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │   SUBMIT     │ ──► │   VALIDATE   │ ──► │   SETTLE     │
  │   (Maker)    │     │   (Checker)  │     │   (Checker)  │
  └──────────────┘     └──────────────┘     └──────────────┘
```

---

## Integration Point: trade_create() Function

The AVP calculation is triggered when a trade is **created** (at INITIAL status). Here's how to modify the `trade/views.py` file:

### Step 1: Import AVP Services

Add these imports at the top of `trade/views.py`:

```python
# Add these imports to trade/views.py
from decimal import Decimal
from trade.services import (
    position_service,
    settlement_service,
    position_queue_service,
    multicurrency_service
)
```

### Step 2: Modify trade_create() Function

Update the `trade_create()` function to trigger position calculation **after trade is saved**:

```python
def trade_create(request, trade_type=None):
    """Create a new trade (Maker action: Create -> INITIAL).

    AVP position calculation is triggered here based on settle_date:
    - settle_date = today: Position calculated immediately
    - settle_date > today: Trade queued for future settlement
    - settle_date < today: Backdated validation and recalculation
    """
    dropdown_options = trade_dropdown_service.get_all_dropdown_options()

    if request.method == 'POST':
        try:
            user_info = get_user_info(request)

            # Collect form data (existing code)
            trade_data = {
                'trade_type': request.POST.get('trade_type', trade_type or 'BUY'),
                'portfolio_short_name': request.POST.get('portfolio_short_name', '').strip(),
                'security_label': request.POST.get('security_label', '').strip(),
                'trade_date': request.POST.get('trade_date', ''),
                'settle_date': request.POST.get('settle_date', ''),
                'quantity': request.POST.get('quantity', 0),
                'price': request.POST.get('price', 0),
                'commission': request.POST.get('commission', 0),
                'sec_fee': request.POST.get('sec_fee', 0),
                'other_charges': request.POST.get('other_charges', 0),
                # ... rest of form fields ...
            }

            # Validate trade data
            is_valid, errors = trade_kudu_repository.validate_trade_data(trade_data)
            if not is_valid:
                for error in errors:
                    messages.error(request, error)
                return render(request, 'trade/trade_form.html', {...})

            # ============================================================
            # VALIDATE POSITION BEFORE SAVING (for SELL trades)
            # ============================================================
            if trade_data['trade_type'] == 'SELL':
                qty = Decimal(str(trade_data.get('quantity', 0) or 0))
                price = Decimal(str(trade_data.get('price', 0) or 0))

                is_valid, position_errors = position_service.validate_trade_for_position(
                    trade_type='SELL',
                    quantity=qty,
                    price=price,
                    portfolio_id=trade_data['portfolio_short_name'],
                    security_id=trade_data['security_label']
                )

                if not is_valid:
                    for error in position_errors:
                        messages.error(request, error)
                    return render(request, 'trade/trade_form.html', {...})

            # Insert trade (existing code)
            trade_id = trade_kudu_repository.insert_trade(trade_data, created_by=user_info['username'])

            if not trade_id:
                raise Exception("Failed to create trade")

            # ============================================================
            # TRIGGER AVP POSITION CALCULATION (NEW CODE)
            # ============================================================
            position_success, position_message = _trigger_position_calculation(
                trade_data=trade_data,
                trade_id=trade_id,
                updated_by=user_info['username']
            )

            # Audit log (existing code)
            audit_log_kudu_repository.log_action(
                user_id=user_info['user_id'],
                username=user_info['username'],
                user_email=user_info['user_email'],
                action_type='CREATE',
                entity_type='TRADE',
                entity_id=str(trade_id),
                entity_name=f"{trade_data['trade_type']} - {trade_data['security_label']}",
                action_description=f"Created trade. Position: {position_message}",
                new_value=json.dumps(trade_data, default=str),
                # ... rest of audit fields ...
            )

            # Success message with position info
            messages.success(request, f'Trade {trade_id} created. {position_message}')
            return redirect('trade:list')

        except Exception as e:
            messages.error(request, f'Error creating trade: {str(e)}')

    # GET request - render form
    return render(request, 'trade/trade_form.html', {...})


def _trigger_position_calculation(trade_data: dict, trade_id: int, updated_by: str) -> tuple:
    """
    Trigger position calculation based on settlement date.

    Called at trade CREATION (INITIAL status).

    Uses settlement_service to determine processing mode:
    - T+0 (settle_date = today): Process IMMEDIATELY → Position updated now
    - T+1/T+2 (settle_date > today): QUEUE for later → Position updated on settle_date
    - Backdated (settle_date < today): VALIDATE and recalculate chain
    """
    try:
        # Extract trade details
        portfolio_id = trade_data.get('portfolio_short_name', '')
        security_id = trade_data.get('security_label', '')
        trade_type = trade_data.get('trade_type', '')

        quantity = Decimal(str(trade_data.get('quantity', 0) or 0))
        price = Decimal(str(trade_data.get('price', 0) or 0))

        # Calculate total charges
        commission = Decimal(str(trade_data.get('commission', 0) or 0))
        sec_fee = Decimal(str(trade_data.get('sec_fee', 0) or 0))
        other_charges = Decimal(str(trade_data.get('other_charges', 0) or 0))
        charges = commission + sec_fee + other_charges

        trade_date = trade_data.get('trade_date', '')
        settle_date = trade_data.get('settle_date', '')

        # Get currency info for multi-currency support
        security_currency = trade_data.get('currency_code', '')
        portfolio_currency = _get_portfolio_currency(portfolio_id)
        isin = trade_data.get('isin', '')
        security_name = trade_data.get('security_full_name', '')

        # Use settlement service to process based on settle_date
        # This is called at trade CREATION, not at workflow settlement
        success, message, result = settlement_service.process_trade_settlement(
            trade_id=trade_id,
            portfolio_id=portfolio_id,
            security_id=security_id,
            trade_type=trade_type,
            quantity=quantity,
            price=price,
            charges=charges,
            trade_date=trade_date,
            settle_date=settle_date,
            updated_by=updated_by,
            security_currency=security_currency,
            portfolio_currency=portfolio_currency,
            isin=isin,
            security_name=security_name
        )

        return success, message

    except Exception as e:
        logger.error(f"Error triggering position calculation: {str(e)}")
        return False, f"Position calculation error: {str(e)}"


def _get_portfolio_currency(portfolio_id: str) -> str:
    """Get portfolio base currency."""
    try:
        return multicurrency_service.get_portfolio_currency(portfolio_id) or 'USD'
    except:
        return 'USD'
```

### Step 3: Also Update trade_edit() Function

When a trade is edited, if the settle_date or quantity/price changes, we need to recalculate:

```python
def trade_edit(request, trade_id):
    """Edit trade (Maker action: Update -> MODIFIED).

    If settle_date is today and trade values change,
    position will be recalculated.
    """
    # ... existing validation code ...

    if request.method == 'POST':
        try:
            # ... collect updated_data ...

            # Track if position-affecting fields changed
            position_fields = ['quantity', 'price', 'commission', 'sec_fee', 'other_charges', 'settle_date']
            position_changed = any(
                str(updated_data.get(f, '')) != str(trade_data.get(f, ''))
                for f in position_fields
            )

            # Update trade
            success = trade_kudu_repository.update_trade(trade_id, updated_data, user_info['username'])

            if success and position_changed:
                # Re-trigger position calculation with updated values
                merged_data = {**trade_data, **updated_data}
                _trigger_position_calculation(
                    trade_data=merged_data,
                    trade_id=trade_id,
                    updated_by=user_info['username']
                )

            # ... rest of existing code ...
```

---

## Step-by-Step Testing Guide

### Step 1: Create a BUY Trade with T+0 (Same-Day Settlement)

1. Navigate to **Trade** → **Create Trade**
2. Fill in the form:

| Field | Value |
|-------|-------|
| Trade Type | BUY |
| Portfolio | FUND-001 |
| Security | AAPL |
| Quantity | 100 |
| Price | 175.00 |
| Commission | 10.00 |
| Sec Fee | 0.50 |
| Other Charges | 0.00 |
| Trade Date | 2026-03-04 |
| Settle Date | **2026-03-04 (TODAY - T+0)** |

3. Click **Save Trade**
4. **AVP CALCULATION HAPPENS IMMEDIATELY** because settle_date = today
5. Trade status: **INITIAL** (workflow continues independently)
6. Position is already updated in `position_master`!

### Step 2: Verify Position (BEFORE Workflow Completes)

**Position is already calculated** - check immediately after trade creation:

```sql
-- Check position (should show quantity=100, avg_cost=175.105)
SELECT * FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'FUND-001'
  AND security_label = 'AAPL'
  AND status = 'OPEN'
ORDER BY created_at DESC;
```

### Step 3: Continue Workflow (Independent of AVP)

The workflow continues as normal, but **position is already updated**:

1. **Submit for Validation** → PENDING_VALIDATION
2. **Validate Trade** (as Checker) → VALIDATED
3. **Settle Trade** (as Checker) → SETTLED

The workflow settlement is for trade lifecycle management, NOT for position calculation.

### Alternative: Create Trade with T+2 (Future Settlement)

1. Create trade with:

| Field | Value |
|-------|-------|
| Trade Date | 2026-03-04 |
| Settle Date | **2026-03-06 (T+2 - FUTURE)** |

2. Click **Save Trade**
3. **Trade is QUEUED** for settlement on 2026-03-06
4. Position will be calculated when settle_date arrives

Check the queue:
```sql
SELECT * FROM gmp_cis.cis_settlement_queue
WHERE trade_id = <your_trade_id>
  AND status = 'PENDING';
```

### Step 4: Verify Position

Check the position was created:

```sql
-- Check cis_trade_position
SELECT * FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'FUND-001'
  AND security_label = 'AAPL'
  AND status = 'OPEN'
ORDER BY created_at DESC;

-- Check position_master (shared table)
SELECT * FROM gmp_cis.position_master
WHERE portfolio = 'FUND-001'
  AND security_short_name = 'AAPL'
  AND src_system = 'CIS'
ORDER BY etl_insert_ts DESC;
```

---

## Test Scenarios

### Scenario A: T+0 Settlement (Same Day)

```
Trade Date:  2026-03-04
Settle Date: 2026-03-04  (same day)
Result:      Position calculated immediately on settlement
```

### Scenario B: T+2 Settlement (Future)

```
Trade Date:  2026-03-04
Settle Date: 2026-03-06  (T+2)
Result:      Trade queued in cis_settlement_queue
             Background worker processes on settle_date
```

### Scenario C: Backdated Settlement

```
Today:       2026-03-15
Trade Date:  2026-03-01
Settle Date: 2026-03-01  (backdated)
Result:      Validated against month-end limit (Feb 28)
             If valid: Recalculates all positions from Mar 1 to today
```

### Scenario D: Multiple BUY Trades

```
Trade 1: BUY 100 AAPL @ $175.00 + $10 charges
  Position: Qty=100, AVP=$175.10

Trade 2: BUY 50 AAPL @ $180.00 + $5 charges
  Position: Qty=150, AVP=$176.77

Trade 3: BUY 25 AAPL @ $170.00 + $2 charges
  Position: Qty=175, AVP=$175.90
```

### Scenario E: SELL Trade

```
Current:     Qty=175, AVP=$175.90
Trade:       SELL 50 AAPL @ $185.00
Result:      Qty=125, AVP=$175.90 (unchanged)
             Realized P&L = (185-175.90)*50 = $455
```

### Scenario F: Multi-Currency

```
Portfolio:   FUND-SGD (base: SGD)
Security:    AAPL (currency: USD)
Trade:       BUY 100 @ $175.00 (USD)
FX Rate:     USD-SGD = 1.35

Result:
  AVP (Local/USD): $175.00
  AVP (Base/SGD):  S$236.25
```

---

## Position Display in Trade Detail

To show position information in the trade detail page, uncomment the code in `trade_detail()` view:

```python
def trade_detail(request, trade_id):
    # ... existing code ...

    # ENABLE POSITION DISPLAY
    position = None
    if status == TradeKuduRepository.STATUS_SETTLED:
        portfolio = trade_data.get('portfolio_short_name', '')
        security = trade_data.get('security_label', '')
        if portfolio and security:
            position_data = position_service.get_position(portfolio, security)
            if position_data:
                position = PositionWrapper(position_data)

    context = {
        'trade': trade,
        'history': history,
        'position': position,  # Pass to template
        # ... rest of context ...
    }
```

Add `PositionWrapper` class:

```python
class PositionWrapper:
    """Wrapper for position dict to object conversion."""

    def __init__(self, data):
        self.data = data
        self.position_id = data.get('position_id', '')
        self.portfolio_short_name = data.get('portfolio_short_name', '')
        self.security_label = data.get('security_label', '')
        self.quantity = data.get('quantity', 0)
        self.average_cost = data.get('average_cost', 0)
        self.total_cost = data.get('total_cost', 0)
        self.current_price = data.get('current_price', 0)
        self.market_value = data.get('market_value', 0)
        self.unrealized_pnl = data.get('unrealized_pnl', 0)
        self.realized_pnl = data.get('realized_pnl', 0)
        self.status = data.get('status', 'OPEN')
        self.security_currency = data.get('security_currency', '')
        self.portfolio_currency = data.get('portfolio_currency', '')
```

---

## Template Changes

### trade_detail.html - Position Section

Add this section to show position after settlement:

```html
{% if position %}
<!-- Position Impact Section -->
<div class="card mt-4">
    <div class="card-header bg-success text-white">
        <h5 class="mb-0">Position Impact</h5>
    </div>
    <div class="card-body">
        <div class="row">
            <div class="col-md-6">
                <table class="table table-sm">
                    <tr>
                        <th>Quantity:</th>
                        <td>{{ position.quantity|floatformat:2 }}</td>
                    </tr>
                    <tr>
                        <th>Average Cost:</th>
                        <td>{{ position.average_cost|floatformat:8 }}</td>
                    </tr>
                    <tr>
                        <th>Total Cost:</th>
                        <td>{{ position.total_cost|floatformat:2 }}</td>
                    </tr>
                </table>
            </div>
            <div class="col-md-6">
                <table class="table table-sm">
                    <tr>
                        <th>Current Price:</th>
                        <td>{{ position.current_price|floatformat:2 }}</td>
                    </tr>
                    <tr>
                        <th>Market Value:</th>
                        <td>{{ position.market_value|floatformat:2 }}</td>
                    </tr>
                    <tr>
                        <th>Unrealized P&L:</th>
                        <td class="{% if position.unrealized_pnl >= 0 %}text-success{% else %}text-danger{% endif %}">
                            {{ position.unrealized_pnl|floatformat:2 }}
                        </td>
                    </tr>
                    <tr>
                        <th>Realized P&L:</th>
                        <td class="{% if position.realized_pnl >= 0 %}text-success{% else %}text-danger{% endif %}">
                            {{ position.realized_pnl|floatformat:2 }}
                        </td>
                    </tr>
                </table>
            </div>
        </div>
        <div class="text-muted small mt-2">
            Position ID: {{ position.position_id }} |
            Status: {{ position.status }} |
            {% if position.security_currency and position.portfolio_currency %}
            Currency: {{ position.security_currency }} → {{ position.portfolio_currency }}
            {% endif %}
        </div>
    </div>
</div>
{% endif %}
```

---

## Background Worker Setup

For async processing (T+1/T+2 settlements), you need to run the background worker:

### Option 1: Django Management Command

Create `trade/management/commands/run_position_worker.py`:

```python
from django.core.management.base import BaseCommand
from trade.services import position_queue_service

class Command(BaseCommand):
    help = 'Run the position queue background worker'

    def handle(self, *args, **options):
        self.stdout.write('Starting position queue worker...')
        position_queue_service.start_worker()
```

Run with:
```bash
python manage.py run_position_worker
```

### Option 2: Celery Task (if using Celery)

```python
# trade/tasks.py
from celery import shared_task
from trade.services import position_queue_service

@shared_task
def process_position_queue():
    """Process pending position calculations."""
    position_queue_service.process_db_queue()
```

### Option 3: Cron Job

Add to crontab:
```
# Run every 5 minutes
*/5 * * * * cd /path/to/project && python manage.py shell -c "from trade.services import position_queue_service; position_queue_service.process_db_queue()"
```

---

## Monitoring

### Queue Statistics API

Add an API endpoint to monitor queue status:

```python
# trade/views.py

@require_http_methods(["GET"])
def queue_statistics(request):
    """Get position queue statistics."""
    stats = position_queue_service.get_queue_statistics()
    return JsonResponse({
        'pending': stats.get('pending', 0),
        'processing': stats.get('processing', 0),
        'completed': stats.get('completed', 0),
        'failed': stats.get('failed', 0),
        'dead_letter': stats.get('dead_letter', 0),
        'total': stats.get('total', 0)
    })
```

Add URL:
```python
# trade/urls.py
path('api/queue-stats/', views.queue_statistics, name='queue_stats'),
```

---

## Error Handling

### Trade Settlement Errors

If position calculation fails during settlement:
1. Trade is still marked as SETTLED
2. Warning logged to audit
3. Trade queued for retry in position_queue
4. SLA monitoring tracks processing time

### Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| "Insufficient quantity" | SELL qty > position qty | Check position before selling |
| "Backdated settlement not allowed" | Beyond month-end limit | Use valid settle date |
| "Position calculation error" | Database issue | Check logs, retry from queue |
| "No FX rate found" | Missing FX data | Add rate to gmp_cis_sta_dly_fx_rates |

---

## Summary

### Integration Checklist

- [ ] Add imports to `trade/views.py`
- [ ] Modify `trade_settle()` function
- [ ] Add `_trigger_position_calculation()` helper
- [ ] Add `PositionWrapper` class
- [ ] Update `trade_detail()` to show position
- [ ] Add position section to `trade_detail.html`
- [ ] Set up background worker for async processing
- [ ] Add monitoring endpoints

### Files Modified

| File | Changes |
|------|---------|
| `trade/views.py` | Add AVP integration to settle |
| `trade/templates/trade/trade_detail.html` | Position display |
| `trade/urls.py` | Queue stats API |
| `trade/management/commands/run_position_worker.py` | Worker command |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-04 | System | Initial UI integration guide |

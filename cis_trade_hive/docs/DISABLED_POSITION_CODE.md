# Disabled Position Code

This document describes the position tracking functionality that has been disabled in the Trade module.

## Overview

The position tracking feature was designed to track portfolio holdings with multi-currency support (Local/Base currency). It has been disabled but the code remains in place for future re-enablement.

## Disabled Components

### 1. URL Routes (`trade/urls.py`)

**Location:** Lines 37-46

The following URL patterns have been commented out:

```python
# path('positions/', views.position_list, name='position_list'),
# path('positions/<int:position_id>/', views.position_detail, name='position_detail'),
# path('positions/refresh/', views.refresh_positions, name='refresh_positions'),
```

### 2. View Functions (`trade/views.py`)

**Location:** Lines 1041-1139

The following views have been commented out:

- `PositionWrapper` class - Wrapper for position dict to enable template attribute access
- `position_list()` - Lists all positions with summary statistics
- `position_detail()` - Shows details and version history for a single position
- `refresh_positions()` - Refreshes position calculations

**Additional disabled code:** Lines 333-342

Position impact display in trade_detail view has been commented out.

### 3. Sidebar Navigation (`templates/components/sidebar.html`)

**Location:** Lines 97-109

The Positions link in the Trades submenu has been commented out:

```html
{# <li class="nav-item"> #}
{#     <a class="nav-link ..." href="{% url 'trade:position_list' %}"> #}
{#         <i class="bi bi-pie-chart"></i> #}
{#         <span>Positions</span> #}
{#     </a> #}
{# </li> #}
```

### 4. Templates (NOT disabled - kept intact)

The following templates remain in place and can be used when re-enabling:

- `templates/trade/position_list.html` - Position list page
- `templates/trade/position_detail.html` - Position detail page

## How to Re-Enable Position Functionality

To restore position tracking, follow these steps:

### Step 1: Uncomment URL Routes

In `trade/urls.py`, find lines 37-46 and uncomment the position URLs:

```python
# Change from:
# path('positions/', views.position_list, name='position_list'),
# path('positions/<int:position_id>/', views.position_detail, name='position_detail'),
# path('positions/refresh/', views.refresh_positions, name='refresh_positions'),

# To:
path('positions/', views.position_list, name='position_list'),
path('positions/<int:position_id>/', views.position_detail, name='position_detail'),
path('positions/refresh/', views.refresh_positions, name='refresh_positions'),
```

### Step 2: Uncomment View Functions

In `trade/views.py`, find lines 1041-1139 and uncomment:

1. The `PositionWrapper` class
2. The `position_list()` function
3. The `position_detail()` function
4. The `refresh_positions()` function

Also uncomment the position impact code in `trade_detail()` view at lines 333-342.

### Step 3: Uncomment Sidebar Link

In `templates/components/sidebar.html`, find lines 97-109 and uncomment the Positions link:

```html
<!-- Change from Django comment syntax {# ... #} to regular HTML -->
<li class="nav-item">
    <a class="nav-link {% if 'positions' in request.path %}active{% endif %}" href="{% url 'trade:position_list' %}">
        <i class="bi bi-pie-chart"></i>
        <span>Positions</span>
    </a>
</li>
```

### Step 4: Verify

After re-enabling, verify:

1. Run Django check: `python manage.py check`
2. Start the server: `python manage.py runserver`
3. Navigate to `/trade/positions/` to confirm the page loads
4. Check the sidebar shows the Positions link

## Database Tables

The position functionality uses the following Kudu table:

- `gmp_cis.cis_trade_position` - Stores position records with multi-currency support

### Position Table Schema

Key columns:
- `position_id` - Primary key
- `portfolio_short_name` - Portfolio identifier
- `security_label` - Security identifier
- `isin` - ISIN code
- `quantity` - Number of units held
- `security_currency` - Currency of the security
- `portfolio_currency` - Base currency of the portfolio
- `cost_value_local` - Cost in security currency
- `cost_value_base` - Cost in portfolio currency
- `market_value_local` - Market value in security currency
- `market_value_base` - Market value in portfolio currency
- `unrealized_pnl_local` - Unrealized P&L in security currency
- `unrealized_pnl_base` - Unrealized P&L in portfolio currency
- `valuation_date` - Date of valuation
- `src_system` - Source system (CIS, GMP, etc.)

## Related Management Commands

The following management command was created to upload position data:

- `trade/management/commands/upload_amsiceq_positions.py` - Uploads AMSICEQ position records

## Notes

- Templates (`position_list.html`, `position_detail.html`) are kept intact and ready for use
- The repository layer (`trade/repositories/trade_kudu_repository.py`) position methods remain functional
- Position data in Kudu tables is not affected by this disabling

---

Last updated: 2026-02-09

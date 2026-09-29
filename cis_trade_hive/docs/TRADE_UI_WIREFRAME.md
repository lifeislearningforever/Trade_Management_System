# Trade Management System - UI Wireframe

## Overview
This document provides wireframes for the Trade Management module with Buy, Sell, Add Long, Deliver Long, Reduction Basis, Income, Split Transaction, and Notes tabs. Implements Four-Eyes (Maker-Checker) workflow with full audit trail.

---

## 1. Trade List View

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🏠 Dashboard > Trades                                                                    │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  📊 TRADES                                                                               │
│  Manage trades with Four-Eyes principle (Maker-Checker)                                 │
│                                                                                          │
│  ┌──────────────────┐  ┌─────────────────────────┐  ┌──────────────────────────┐        │
│  │ + Create New     │  │ ⏳ Pending Validation    │  │ ✓ Pending Settlement     │        │
│  │   Trade          │  │    [Badge: 5]           │  │   [Badge: 3]             │        │
│  └──────────────────┘  └─────────────────────────┘  └──────────────────────────┘        │
│                                                                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│  🔍 SEARCH & FILTER                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │  Search                     Trade Type           Status                            │ │
│  │  ┌──────────────────────┐  ┌──────────────────┐ ┌──────────────────┐               │ │
│  │  │ 🔍 Deal#, Security...│  │ All Types      ▼│ │ All Statuses   ▼│               │ │
│  │  └──────────────────────┘  └──────────────────┘ └──────────────────┘               │ │
│  │                                                                                    │ │
│  │  Portfolio (Multi-Select)                Security (Multi-Select)                   │ │
│  │  ┌─────────────────────────────────────┐ ┌─────────────────────────────────────┐  │ │
│  │  │ [📋 Select Portfolios...]           │ │ [📋 Select Securities...]           │  │ │
│  │  │ (Click to open modal)               │ │ (Click to open modal)               │  │ │
│  │  └─────────────────────────────────────┘ └─────────────────────────────────────┘  │ │
│  │                                                                                    │ │
│  │  Selected: [Badge: 3 portfolios] [×]      Selected: [Badge: 2 securities] [×]    │ │
│  │                                                                                    │ │
│  │  Trade Date From           Trade Date To                                           │ │
│  │  ┌──────────────────────┐  ┌──────────────────┐                                   │ │
│  │  │ 📅 YYYY-MM-DD        │  │ 📅 YYYY-MM-DD    │                                   │ │
│  │  └──────────────────────┘  └──────────────────┘                                   │ │
│  │                                                                                    │ │
│  │  [🔍 Search]  [✖ Clear]                                                           │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│  TRADE LIST                                                    [📥 Download CSV]        │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │ Type │Portfolio│Security│Trade Date│Settle Date│Qty│Price│Amount│Status │Actions │ │
│  ├──────┼─────────┼────────┼──────────┼───────────┼───┼─────┼──────┼───────┼────────┤ │
│  │ BUY  │UOB-SG   │AAPL    │2024-01-15│2024-01-17 │100│150  │15000 │INITIAL│👁✏📤  │ │
│  │ SELL │UOB-HK   │GOOGL   │2024-01-14│2024-01-16 │50 │140  │7000  │PENDING│👁      │ │
│  │ BUY  │UOB-MY   │MSFT    │2024-01-13│2024-01-15 │200│380  │76000 │SETTLED│👁      │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  Pagination: [First] [Prev] Page 1 of 10 [Next] [Last]                                  │
│                                                                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│  ℹ️ FOUR-EYES WORKFLOW                                                                   │
│  • MAKER: Create→INITIAL, Edit→MODIFIED, Submit→PENDING_VALIDATION, Cancel→CANCELLED   │
│  • CHECKER: Validate→VALIDATED, Reject→CANCELLED, Settle→SETTLED                        │
│  • Makers cannot validate/settle their own trades                                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1A. Portfolio Multi-Select Modal

Purpose: Allow users to select multiple portfolios for filtering trades using OR logic.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         SELECT PORTFOLIOS                                    [X]         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  🔍 Search Portfolios                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ 🔍 Type to search portfolios...                                                     ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Selected: 3 portfolios                                              [Clear Selection]  │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ ☐ │ Portfolio Name     │ Currency │ Manager         │ Status   │ Cash Balance      ││
│  ├───┼────────────────────┼──────────┼─────────────────┼──────────┼───────────────────┤│
│  │ ☑ │ A A ANTHONY SEC    │ SGD      │ John Manager    │ SETTLED  │ 1,250,000.00      ││
│  │ ☑ │ AIIF CP            │ USD      │ Jane Manager    │ SETTLED  │ 2,500,000.00      ││
│  │ ☐ │ AIIF CP II LTD     │ USD      │ Jane Manager    │ SETTLED  │ 3,750,000.00      ││
│  │ ☑ │ AMADIA INVESTME    │ HKD      │ Bob Manager     │ SETTLED  │ 500,000.00        ││
│  │ ☐ │ ASEAN CHINA II     │ CNY      │ Alice Manager   │ SETTLED  │ 8,000,000.00      ││
│  │ ☐ │ ASIA FIXED INCOME  │ SGD      │ John Manager    │ SETTLED  │ 4,200,000.00      ││
│  │ ☐ │ GLOBAL EQUITY FUND │ USD      │ Sarah Manager   │ SETTLED  │ 15,000,000.00     ││
│  │ ...                                                                                  ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Showing 1-20 of 150 portfolios                      [Load More]                        │
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              [Cancel]  [Apply Selection (3)]                     │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Real-time search filtering
- Checkbox selection for multiple portfolios
- Shows portfolio details (Currency, Manager, Status, Cash Balance)
- Selection count badge
- Clear selection button
- Lazy loading with "Load More" for large datasets
- OR logic: Selecting A, B, C shows trades for A OR B OR C

---

## 1B. Security Multi-Select Modal

Purpose: Allow users to select multiple securities for filtering trades using OR logic.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         SELECT SECURITIES                                    [X]         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  🔍 Search Securities                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ 🔍 Search by name, ISIN, or ticker...                                               ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Selected: 2 securities                                              [Clear Selection]  │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ ☐ │ Security Name             │ Type   │ ISIN         │ Ticker │ Currency │ Price  ││
│  ├───┼───────────────────────────┼────────┼──────────────┼────────┼──────────┼────────┤│
│  │ ☑ │ Reyes, Torres and Bishop  │ EQUITY │ US1234567890 │ RTB    │ USD      │ 150.25 ││
│  │ ☐ │ Rose, Winters and Morrison│ EQUITY │ US0987654321 │ RWM    │ USD      │ 220.50 ││
│  │ ☑ │ Thomas, Bruce and Williams│ EQUITY │ GB1234567890 │ TBW    │ GBP      │ 180.00 ││
│  │ ☐ │ Cooke-Garcia              │ BOND   │ DE0987654321 │ CGR    │ EUR      │ 95.00  ││
│  │ ☐ │ Buck Ltd                  │ EQUITY │ HK1234567890 │ BUCK   │ HKD      │ 45.75  ││
│  │ ☐ │ Alpha Technologies Inc    │ EQUITY │ US5555555555 │ ATI    │ USD      │ 89.99  ││
│  │ ☐ │ Beta Financial Corp       │ BOND   │ US6666666666 │ BFC    │ USD      │ 102.50 ││
│  │ ...                                                                                  ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Showing 1-20 of 500 securities                      [Load More]                        │
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              [Cancel]  [Apply Selection (2)]                     │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

**Features:**
- Search by security name, ISIN, or ticker symbol
- Checkbox selection for multiple securities
- Shows security details (Type, ISIN, Ticker, Currency, Price)
- Selection count badge
- Clear selection button
- Lazy loading with "Load More" for large datasets
- OR logic: Selecting A, B, C shows trades for A OR B OR C

---

## 1C. Multi-Select Filter Behavior

### Filter Logic
```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  FILTER LOGIC EXAMPLE                                                                    │
│                                                                                          │
│  Selected Portfolios: [A A ANTHONY SEC], [AIIF CP], [AMADIA INVESTME]                   │
│  Selected Securities: [Reyes, Torres and Bishop], [Thomas, Bruce and Williams]         │
│                                                                                          │
│  SQL Generated:                                                                          │
│  WHERE (portfolio_short_name IN ('A A ANTHONY SEC', 'AIIF CP', 'AMADIA INVESTME'))     │
│    AND (security_label IN ('Reyes, Torres and Bishop', 'Thomas, Bruce and Williams'))   │
│                                                                                          │
│  Result: Shows trades matching ANY of the selected portfolios                           │
│          AND ANY of the selected securities                                              │
│                                                                                          │
│  • Within Portfolio filter: OR logic (Portfolio A OR B OR C)                            │
│  • Within Security filter: OR logic (Security X OR Y OR Z)                              │
│  • Between filters: AND logic (Portfolios AND Securities AND Status AND...)            │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Selected Items Display
```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  Portfolio Filter Display:                                                               │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ [A A ANTHONY SEC ×] [AIIF CP ×] [AMADIA INVESTME ×]        [📋 Select] [Clear All] ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  • Click × on individual badge to remove single selection                               │
│  • Click "Clear All" to remove all selections                                            │
│  • Click "Select" to open modal and modify selections                                   │
│  • Badges are truncated if too many (e.g., "+5 more")                                   │
│                                                                                          │
│  When many items selected:                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ [3 Portfolios Selected]  [📋 Modify]  [Clear All]                                   ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1D. API Endpoints for Multi-Select

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/trade/api/portfolios-detailed/` | GET | Returns portfolios with full details for modal |
| `/trade/api/securities-detailed/` | GET | Returns securities with full details for modal |

Query Parameters:
- `search`: Filter by name/ISIN/ticker
- `limit`: Number of results (default: 100)
- `offset`: Pagination offset

Response Format (Portfolios):
```json
{
  "results": [
    {
      "portfolio_short_name": "A A ANTHONY SEC",
      "portfolio_full_name": "A A ANTHONY SEC",
      "currency": "SGD",
      "manager": "John Manager",
      "cash_balance": "1250000.00",
      "status": "SETTLED"
    }
  ],
  "count": 150
}
```

Response Format (Securities):
```json
{
  "results": [
    {
      "security_label": "Reyes, Torres and Bishop",
      "security_full_name": "Reyes, Torres and Bishop",
      "security_type": "EQUITY",
      "isin": "US1234567890",
      "ticker": "RTB",
      "currency_code": "USD",
      "current_price": "150.25",
      "issuer": "Reyes Group",
      "status": "ACTIVE"
    }
  ],
  "count": 500
}
```

---

## 2. Trade Create/Edit Form (Main Layout with Tabs)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🏠 Dashboard > Trades > Create New Trade                                                 │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ➕ CREATE NEW TRADE                                                                     │
│  All fields marked with * are required                                                  │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │ ┌─────┐ ┌─────┐ ┌────────┐ ┌────────────┐ ┌───────────────┐ ┌──────┐ ┌─────────┐  │ │
│  │ │ Buy │ │Sell │ │Add Long│ │Deliver Long│ │Reduction Basis│ │Income│ │Split Txn│  │ │
│  │ └─────┘ └─────┘ └────────┘ └────────────┘ └───────────────┘ └──────┘ └─────────┘  │ │
│  │ ┌───────┐                                                                          │ │
│  │ │ Notes │                                                                          │ │
│  │ └───────┘                                                                          │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  [ACTIVE TAB CONTENT - See individual tab wireframes below]                             │
│                                                                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                           [✖ Cancel]    [💾 Save Trade]                          │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. BUY Tab (Part 1 - Core Fields)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 📋 BASIC INFORMATION                                                                     │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Portfolio Short Name *              Portfolio Full Name (Auto)                          │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select Portfolio            ▼  │ │ [Auto-populated based on selection]             ││
│  │ (Select2 Dropdown)             │ │ (Read-only)                                      ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Security Label *                    Security Full Name (Auto)     Security Type (Auto) │
│  ┌─────────────────────────────────┐ ┌───────────────────────────┐ ┌──────────────────┐│
│  │ Search Security...          ▼  │ │ [Auto-populated]          │ │ [Auto-populated] ││
│  │ (Select2 with Search)          │ │ (Read-only)               │ │ (Read-only)      ││
│  └─────────────────────────────────┘ └───────────────────────────┘ └──────────────────┘│
│                                                                                          │
│  Status *                                                                                │
│  ┌─────────────────────────────────┐                                                    │
│  │ Select Status               ▼  │  Options: Trade Status dropdown values             │
│  └─────────────────────────────────┘                                                    │
│                                                                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ 📅 DATE & QUANTITY                                                                       │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Trade Date *                        Settle Date *                                       │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 📅 YYYY-MM-DD                   │ │ 📅 YYYY-MM-DD                                   ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Quantity *                          Face Value                                          │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Number of units traded          │ │ Nominal value per unit                          ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ 💰 PRICING & COSTS                                                                       │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Price *                             Commission                                          │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 💵 Price per unit               │ │ 💵 Broker commission                            ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Accrued Interest (Calculated)       Sec Fee                                             │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ [Auto-calculated, read-only]    │ │ 💵 Regulatory/security fee                      ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Other Charges                       Total Amount (Calculated)                           │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 💵 Other charges                │ │ [Auto-calculated: Qty×Price+Fees, read-only]   ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. BUY Tab (Part 2 - Additional Fields)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🏦 GENERAL LEDGER & ACCOUNTING                                                           │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Open/Close Position *               Extension                                           │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Open                        ▼  │ │ Select Extension                            ▼  ││
│  │ (Open/Close dropdown)          │ │ (Extension dropdown)                            ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Brokers *                           Broker Name *                                       │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select Broker               ▼  │ │ Select Broker Name                          ▼  ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  GL Fund Type *                      GL Cost Centre *                                    │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select GL Fund Type         ▼  │ │ Select GL Cost Centre                       ▼  ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  GL Account Code *                   Contract Ref                                        │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select GL Account Code      ▼  │ │ Reference number for contract                   ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ 📊 FX & DEALING                                                                          │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Open FX Rate *                      Curr Dealing                                        │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ FX rate at open                 │ │ Currency dealing amount                         ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Open Dealing                        Input TAX(OTH)                                      │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Open dealing amount             │ │ Other tax input                                 ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Qty Entitled                        FD Receipt                                          │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Quantity entitled               │ │ Fixed deposit receipt                           ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Org Pur Date *                      Lot                                                 │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 📅 Original purchase date       │ │ Lot size                                        ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ 📋 POST-TRADE INFO (Output/Calculated)                                                   │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Selling Rule *                      Cash Balance *                                      │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select Selling Rule         ▼  │ │ [Auto-calculated or dropdown]                  ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Custodian (Auto)                    Amor/Accr Method (Auto)                             │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ [Auto-populated from Portfolio] │ │ [Auto-populated, Amortisation method]          ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Lots Held (Output)                  Quantity Held (Calculated)                          │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ [Auto-calculated post-trade]    │ │ [Auto-calculated post-trade]                   ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Remarks                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                                                                                     ││
│  │ Enter any additional comments or remarks...                                         ││
│  │                                                                                     ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. User Defined Fields (UDF) Section - Trade

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🔧 USER DEFINED FIELDS (UDF)                                                             │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Fund Type *                         Section 31/26                                       │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select Fund Type            ▼  │ │ Select Section                              ▼  ││
│  │ (Equity, Bond, etc.)           │ │ (Regulatory section dropdown)                   ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Sub Custodian *                     Disclosure Req                                      │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select Sub Custodian        ▼  │ │ ☐ Yes  ☑ No                                    ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Counter Pledged                     Revision Code                                       │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ ☐ Yes  ☑ No                    │ │ Select Revision Code                        ▼  ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  UOBN/UOBN-HK *                      Income/Exp Type *                                   │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select UOBN                 ▼  │ │ Select Income/Exp Type                      ▼  ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Currency Hedge                                                                          │
│  ┌─────────────────────────────────┐                                                    │
│  │ ☐ Yes  ☑ No                    │                                                    │
│  └─────────────────────────────────┘                                                    │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. SELL Tab

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 📉 SELL TRADE                                                                            │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  [Same fields as BUY tab with the following differences:]                               │
│                                                                                          │
│  • Trade Type: SELL (pre-selected, read-only)                                           │
│  • Open/Close Position: Typically "Close"                                               │
│  • Additional validation: Cannot sell more than held quantity                           │
│  • Shows current holding quantity for reference                                          │
│                                                                                          │
│  Current Holdings Display:                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ ℹ️ Current Holdings for Selected Security                                           ││
│  │ Portfolio: UOB-SG | Security: AAPL | Qty Held: 500 | Avg Cost: 145.50              ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Realized P&L (Calculated)                                                               │
│  ┌─────────────────────────────────┐                                                    │
│  │ [Auto-calculated on sell]       │                                                    │
│  └─────────────────────────────────┘                                                    │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. ADD LONG Tab

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 📈 ADD LONG POSITION                                                                     │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Purpose: Add to existing long position without creating new deal                       │
│                                                                                          │
│  Select Existing Position *                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ 🔍 Search existing positions to add to...                                       ▼  ││
│  │ Shows: Portfolio | Security | Current Qty | Avg Price                              ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Additional Quantity *               Additional Price *                                  │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Quantity to add                 │ │ Price per unit                                  ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Trade Date *                        Settle Date *                                       │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 📅 YYYY-MM-DD                   │ │ 📅 YYYY-MM-DD                                   ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  [Standard GL, FX, UDF fields as in BUY tab]                                            │
│                                                                                          │
│  Position Summary (After Add):                                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ Current Qty: 500  +  Add Qty: 100  =  New Qty: 600                                 ││
│  │ New Avg Cost: [Calculated weighted average]                                         ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. DELIVER LONG Tab

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 📤 DELIVER LONG (Transfer Out)                                                           │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Purpose: Transfer/deliver securities from portfolio (e.g., corporate action, transfer) │
│                                                                                          │
│  Select Position to Deliver *                                                            │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ 🔍 Search positions...                                                          ▼  ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Delivery Quantity *                 Delivery Type *                                     │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Quantity to deliver             │ │ Select Type                                 ▼  ││
│  └─────────────────────────────────┘ │ (Transfer, Corporate Action, Settlement, etc.) ││
│                                       └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Delivery Date *                     Counterparty                                        │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 📅 YYYY-MM-DD                   │ │ Select Counterparty                         ▼  ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Reference Number                    Remarks                                             │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ External reference              │ │ Delivery notes                                  ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  [Standard GL, UDF fields]                                                               │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. REDUCTION BASIS Tab

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 📊 REDUCTION BASIS                                                                       │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Purpose: Adjust cost basis due to return of capital, partial redemption, etc.          │
│                                                                                          │
│  Select Position *                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ 🔍 Search positions for basis reduction...                                      ▼  ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Reduction Type *                    Reduction Amount *                                  │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select Type                 ▼  │ │ Amount of reduction per unit                    ││
│  │ (Return of Capital, Amortization,│ └─────────────────────────────────────────────────┘│
│  │  Write-down, etc.)              │                                                    │
│  └─────────────────────────────────┘                                                    │
│                                                                                          │
│  Effective Date *                    Units Affected                                      │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 📅 YYYY-MM-DD                   │ │ Number of units (default: all)                  ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Cost Basis Impact:                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ Current Cost Basis: $145.50  →  New Cost Basis: $140.50  (Reduction: $5.00/unit)   ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  [Standard GL, UDF fields]                                                               │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. INCOME Tab

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 💵 INCOME RECORDING                                                                      │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Purpose: Record dividend, interest, or other income from securities                    │
│                                                                                          │
│  Select Position *                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ 🔍 Search positions for income recording...                                     ▼  ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Income Type *                       Income/Exp Type *                                   │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select Type                 ▼  │ │ Select Category                             ▼  ││
│  │ (Dividend, Interest, Premium,  │ │ (From UDF dropdown)                             ││
│  │  Distribution, etc.)           │ └─────────────────────────────────────────────────┘│
│  └─────────────────────────────────┘                                                    │
│                                                                                          │
│  Ex-Date                             Record Date                                         │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 📅 YYYY-MM-DD                   │ │ 📅 YYYY-MM-DD                                   ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Pay Date *                          Amount Per Unit *                                   │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 📅 YYYY-MM-DD                   │ │ 💵 Income per unit                              ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Units Entitled                      Gross Amount (Calculated)                           │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ [Auto or manual]                │ │ [Units × Amount Per Unit]                       ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Withholding Tax                     Net Amount (Calculated)                             │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 💵 WHT amount                   │ │ [Gross - WHT]                                   ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  [Standard GL, UDF fields]                                                               │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. SPLIT TRANSACTION Tab

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🔀 SPLIT TRANSACTION                                                                     │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Purpose: Record stock splits, reverse splits, or lot splits                            │
│                                                                                          │
│  Select Position *                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ 🔍 Search positions for split...                                                ▼  ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Split Type *                        Split Ratio *                                       │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Select Type                 ▼  │ │ New : Old (e.g., 2:1 for 2-for-1 split)        ││
│  │ (Stock Split, Reverse Split,   │ │ ┌─────────┐ : ┌─────────┐                       ││
│  │  Lot Split)                    │ │ │    2    │   │    1    │                       ││
│  └─────────────────────────────────┘ │ └─────────┘   └─────────┘                       ││
│                                       └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Effective Date *                    Ex-Date                                             │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ 📅 YYYY-MM-DD                   │ │ 📅 YYYY-MM-DD                                   ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Before/After Summary:                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ BEFORE SPLIT                      AFTER SPLIT                                       ││
│  │ ─────────────────────────────     ─────────────────────────────                     ││
│  │ Quantity: 100                     Quantity: 200 (×2)                                ││
│  │ Price: $200.00                    Price: $100.00 (÷2)                               ││
│  │ Total Value: $20,000              Total Value: $20,000 (unchanged)                  ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  [Standard GL, UDF fields]                                                               │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. NOTES Tab

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 📝 TRADE NOTES                                                                           │
│ ─────────────────────────────────────────────────────────────────────────────────────── │
│                                                                                          │
│  Purpose: Add notes, attachments, and comments to trade                                 │
│                                                                                          │
│  Notes                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                                                                                     ││
│  │ Enter detailed notes about this trade...                                           ││
│  │                                                                                     ││
│  │                                                                                     ││
│  │                                                                                     ││
│  │                                                                                     ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Internal Reference                  External Reference                                  │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────────────┐│
│  │ Internal tracking number        │ │ External/client reference                       ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────────────┘│
│                                                                                          │
│  Trade History / Audit Trail (Read-only in Edit mode):                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ Date/Time           │ User        │ Action        │ Changes                         ││
│  │─────────────────────┼─────────────┼───────────────┼─────────────────────────────────││
│  │ 2024-01-15 10:30:00 │ john.doe    │ CREATE        │ Initial creation                ││
│  │ 2024-01-15 11:00:00 │ jane.smith  │ VALIDATE      │ Validated trade                 ││
│  │ 2024-01-15 14:00:00 │ mike.jones  │ SETTLE        │ Settled to active               ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 13. Trade Detail View (View Mode)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🏠 Dashboard > Trades > Trade Detail                                                     │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  👁 VIEW TRADE                                                    Status: [VALIDATED]   │
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │  [✏ Edit]  [📤 Submit]  [✓ Validate]  [✗ Reject]  [💼 Settle]  [🗑 Cancel]      │   │
│  │  (Buttons shown based on status and user role)                                   │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │ ┌─────┐ ┌─────┐ ┌────────┐ ┌────────────┐ ┌───────────────┐ ┌──────┐ ┌─────────┐  │ │
│  │ │ Buy │ │Sell │ │Add Long│ │Deliver Long│ │Reduction Basis│ │Income│ │Split Txn│  │ │
│  │ └─────┘ └─────┘ └────────┘ └────────────┘ └───────────────┘ └──────┘ └─────────┘  │ │
│  │ ┌───────┐ ┌───────┐                                                                │ │
│  │ │ Notes │ │ Audit │                                                                │ │
│  │ └───────┘ └───────┘                                                                │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  [ALL FIELDS DISPLAYED AS READ-ONLY WITH VALUES]                                        │
│                                                                                          │
│  Workflow Actions (Bottom of page):                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                                  │   │
│  │  Status: PENDING_VALIDATION                                                      │   │
│  │  Created by: john.doe on 2024-01-15 10:30:00                                     │   │
│  │  Modified by: john.doe on 2024-01-15 10:45:00                                    │   │
│  │                                                                                  │   │
│  │  [✓ Validate Trade]  [✗ Reject Trade]                                           │   │
│  │  (Only visible to Checker, not the Maker)                                        │   │
│  │                                                                                  │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 14. Pending Validation Queue (Checker View)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🏠 Dashboard > Trades > Pending Validation                                               │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ⏳ PENDING VALIDATION QUEUE                                                             │
│  Trades awaiting checker approval (Four-Eyes Principle)                                 │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │ Type │Portfolio│Security│Trade Date│Amount  │Maker     │Submitted  │Actions       │ │
│  ├──────┼─────────┼────────┼──────────┼────────┼──────────┼───────────┼──────────────┤ │
│  │ BUY  │UOB-SG   │AAPL    │2024-01-15│$15,000 │john.doe  │10:30 AM   │[👁][✓][✗]   │ │
│  │ SELL │UOB-HK   │GOOGL   │2024-01-14│$7,000  │jane.smith│09:15 AM   │[👁][✓][✗]   │ │
│  │ BUY  │UOB-MY   │MSFT    │2024-01-13│$76,000 │bob.jones │Yesterday  │[👁][✓][✗]   │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  Legend:                                                                                 │
│  👁 View Details  ✓ Validate  ✗ Reject                                                  │
│                                                                                          │
│  ⚠️ Note: You cannot validate trades you created (Four-Eyes Principle)                  │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 15. Pending Settlement Queue

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🏠 Dashboard > Trades > Pending Settlement                                               │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ✓ PENDING SETTLEMENT QUEUE                                                              │
│  Validated trades awaiting final settlement                                              │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │ Type │Portfolio│Security│Trade Date│Amount  │Validated By│Validated At│Actions    │ │
│  ├──────┼─────────┼────────┼──────────┼────────┼────────────┼────────────┼───────────┤ │
│  │ BUY  │UOB-SG   │AAPL    │2024-01-15│$15,000 │mike.checker│11:00 AM   │[👁][💼]   │ │
│  │ SELL │UOB-HK   │GOOGL   │2024-01-14│$7,000  │sarah.admin │10:30 AM   │[👁][💼]   │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  Legend:                                                                                 │
│  👁 View Details  💼 Settle (Finalize)                                                  │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 16. Audit Trail View

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 🏠 Dashboard > Trades > Trade Detail > Audit Trail                                       │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  📋 AUDIT TRAIL - Trade #12345                                                           │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│  │ Timestamp           │ User        │ Action   │ Field Changed │ Old Value│ New Value│ │
│  ├─────────────────────┼─────────────┼──────────┼───────────────┼──────────┼──────────┤ │
│  │ 2024-01-15 10:30:00 │ john.doe    │ CREATE   │ -             │ -        │ -        │ │
│  │ 2024-01-15 10:35:00 │ john.doe    │ UPDATE   │ Quantity      │ 100      │ 150      │ │
│  │ 2024-01-15 10:35:00 │ john.doe    │ UPDATE   │ Price         │ 145.00   │ 146.50   │ │
│  │ 2024-01-15 10:40:00 │ john.doe    │ SUBMIT   │ Status        │ INITIAL  │ PENDING  │ │
│  │ 2024-01-15 11:00:00 │ mike.checker│ VALIDATE │ Status        │ PENDING  │ VALIDATED│ │
│  │ 2024-01-15 14:00:00 │ mike.checker│ SETTLE   │ Status        │ VALIDATED│ SETTLED  │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                          │
│  [📥 Export Audit Log]  [🔍 Filter by Date Range]                                       │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 17. Validation/Rejection Modal

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         VALIDATE TRADE                                    [X]           │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  Trade Summary:                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │ Type: BUY | Portfolio: UOB-SG | Security: AAPL                                      ││
│  │ Quantity: 100 | Price: $150.00 | Total: $15,000.00                                  ││
│  │ Trade Date: 2024-01-15 | Settle Date: 2024-01-17                                    ││
│  │ Created by: john.doe on 2024-01-15 10:30:00                                         ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  Validation Comments (Optional):                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                                                                                     ││
│  │ Enter any comments about this validation...                                         ││
│  │                                                                                     ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              [Cancel]  [✓ Confirm Validation]                    │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         REJECT TRADE                                      [X]           │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│  ⚠️ You are about to reject this trade                                                  │
│                                                                                          │
│  Trade Summary: [Same as above]                                                          │
│                                                                                          │
│  Rejection Reason * (Required):                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐│
│  │                                                                                     ││
│  │ Please provide reason for rejection...                                             ││
│  │                                                                                     ││
│  └─────────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              [Cancel]  [✗ Confirm Rejection]                     │   │
│  └──────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 18. Status Badge Legend

| Status | Badge Color | Description |
|--------|-------------|-------------|
| INITIAL | Gray/Secondary | New trade, not yet submitted |
| MODIFIED | Blue/Info | Trade has been edited after creation |
| PENDING_VALIDATION | Yellow/Warning | Submitted, awaiting checker approval |
| VALIDATED | Primary/Blue | Approved by checker, awaiting settlement |
| SETTLED | Green/Success | Fully processed, active trade |
| CANCELLED | Dark/Black | Trade cancelled/rejected |

---

## 19. Field Behavior Summary

| Field Type | Behavior |
|------------|----------|
| Input | User enters value manually |
| Output | Auto-populated from related entity (read-only) |
| Calculated | Auto-computed based on other fields (read-only) |
| Dropdown | User selects from predefined list |
| Select2 | Searchable dropdown for large lists (Portfolio, Security) |
| Date | Date picker input |
| Boolean | Checkbox or Yes/No toggle |

---

## 20. Responsive Considerations

- **Desktop**: Full form layout with 2-3 columns
- **Tablet**: 2 columns, collapsible sections
- **Mobile**: Single column, accordion-style sections, sticky action buttons

---

## 21. Accessibility Notes

- All form fields have associated labels
- Required fields marked with asterisk (*) and `aria-required="true"`
- Error messages linked to fields with `aria-describedby`
- Tab navigation follows logical order
- Color contrast meets WCAG 2.1 AA standards
- Screen reader announcements for status changes

---

## Document Version
- Version: 1.1
- Created: 2024-01-15
- Updated: 2026-01-13
- Author: System Design Team

### Changelog
- **v1.1 (2026-01-13)**: Added Multi-Select Modal functionality for Portfolio and Security filters
  - Section 1A: Portfolio Multi-Select Modal wireframe
  - Section 1B: Security Multi-Select Modal wireframe
  - Section 1C: Multi-Select Filter Behavior documentation
  - Section 1D: API Endpoints for Multi-Select
  - Updated Trade List View to show multi-select filter buttons

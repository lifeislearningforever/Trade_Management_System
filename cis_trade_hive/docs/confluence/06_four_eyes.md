# Four-Eyes Workflow (Maker-Checker)

> **Audience:** User, BA, SA, Developer, Support
> **Read time:** ~8 minutes

---

## What Is Four-Eyes?

**Four-Eyes** (also called Maker-Checker) is a financial control principle: no critical action can be performed by a single person. Every important operation requires a second person to review and approve it.

The name comes from the idea that important decisions need "four eyes" looking at them — two from the maker, two from the checker.

In CIS, this applies to:
- **Trades** — a trader creates, a checker validates
- **Portfolios** — a maker creates, a checker approves

---

## The Core Rules

1. **You cannot approve your own work.** Ever. The system enforces this — even if you have the Checker role.
2. **A record is not active until approved.** DRAFT/PENDING records don't appear in position calculations or reports.
3. **Every approval action is logged.** Who approved it, when, and any comments.
4. **Rejection sends it back** — with a reason — so the maker can correct and resubmit.

---

## Trade Maker-Checker Flow

```
┌──────────────────────────────────────────────────────────────────┐
│  MAKER (Trader)                                                  │
│                                                                  │
│  1. Creates trade: status = INITIAL                              │
│  2. Reviews, optionally edits: status = MODIFIED                 │
│  3. Clicks "Submit for Validation": status = PENDING_VALIDATION  │
└─────────────────────────┬────────────────────────────────────────┘
                          │ Trade is now locked for editing
                          │
┌─────────────────────────▼────────────────────────────────────────┐
│  CHECKER (different person)                                      │
│                                                                  │
│  4a. Reviews trade details                                       │
│      Clicks "Validate" → status = VALIDATED                      │
│      → Trade proceeds to settlement                              │
│                                                                  │
│  4b. Finds an issue                                              │
│      Clicks "Reject" + types reason → status = CANCELLED         │
│      → Maker is notified (they can create a new trade)           │
└──────────────────────────────────────────────────────────────────┘
                          │
        (after validation)│
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│  SYSTEM (automatic)                                              │
│                                                                  │
│  5. Settlement processing runs (EOD or T+0)                      │
│     status = SETTLED                                             │
│     Position (AVP) automatically updated                         │
└──────────────────────────────────────────────────────────────────┘
```

---

## Portfolio Maker-Checker Flow

```
┌──────────────────────────────────────────────────────────────────┐
│  MAKER                                                           │
│                                                                  │
│  1. Creates portfolio: status = DRAFT                            │
│  2. Submits: status = PENDING_APPROVAL                           │
└─────────────────────────┬────────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────────┐
│  CHECKER                                                         │
│                                                                  │
│  3a. Approves → status = APPROVED → ACTIVE                       │
│      Trades can now be entered against this portfolio            │
│                                                                  │
│  3b. Rejects → status = REJECTED                                 │
│      Maker can edit and resubmit                                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## What Gets Stored for Each Transition

Every status change records:

| Field | What it captures |
|-------|-----------------|
| `submitted_by` | Who submitted for approval |
| `submitted_at` | Timestamp of submission |
| `submission_comments` | Optional maker's note |
| `reviewed_by` | Who approved or rejected |
| `reviewed_at` | Timestamp of decision |
| `review_comments` | Checker's reason (required on rejection) |

This creates a full audit record of the decision — who, when, and why.

---

## Where to Find Pending Items

### As a Checker:
- **Trade → Pending Validation** — all trades awaiting your review
- **Portfolio → Pending Approval** — all portfolios awaiting your review

Items are sorted by submission time (oldest first).

---

## What Users Cannot Do

| Action | Rule |
|--------|------|
| Approve own trade | Not allowed — system checks `created_by == approver` |
| Edit a PENDING_VALIDATION trade | Not allowed — locked while under review |
| Edit a SETTLED trade | Not allowed — immutable once settled |
| Settle a trade without approval | Not allowed — must be VALIDATED first |
| Create a trade against a DRAFT portfolio | Not allowed — portfolio must be ACTIVE |

---

## Rejection vs Cancellation

| | Rejection | Cancellation |
|--|-----------|-------------|
| Who does it | Checker (during validation) | Can also happen other ways |
| Status | CANCELLED | CANCELLED |
| Can maker resubmit? | No — must create new trade | No |
| Why it happens | Checker found an issue | Various reasons |

A cancelled trade is never physically deleted. It stays in the history with status `CANCELLED` and is excluded from active views.

---

## For Developers: Where Four-Eyes Is Implemented

| Layer | File | What it does |
|-------|------|-------------|
| Service | `trade/services/trade_service.py` | `submitted_by != reviewer` check |
| Service | `portfolio/services/portfolio_service.py` | Same for portfolios |
| View | `trade/views.py` | Only checker role can reach approve endpoint |
| Middleware | `core/middleware/permission_middleware.py` | `trade-approve` permission required for approve URL |
| Template | `templates/trade/trade_detail.html` | Approve/Reject buttons only shown to checkers |
| Database | `cis_trade`, `cis_portfolio` | `submitted_by`, `reviewed_by`, `reviewed_at`, `review_comments` columns |

### Self-Approval Check (Service Layer)
```python
def validate_trade(trade, reviewing_user):
    if trade.created_by == reviewing_user.username:
        raise PermissionDenied(
            "Cannot validate your own trade. "
            "A different user must review this trade."
        )
    # proceed with validation...
```

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| Checker cannot see the Validate button | Do they have `trade-approve` permission in their RBAC group? |
| "Cannot approve own trade" error | The checker and maker are the same user — a different person must approve |
| Trade stuck in PENDING_VALIDATION | No checker has reviewed it yet, or all checkers lack the permission |
| Rejection comment required | System enforces a comment on rejection — checker must provide a reason |
| Portfolio not available for trade | Check portfolio status — it must be ACTIVE (not DRAFT or PENDING_APPROVAL) |

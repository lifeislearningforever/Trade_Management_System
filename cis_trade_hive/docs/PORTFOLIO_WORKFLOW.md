# Portfolio Maker-Checker Workflow

**Document:** CisTrade Portfolio Workflow
**Version:** 1.0
**Date:** 2026-06-25
**Purpose:** SA / UAT review of current Maker-Checker flow and open design questions

---

## 1. Status Lifecycle

```
CREATE
  │
  ▼
INITIAL ──────────────────────────────────────────────────► CANCELLED
  │  (Maker: Cancel)                                              │
  │                                                               │
  │ (Maker: Edit)                                                 │ (Maker: Reactivate)
  ▼                                                               │
MODIFIED ──────────────────────────────────────────────────► CANCELLED
  │  (Maker: Cancel)                                              │
  │                                                               └──► INITIAL (reset)
  │ (Maker: Submit)
  ▼
PENDING_VALIDATION ─────────────────────────────────────────► CANCELLED
  │  (Maker: Cancel OR Checker: Reject — both go to CANCELLED)
  │
  │ (Checker: Validate/Approve)
  ▼
VALIDATED ──────────────────────────────────────────────────► (no cancel allowed)
  │
  │ (Checker: Settle)
  ▼
SETTLED  ◄── Final active state (is_active = true)
```

---

## 2. Maker Actions

| Action | From Status | To Status | Who | Notes |
|--------|-------------|-----------|-----|-------|
| **Create** | — | INITIAL | Maker | New portfolio, not active |
| **Edit** | INITIAL, MODIFIED, PENDING_VALIDATION, CANCELLED | MODIFIED | Maker | CIS records only |
| **Submit** | INITIAL, MODIFIED | PENDING_VALIDATION | Maker | Sends to checker queue |
| **Cancel** | INITIAL, MODIFIED, PENDING_VALIDATION | CANCELLED | Maker | Permanent unless reactivated |
| **Reactivate** | CANCELLED | INITIAL | Maker | Resets all cancellation fields, ready to resubmit |

---

## 3. Checker Actions

| Action | From Status | To Status | Who | Notes |
|--------|-------------|-----------|-----|-------|
| **Validate (Approve)** | PENDING_VALIDATION | VALIDATED | Checker | Four-Eyes: must be different user from submitter |
| **Reject** | PENDING_VALIDATION | **CANCELLED** | Checker | ⚠️ See design issue below |
| **Settle** | VALIDATED | SETTLED | Checker | Sets `is_active = true`, portfolio becomes active |

---

## 4. Four-Eyes Principle

- The user who **submits** a portfolio **cannot validate or reject** it
- Enforced in code: `portfolio_validate` view checks `submitted_by == current_user` and blocks with error
- Not enforced on Cancel or Reactivate (Maker self-service actions)

---

## 5. Where the Buttons Appear

### Detail Page (`/portfolio/<name>/`)

| Button | Condition |
|--------|-----------|
| Edit | status in (INITIAL, MODIFIED, PENDING_VALIDATION, CANCELLED) AND CIS record |
| Submit | status in (INITIAL, MODIFIED) AND CIS record |
| Cancel | status in (INITIAL, MODIFIED, PENDING_VALIDATION) AND CIS record |
| Reactivate | status == CANCELLED AND CIS record |
| **Approve** | status == PENDING_VALIDATION |
| **Reject** | status == PENDING_VALIDATION |
| Settle | status == VALIDATED |

### Pending Validation Queue (`/portfolio/pending-validation/`)

| Button | Shown when |
|--------|-----------|
| View | Always |
| Validate | `view_type == 'validation'` (i.e. PENDING_VALIDATION tab) |
| Reject | `view_type == 'validation'` (i.e. PENDING_VALIDATION tab) |
| Settle | `view_type == 'settlement'` (i.e. VALIDATED tab) |

---

## 6. ⚠️ Open Design Issues (For SA Review)

### Issue 1 — Reject goes to CANCELLED (same as Maker Cancel)

**Current behaviour:**
When a Checker clicks **Reject**, the portfolio status becomes `CANCELLED` — exactly the same state as when a Maker cancels it.

**Problem:**
- The Maker cannot distinguish between "I cancelled it myself" and "Checker rejected it"
- The rejection reason is stored in `cancel_reason` column (shared with maker cancellation)
- After rejection, the Maker must **Reactivate** → gets back to `INITIAL` and resubmits
- There is no notification to the Maker that their submission was rejected

**Proposed fix (SA to confirm):**
Add a separate `REJECTED` status:
```
PENDING_VALIDATION ──(Checker: Reject)──► REJECTED
REJECTED ──(Maker: Edit & Resubmit)──► PENDING_VALIDATION
```
Benefits: Maker sees clearly it was rejected; rejection reason visible in workflow; no confusion with Maker's own cancellation.

---

### Issue 2 — Pending Validation queue shows INITIAL portfolios (PORTIARP-7415)

**Observed in UAT:**
The Pending Validation page (`/portfolio/pending-validation/`) is displaying portfolios with status `INITIAL`, not `PENDING_VALIDATION`.

**Root cause investigation needed:**
- The code query correctly filters `WHERE status = 'PENDING_VALIDATION'`
- In UAT Kudu, either:
  a. The `status` column values are stored differently (case/encoding issue), OR
  b. Makers submitted portfolios but the Kudu `UPDATE` on submit did not persist (Impala write failure)

**Impact:** Checker sees portfolios they cannot approve/reject (they are still INITIAL). Clicking Validate/Reject fails silently with "Cannot validate portfolio with status INITIAL".

**Action required:**
- Run `SELECT name, status FROM gmp_cis.cis_portfolio WHERE status = 'PENDING_VALIDATION'` directly in UAT Impala shell to verify data
- Check Impala application logs for any UPDATE errors during submit

---

### Issue 3 — Maker can Edit while Pending Validation

**Current behaviour:**
A Maker can edit a portfolio even after submitting it (`PENDING_VALIDATION` is in `MAKER_EDITABLE_STATUSES`). If they edit, status changes to `MODIFIED`.

**Question for SA:** Is this intended? Typically in Four-Eyes workflows, once submitted the record is locked until the checker acts. Allowing mid-submission edits can confuse the checker who may be reviewing an older version.

**Options:**
- A: Lock editing once in `PENDING_VALIDATION` (remove from `MAKER_EDITABLE_STATUSES`)
- B: Keep current behaviour — edit allowed, status reverts to `MODIFIED` pulling it out of checker queue
- C: Allow edit but notify checker that submission was updated

---

### Issue 4 — No SETTLED → CANCELLED / SETTLED → MODIFIED path

**Current behaviour:**
Once a portfolio reaches `SETTLED` (active), there is no way to deactivate, close, or modify it from the UI.

**Question for SA:** Do we need:
- A "Close Portfolio" action (SETTLED → CLOSED/INACTIVE)?
- A "Modify Active Portfolio" flow (requires re-approval)?

---

## 7. Current Status → Allowed Actions Matrix

| Status | Maker: Edit | Maker: Submit | Maker: Cancel | Maker: Reactivate | Checker: Validate | Checker: Reject | Checker: Settle |
|--------|:-----------:|:-------------:|:-------------:|:-----------------:|:-----------------:|:---------------:|:---------------:|
| INITIAL | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| MODIFIED | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| PENDING_VALIDATION | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ |
| VALIDATED | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| SETTLED | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| CANCELLED | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |

> Note: All Maker actions require `portfolio-edit WRITE` permission.
> All Checker actions require `portfolio-approval WRITE` permission.
> Both restricted to `src_system = CIS` records only (GMP records are read-only).

---

## 8. Audit Trail

Every workflow action is logged to `gmp_cis.cis_audit_log` with:

| Action | Logged As |
|--------|-----------|
| Create | `CREATE` |
| Edit | `UPDATE` |
| Submit | `SUBMIT` |
| Validate/Approve | `VALIDATE` |
| Reject | `REJECT` |
| Cancel | `CANCEL` |
| Settle | `SETTLE` |
| Reactivate | `REACTIVATE` |

Fields logged: `user_id`, `username`, `timestamp`, `old_value` (JSON), `new_value` (JSON), `ip_address`, `user_agent`.

---

## 9. Questions for SA Sign-off

| # | Question | Options |
|---|----------|---------|
| Q1 | Should Checker Reject go to `CANCELLED` or a new `REJECTED` status? | CANCELLED (current) / New REJECTED status |
| Q2 | Should Maker be allowed to edit a portfolio in `PENDING_VALIDATION`? | Yes (current) / No — lock it |
| Q3 | Is there a need to close/deactivate a `SETTLED` portfolio? | Yes — add CLOSED status / No |
| Q4 | Should Maker receive a notification (in-app or email) when portfolio is rejected? | Yes / No |
| Q5 | UAT data issue — are portfolios being submitted but status not updating in Kudu? | Needs DBA to verify via Impala shell |

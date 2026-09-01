# Trade Cancel — Maker/Checker (Four-Eyes) Gap

**Status:** Open — for SA review, not yet fixed.

## Question

Does trade cancellation enforce the Four-Eyes (maker-checker) principle?

## Answer

Yes, structurally — but enforcement has a gap compared to the normal trade
validation flow.

## Flow (`cis_trade_hive/trade/views.py`)

1. **Maker** — `trade_cancel()` (line ~1300): sets `status=MODIFIED`,
   `is_deleted=true`, `cancel_reason`/`cancelled_by` immediately, reverses the
   position chain right away, logs `CANCEL_REQUEST`. Trade now sits in
   **PENDING_CANCELLATION** awaiting a checker.
2. **Checker approves** — `trade_approve_cancellation()` (line ~1371):
   finalises `status → CANCELLED`, logs `CANCEL_APPROVE`.
3. **Checker rejects** — `trade_reject_cancellation()` (line ~1419): restores
   `is_deleted=false`, reverts status to the pre-cancel value read from trade
   history, logs `CANCEL_REJECT`.

Same overall shape as the ordinary INITIAL → VALIDATED Four-Eyes flow.

## The gap

The ordinary trade-validation flow explicitly blocks self-approval —
`trade_validate()` (line ~1197-1214):

```python
# Four-eyes check — checker cannot be the same person who created the trade
created_by = trade_data.get('created_by', '')
if created_by and created_by == user_info['username']:
    messages.error(request, 'Four-eyes principle: You cannot validate your own trade.')
    return redirect('trade:detail', trade_id=trade_id)
```

**`trade_approve_cancellation()` and `trade_reject_cancellation()` have no
equivalent check.** Nothing stops the same user who submitted the cancel
request (`cancelled_by`) from also approving or rejecting it themselves.

Also: `trade_cancel()` (the maker action) is missing the `@require_login`
decorator that both checker views (`trade_approve_cancellation`,
`trade_reject_cancellation`) carry.

## Suggested fix (pending SA sign-off)

- Add the same maker≠checker guard to both checker views, comparing
  `cancelled_by` (or `trade_data.get('cancelled_by')`) against the acting
  user, mirroring the `trade_validate()` check.
- Add `@require_login` to `trade_cancel()`.

## Files involved

- `cis_trade_hive/trade/views.py` — `trade_cancel`, `trade_approve_cancellation`,
  `trade_reject_cancellation`, `trade_validate` (reference implementation of
  the check to mirror).
- `cis_trade_hive/trade/repositories/trade_kudu_repository.py` —
  `submit_for_cancellation`, `approve_cancellation`, `reject_cancellation`.

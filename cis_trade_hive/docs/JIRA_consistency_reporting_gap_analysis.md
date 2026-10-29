# Gap Analysis — "Ensuring Consistency in Definitions and Reporting Figures across All Reports"

JIRA: Defect, Severity 2 - High, Component: CIS - Functional, Applications: CIS - Corporate
Investment System, Root Cause Category: Req - Conversion Specification Updated

Date: 2026-08-19

## JIRA requirements vs. current codebase state

| # | Requirement | Status | Notes |
|---|---|---|---|
| 1 | Unrealised P/L (FC) and (LC) = "zero" for Investment Type (portfolio static) = Subsidiary co, Associated co, Restructured Equity-New | **Partial** | Zeroed for `ASSOC`/`SUBSI` investment types in `trade/services/position_service.py` (`_is_equity_method_security`, ~lines 1905-1920; applied at 486-490, 1240-1274, 1298). No handling found anywhere for "Restructured Equity-New" — not referenced in trade/, reference_data/, or security/. |
| 2 | Provision (FC) and (LC) only apply to Subsidiary co / Associated co; all other Investment Types default to zero | **Not found** | `provision_fc`/`provision_lc` fields exist and are carried forward (`position_service.py` ~579-580, 615-616, 820-821, 888-889) but nothing gates provision to specific investment types or zeroes it for others. |
| 3 | Definitions: FC = security-denominated currency, LC = portfolio currency, SGD = official reporting currency | **Implicit only** | Only expressed via `_fc`/`_lc` field-naming convention throughout `position_service.py` / `multicurrency_service.py`. No formalized/documented mapping exists in code or config. |
| 4 | REVALUED: Cost(LC) = Cost(FC) × historical avg FX; Provision(LC) = Provision(FC) × historical avg FX. NON_REVALUED: both use as-at-reporting FX | **Partial** | Reval status resolution exists (`_get_portfolio_revaluation_status`, ~1992-2024, defaults to REVALUED) and is applied to Cost/position values (502-535, 736-776, 1228-1307). Provision is **not** FX-recomputed by reval status at all — it's only carried forward, so the Provision(LC) half of this rule is unimplemented. |
| 5 | Market Value (LC) = Market Value (FC) × as-at-reporting FX rate, regardless of revalued status | **Implemented** | `position_service.py` ~1274, 1298 — market_value_lc consistently uses current FX rate. |
| 6 | NBV: Cost(FC) − Prov(FC) + Unrealised PL(FC) = NBV(FC); same for LC | **Implemented** | Explicit formula in `position_service.py` ~582-584 and ~1482-1493. |
| 7 | Reporting SGD = direct translation from LC × as-at-reporting FX rate | **Not found** | No SGD-specific reporting-currency translation logic located anywhere. |
| 8 | GL account number: 10th digit = inside/outside (IOS) code (counterparty residence). IOS applies only to UOBS portfolios: '1' = outside Singapore, '0' = in Singapore. All other portfolios default to '0' | **Not found** | No `gl_account_number` / `gl_account` field exists anywhere in the codebase. "UOBS" only appears as an RBAC `default_entity` value (`core/repositories/rbac_admin_repository.py`, `core/repositories/acl_repository_v2.py`) — unrelated to GL accounts. |
| 9 | Apply consistency in these definitions/figures across all reports | **Not verifiable** | No dedicated "reports" module exists. Position figures live in `trade/views_position.py` / `trade/repositories/position_repository.py`; whether every export path applies the same rules wasn't independently confirmed since there's no single reporting layer to check. |

## Summary

Two pieces already exist as side effects of prior AVP (average-price-position) work:
- **Req 5** (Market Value LC translation) — implemented.
- **Req 6** (NBV formula) — implemented.

**Req 4** (revalued/non-revalued FX handling) is implemented for Cost but not for Provision.

**Req 1** (equity-method zeroing) covers Subsidiary/Associated but not "Restructured Equity-New."

**Reqs 2, 3, 7, 8** are effectively unimplemented (Req 3 exists only as an implicit naming convention, not enforced definitions).

**Req 9** can't be assessed until a reporting layer/inventory of "all reports" is identified.

**Conclusion:** This ticket is not implemented. The core asks — provision zeroing by investment type, "Restructured Equity-New" handling, SGD reporting translation, and the GL account IOS digit — are all missing and represent real, unscoped implementation work, not something already done that just needs verification.

## Open questions for SA

1. Where does "Restructured Equity-New" come from as a portfolio-static Investment Type value — is it a new enum value to add to `cis_security`/portfolio static data, or does it already exist under a different code we should map?
2. Is there a canonical list of "all reports" this consistency rule must apply to? No single reporting layer exists in the current codebase (no `reports/` module) — figures are computed per-view/per-export today.
3. Does `gl_account_number` already exist as a field somewhere upstream (e.g. sourced from GMP/Kudu tables not yet surfaced in this app), or does this app need to originate/derive it?
4. Should Provision(LC) revaluation (historical avg FX vs as-at-reporting FX, matching req 4) be added now alongside the provision-zeroing logic (req 2), since both touch the same `provision_fc`/`provision_lc` code paths?

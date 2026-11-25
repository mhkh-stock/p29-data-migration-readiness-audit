# P29 — Migration Reconciliation Report (SAMPLE)

**Client (SAMPLE):** Ravi Traders, Lahore — wholesale distributor moving from the legacy desktop billing system (BillPro 2009) to a new cloud ERP (CloudERP) · **Audit date:** 25 Nov 2026 · **Status: SAMPLE delivery on synthetic data**

## Verdict: CONDITIONAL GO

The move can go ahead **once the conditions below are met and the migration is re-run**. Nothing in the target is wrong — every paisa reconciles and the target holds no orphans, duplicates or mismatches — but 134 of 810 source rows (16.54%) cannot migrate as they stand, and they carry PKR 2,836,335.35 of sales value. Cutting over with them left behind would silently lose that history.

## Headline numbers (SAMPLE)

- **810 source rows → 676 target rows · 134 quarantined · readiness 83.46%**
- Customers: 150 → 137 (13 quarantined) · Products: 60 → 51 (9 quarantined) · Sales: 600 → 488 (112 quarantined, sales readiness 81.33%)
- Sales money: PKR 16,666,459.35 in the source file (parseable amounts) = PKR 13,830,124.00 migrated + PKR 2,836,335.35 quarantined — reconciled to the paisa
- Credit limits: PKR 138,187,000.00 migrated — reconciled to the paisa
- Mapping coverage: 21/21 source columns (100%) — 20 loaded, 1 explicitly excluded (legacy stock_qty, a point-in-time figure)
- Target checks: 0 orphans · 0 amount mismatches · 0 duplicates — all zero

## Row-count reconciliation

| Table | Source | Target | Quarantined | Readiness |
|---|---|---|---|---|
| customers | 150 | 137 | 13 | 91.33% |
| products | 60 | 51 | 9 | 85.00% |
| sales | 600 | 488 | 112 | 81.33% |
| **Total** | **810** | **676** | **134** | **83.46%** |

## Money reconciliation

| Measure | Source | Migrated | Quarantined | Reconciled? |
|---|---|---|---|---|
| Sales amounts | PKR 16,666,459.35 | PKR 13,830,124.00 | PKR 2,836,335.35 | Yes — to the paisa |
| Credit limits | PKR 138,187,000.00 | PKR 138,187,000.00 | PKR 0.00 | Yes — to the paisa |

Credit limits reconcile with a zero quarantined column because the four unparseable limits were never numbers — there was nothing to sum. The sales gap is fully explained: every quarantined sales row's parseable amount is in the quarantined column, and the two columns add back to the source total.

## Quarantine by reason — the must-fix list

| Source | Reason | Rows | What it means |
|---|---|---|---|
| customers | duplicate_cust_code | 6 | Two customer rows share one code — keep the first, fix or drop the copy |
| customers | unparseable_credit_limit | 4 | Credit limit is not a number — confirm the real limit with the customer |
| customers | unparseable_since_date | 3 | Customer start date is not a real date — confirm it from the paper file |
| products | missing_or_zero_price | 5 | Product has no usable price — set the selling price before the move |
| products | duplicate_prod_code_normalised | 4 | Two product rows share one code once hyphens are removed — keep the first, fix the copy |
| sales | orphan_prod_code | 58 | Sale points at a product code that is not in the migrated products — add the product, or correct the code |
| sales | orphan_cust_code | 33 | Sale points at a customer code that is not in the migrated customers — add the customer, or correct the code |
| sales | duplicate_bill_line | 5 | Exact copy of an earlier bill line — keep the first, drop the copy |
| sales | amount_mismatch | 5 | Bill amount does not equal quantity × unit price — re-check the bill, do not guess |
| sales | unparseable_or_zero_amount | 4 | Bill amount is blank, zero, negative or not a number — confirm the real amount |
| sales | unparseable_bill_date | 4 | Bill date is not a real date — confirm it from the paper bill |
| sales | unparseable_qty | 3 | Quantity is not a whole number — confirm it from the paper bill |

## The cascade finding — fix 12 master rows, unblock 77 sales lines

Of the 112 quarantined sales lines, 77 are **knock-on orphans**: rows that are perfectly clean themselves, but point at a customer or product whose own master row failed migration. Seven customer codes (3 bad dates + 4 bad credit limits) and five product codes (missing prices) never reached the target — and every sale that mentioned them is blocked with them. Fixing those 12 master rows and re-running unblocks all 77 lines at once, with no bill-by-bill work. That is the cheapest fix in this audit, and it should be done first.

## Conditions for cutover (all must hold, then re-run)

1. **Fix the 12 master rows** — 3 customer dates, 4 customer credit limits, 5 product prices. Re-run: this alone unblocks 77 sales lines.
2. **Fix or drop the duplicate codes** — 6 customer codes and 4 product codes appear twice; keep the first occurrence, correct or delete the copy.
3. **Resolve the 14 planted orphan codes** — 8 customer codes and 6 product codes that exist nowhere in the master files: add the missing master row or correct the code on the bill.
4. **Re-check the 16 bad bill values** — 4 dates, 3 quantities, 4 amounts, 5 amount mismatches — against the paper bills. Never guess a date, a quantity or an amount.
5. **Re-run the migration and confirm the new verdict is GO** — zero quarantined rows, money still reconciled to the paisa.

## What migrated with a warning (11 rows — no action blocks cutover)

- 6 customers with no phone — migrated with phone NULL; collect the numbers after cutover.
- 2 customers with an invalid status — migrated as Active; confirm the real status after cutover.
- 3 products with no category — migrated as 'Uncategorised'; assign the real category after cutover.

## Method (plainly stated)

Source files were loaded verbatim into staging, validated row by row in Python (`src/run_migration.py` — the single source of truth for the rules), and transformed by the SQL in `sql/mapping.sql` into the CloudERP star-lite schema (`dim_customer`, `dim_product`, `fact_sales`). Every rejected row is in `quarantine` with its reason; every step is in `migration_log`. The reconciliation queries the client keeps are in `sql/reconciliation.sql` — each returns its expected value on a clean migration. 70 defects were planted in the sample data on purpose (57 that quarantine a row, 13 planted as warnings — 11 of them migrated with a warning and 2 were quarantined as duplicates before the warning was reached); the audit re-found all of them, plus the knock-on orphans the planting did not name. Nothing in this report is typed — every number is recomputed from the database.

## Limits, stated upfront

- **SAMPLE data.** Ravi Traders, the customers, the products and the bills are invented to stand in for a real wholesaler's legacy export. The method is real; the business is not.
- **One migration, three files, six months.** The sample covers Jan–Jun 2026 sales only. A real move has its own tables, its own master lists and its own defect mix — the scripts take the client's files and column names as inputs, but the defect list here is the set this sample was built to show.
- **The audit never invents data.** A missing price, date, quantity or amount is quarantined, not guessed. A 'fixed' migration that guesses those is worse than a flagged one.
- **Stock quantities do not migrate.** The legacy `stock_qty` is a point-in-time figure, not a master attribute — it is documented in the lineage doc and left out of CloudERP on purpose. Stock must be counted, not copied.


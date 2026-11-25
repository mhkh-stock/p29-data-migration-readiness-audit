# P29 — Data Migration Readiness Audit: will anything break when we move systems?

**Client (SAMPLE):** Ravi Traders, Lahore — wholesale distributor moving
from the legacy desktop billing system (BillPro 2009) to a new cloud ERP
(CloudERP) · **Audit date:** 25 Nov 2026 · **Status: SAMPLE delivery on synthetic data**
**Tools:** SQL (SQLite, star-lite schema) · Python (stdlib migration + validation) · Excel (live formulas)
**Deliverable:** `outputs/migration_readiness_workbook_SAMPLE.xlsx` +
`outputs/migration_readiness_report_SAMPLE.pdf` + `outputs/lineage.md` — a
go / no-go verdict with the exact rows that must be fixed before cutover

> ⚠️ **What this is and is not.** Ravi Traders, the customers, the
> products and the 600 bills are synthetic SAMPLE data, generated in
> this repo with a fixed seed — not a real wholesaler's files. What is
> real is the method: the same source→target mapping, the same
> row-count + value reconciliation, the same quarantine and lineage
> run unchanged on the client's real legacy export, and every number
> in the report is recomputed from the loaded data, never typed.

## Business question it answers

> "Will anything break when we move systems?"

A wholesaler about to leave a 17-year-old desktop billing system for a
cloud ERP is not asking for a dashboard — it is asking whether the new
system will open on Monday with the right customers, the right prices
and the right sales history. This delivery answers it with a mapping of
every source column to its target, a reconciliation that proves the
money moves to the paisa, a quarantine of every row that cannot move
yet (with its reason), and a verdict: **CONDITIONAL GO** — the move can
go ahead once 134 rows are fixed and the migration is re-run.

## The method (plainly stated)

**Ingest:** 3 legacy CSVs — `customers_legacy.csv` (150 rows),
`products_legacy.csv` (60), `sales_legacy.csv` (600) — loaded verbatim
into staging, exactly as the old system exported them: duplicate codes,
mixed date formats, amounts as text with commas, orphan bill lines.

**Map:** 21 of 21 source columns mapped in `sql/mapping.sql` (100%
coverage) — 20 loaded into the CloudERP star-lite schema
(`dim_customer`, `dim_product`, `fact_sales`), 1 explicitly excluded
with its reason: legacy `stock_qty` is a point-in-time count, not a
master attribute, and must be counted at cutover, not copied.

**Validate:** every row checked in Python (`src/run_migration.py`,
the single source of truth for the rules) in a fixed order — intrinsic
row defects first (bad date, quantity, amount, amount mismatch), then
references. A sale is quarantined as an orphan only if it is otherwise
clean, so the reason always says what to fix first on that row.

**Quarantine:** 134 rows failed and never reached the target — 57 from
defects planted in the sample on purpose, 77 knock-on orphans (clean
rows blocked because their customer or product failed to migrate).
They sit in `quarantine` with the reason, so the team fixes the source
instead of arguing about the new system.

**Reconcile:** row counts and money, source → staging → target, in
`sql/reconciliation.sql` — the queries the client keeps. Sales money
reconciles to the paisa: PKR 16,666,459.35 in the source =
PKR 13,830,124.00 migrated + PKR 2,836,335.35 quarantined.

**Lineage:** `outputs/lineage.md` traces every target column back to
its legacy file, row and rule — so when a number in CloudERP looks
wrong, the team finds exactly where it came from.

**Limits, stated upfront:** this is SAMPLE data — a fictional
wholesaler, Jan–Jun 2026 sales only. A real move has its own tables,
its own master lists and its own defect mix; the scripts take the
client's files as inputs, but the defect list here is the set this
sample was built to show. The audit never invents a price, date,
quantity or amount — a missing value is quarantined, not guessed.

## What is inside

| File | What it does |
|---|---|
| `outputs/migration_readiness_workbook_SAMPLE.xlsx` | The deliverable: Cover (headline numbers, live) + Mapping (21 columns) + Reconciliation (counts + money, all formulas) + Quarantine (134 rows, filterable) + Go-No-Go (verdict, readiness, must-fix list with COUNTIFs) |
| `outputs/migration_readiness_report_SAMPLE.pdf` | 2-page report: verdict, headline numbers, quarantine by reason, the cascade finding, conditions for cutover |
| `outputs/reconciliation_report.md` | Findings report: verdict, reconciliation tables, must-fix list, method, limits |
| `outputs/lineage.md` | Lineage doc: flow (Mermaid) + table lineage + column lineage + what is deliberately not migrated |
| `outputs/lineage_diagram.png` | Rendered lineage diagram (matplotlib render, not a screenshot) |
| `outputs/quarantine.csv` | One row per rejected row: source table, row number, key, reason, detail |
| `outputs/migration_log.csv` | Every migration step, with rows in / out / quarantined |
| `outputs/reconciliation_summary.json` | Machine-readable audit summary |
| `data/raw/customers_legacy.csv` (150 rows) | The legacy customer file, as exported |
| `data/raw/products_legacy.csv` (60 rows) | The legacy product file, as exported |
| `data/raw/sales_legacy.csv` (600 rows) | The legacy sales file, as exported |
| `data/raw/defect_manifest.json` | The planted-defect manifest (counts + source rows) the audit is checked against |
| `data/processed/migration.db` | The built database: staging + target + mapping + log + quarantine (NOT committed; rebuilds from the scripts) |
| `data/processed/dim_customer.csv` / `dim_product.csv` / `fact_sales.csv` | The target tables as CSVs (137 / 51 / 488 rows) |
| `data/processed/migration_warnings.json` | The 11 rows that migrated with a warning |
| `data/README.md` | Data dictionary + the planted defects, by design |
| `sql/schema.sql` | Staging + target star-lite schema + mapping / log / quarantine tables |
| `sql/mapping.sql` | The 21-column mapping table + the transform SQL |
| `sql/reconciliation.sql` | The 10 reconciliation queries the client keeps |
| `src/generate_data.py` | Generates the 3 SAMPLE legacy files (seed 29, deterministic) |
| `src/run_migration.py` | The migration: load → validate → transform → log + quarantine |
| `src/analyze.py` | Headline numbers + reconciliation report + lineage doc, recomputed from the database |
| `src/build_workbook.py` | Builds the workbook: 5 sheets, live formulas |
| `src/build_report.py` | Builds the 2-page report PDF + lineage diagram |
| `src/checks.py` | Verification suite — 162 automated checks, all passing (incl. LibreOffice recalc) |
| `requirements.txt` | Pinned: `openpyxl==3.1.2`, `reportlab==5.0.1`, `matplotlib==3.6.3` (Python 3.12) |

## How it fits together

```
data/raw/customers_legacy.csv (150) ──▶ stg_customers ──▶ valid (137) ──▶ dim_customer (137)
data/raw/products_legacy.csv  (60)  ──▶ stg_products  ──▶ valid (51)  ──▶ dim_product  (51)
data/raw/sales_legacy.csv     (600) ──▶ stg_sales     ──▶ valid (488) ──▶ fact_sales   (488)
        (src/run_migration.py: load -> validate -> transform, sql/mapping.sql)
                                  │                         │
                                  ▼                         ▼
                          quarantine (134, with reason)   migration_log (7 steps)
                                  │                         │
                                  ▼                         ▼
               src/analyze.py ──▶ reconciliation_report.md + lineage.md + summary.json
                                  │
                                  ▼
               src/build_workbook.py ──▶ migration_readiness_workbook_SAMPLE.xlsx
               src/build_report.py   ──▶ migration_readiness_report_SAMPLE.pdf (2 pages)
                                  ▲ src/checks.py verifies all of it (incl. LibreOffice recalc)
```

## Headline numbers (SAMPLE — Ravi Traders, Jan–Jun 2026)

- **810 source rows → 676 target rows · 134 quarantined · readiness 83.46%**
- **Customers 150 → 137 · Products 60 → 51 · Sales 600 → 488 (sales readiness 81.33%)**
- **Sales money PKR 16,666,459.35 = PKR 13,830,124.00 migrated + PKR 2,836,335.35 quarantined — reconciled to the paisa**
- **Credit limits PKR 138,187,000.00 migrated — reconciled to the paisa**
- **Mapping coverage 21/21 (100%) · target: 0 orphans · 0 mismatches · 0 duplicates**
- **70 defects planted (57 that quarantine a row, 13 warnings) — all re-found, plus 77 knock-on orphans the planting did not name**

## Row-count reconciliation

| Table | Source | Target | Quarantined | Readiness |
|---|---|---|---|---|
| customers | 150 | 137 | 13 | 91.33% |
| products | 60 | 51 | 9 | 85.00% |
| sales | 600 | 488 | 112 | 81.33% |
| **Total** | **810** | **676** | **134** | **83.46%** |

## Money reconciliation

| Measure | Source (parseable) | Migrated | Quarantined | Reconciled? |
|---|---|---|---|---|
| Sales amounts | PKR 16,666,459.35 | PKR 13,830,124.00 | PKR 2,836,335.35 | Yes — to the paisa |
| Credit limits | PKR 138,187,000.00 | PKR 138,187,000.00 | PKR 0.00 | Yes — to the paisa |

Credit limits reconcile with a zero quarantined column because the four
unparseable limits were never numbers — there was nothing to sum. The
sales gap is fully explained: every quarantined sales row's parseable
amount is in the quarantined column, and the two columns add back to
the source total.

## Quarantine by reason

| Source | Reason | Rows |
|---|---|---|
| customers | duplicate_cust_code | 6 |
| customers | unparseable_credit_limit | 4 |
| customers | unparseable_since_date | 3 |
| products | missing_or_zero_price | 5 |
| products | duplicate_prod_code_normalised | 4 |
| sales | orphan_prod_code | 58 |
| sales | orphan_cust_code | 33 |
| sales | duplicate_bill_line | 5 |
| sales | amount_mismatch | 5 |
| sales | unparseable_or_zero_amount | 4 |
| sales | unparseable_bill_date | 4 |
| sales | unparseable_qty | 3 |
| **Total** | | **134** |

## The cascade finding — fix 12 master rows, unblock 77 sales lines

Of the 112 quarantined sales lines, 77 are **knock-on orphans**: rows
that are perfectly clean themselves, but point at a customer or product
whose own master row failed migration. Seven customer codes (3 bad
dates + 4 bad credit limits) and five product codes (missing prices)
never reached the target — and every sale that mentioned them is blocked
with them. Fixing those 12 master rows and re-running unblocks all 77
lines at once, with no bill-by-bill work. That is the cheapest fix in
this audit, and it should be done first.

## Conditions for cutover

1. **Fix the 12 master rows** — 3 customer dates, 4 credit limits, 5 product prices.
2. **Fix or drop the duplicate codes** — 6 customer codes and 4 product codes appear twice.
3. **Resolve the 14 planted orphan codes** — 8 customer codes and 6 product codes that exist nowhere in the master files.
4. **Re-check the 16 bad bill values** — 4 dates, 3 quantities, 4 amounts, 5 amount mismatches — against the paper bills. Never guess.
5. **Re-run the migration and confirm the verdict is GO** — zero quarantined rows, money still reconciled to the paisa.

## Same logic, four ways — and they must agree

The headline numbers exist in four forms: the legacy CSVs, the SQL
database, the workbook's formulas, and the report PDF. `src/checks.py`
recomputes all four from the raw files independently and compares them —
a mistake in any one shows up as a failure — including an independent
re-implementation of the whole validation that must reproduce the
quarantine table row for row. The workbook's formulas were also
recalculated in LibreOffice: every total matches the recompute exactly,
with zero error values.

## Reproduce it (2 minutes)

```bash
pip install -r requirements.txt
python3 src/generate_data.py   # 3 SAMPLE legacy files -> data/raw/
python3 src/run_migration.py   # staging -> validate -> target -> data/processed/migration.db
python3 src/analyze.py         # headline numbers -> outputs/reconciliation_summary.json + report + lineage
python3 src/build_workbook.py  # outputs/migration_readiness_workbook_SAMPLE.xlsx
python3 src/build_report.py    # outputs/migration_readiness_report_SAMPLE.pdf (2 pages) + lineage diagram
python3 src/checks.py          # verification suite — expect all passing
```

To reuse it for a real client: put their three legacy exports in place
of the demo files (same column names, or update `sql/mapping.sql` to
their names) and re-run steps 2–6 — the quarantine, the report and the
workbook rebuild themselves from the new rows, and the 10 reconciliation
queries in `sql/reconciliation.sql` stay with the client for the next
migration. The `.db` file is never committed; it rebuilds from the scripts.

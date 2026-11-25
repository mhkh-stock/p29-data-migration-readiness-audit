# Data — P29 Data Migration Readiness Audit

## Source

**Synthetic SAMPLE data, generated in this repo** — 3 legacy CSVs for
the fictional wholesaler "Ravi Traders, Lahore", made by
`src/generate_data.py` (seed 29, deterministic: re-running it
regenerates byte-identical files). The business, the customers, the
products and the bills are invented to stand in for a real wholesaler's
legacy export from BillPro 2009. Nothing here is a real business's data.

| File | Rows | What it is |
|---|---|---|
| `raw/customers_legacy.csv` | 150 | The legacy customer file, as exported: code, name, phone, city, credit limit (text with commas), since date (mixed formats), status |
| `raw/products_legacy.csv` | 60 | The legacy product file, as exported: code (inconsistent hyphens), name, category, unit price (text with commas), unit, stock qty |
| `raw/sales_legacy.csv` | 600 | The legacy sales file, Jan–Jun 2026: bill no, bill date (mixed formats), customer code, product code, qty, unit price, amount, tax |
| `raw/defect_manifest.json` | — | The planted-defect manifest (counts + source rows) the audit is checked against |
| `processed/migration.db` | — | The built database (staging + target + mapping + log + quarantine — **NOT committed**; rebuilds from the scripts) |
| `processed/dim_customer.csv` | 137 | The target customer dimension |
| `processed/dim_product.csv` | 51 | The target product dimension |
| `processed/fact_sales.csv` | 488 | The target sales fact |
| `processed/migration_warnings.json` | 11 | Rows that migrated with a warning (blank phone, invalid status, blank category) |

The `_SAMPLE` suffix on the deliverables marks this as demo data — the
migration, the reconciliation and the verdict are the deliverable.

## Data dictionary — `raw/customers_legacy.csv`

| Column | Type | Meaning |
|---|---|---|
| `cust_code` | text | Legacy customer code (`C-001` … `C-150`); 6 rows repeat an earlier code on purpose — they are duplicates the migration quarantines |
| `cust_name` | text | Customer name |
| `phone` | text | Phone (`03xx-xxxxxxx`); 8 rows leave it blank on purpose — they migrate as NULL (warning) |
| `city` | text | Lahore / Karachi / Faisalabad / Rawalpindi / Multan / Gujranwala / Sialkot / Peshawar / Islamabad / Hyderabad |
| `credit_limit` | text | Credit limit in PKR as text with commas (`"1,095,000"`); 4 rows carry `TBD`, `n/a`, `1,2x,000` or blank on purpose |
| `since_date` | text | Customer since date in mixed formats (`DD/MM/YYYY`, `YYYY-MM-DD`, `DD-Mon-YYYY`); 3 rows carry an impossible or blank date on purpose |
| `status` | text | Active / Inactive; 2 rows carry `maybe` / `X` on purpose — they migrate as Active (warning) |

## Data dictionary — `raw/products_legacy.csv`

| Column | Type | Meaning |
|---|---|---|
| `prod_code` | text | Legacy product code (`P-001` … `P-060`); 4 rows drop the hyphen (`P012`) on purpose — they collide with an existing code once normalised |
| `prod_name` | text | Product name |
| `category` | text | Electronics / Home & Kitchen / Groceries / Clothing / Hardware; 3 rows leave it blank on purpose — they migrate as `Uncategorised` (warning) |
| `unit_price` | text | Unit price in PKR as text with commas; 5 rows leave it blank or `0` on purpose |
| `uom` | text | Unit of measure (`pcs` / `box` / `set`) |
| `stock_qty` | text | Legacy stock count — a point-in-time figure, deliberately NOT migrated (see lineage.md) |

## Data dictionary — `raw/sales_legacy.csv`

| Column | Type | Meaning |
|---|---|---|
| `bill_no` | text | Bill number (`B-1001` … `B-1600`); 5 rows are exact copies of earlier lines on purpose |
| `bill_date` | text | Bill date in mixed formats; 4 rows carry an impossible or blank date on purpose |
| `cust_code` | text | Customer code; 8 rows carry a code (`C-900` …) that exists nowhere in the customer file on purpose |
| `prod_code` | text | Product code; 6 rows carry a code (`P-900` …) that exists nowhere in the product file on purpose |
| `qty` | text | Quantity; 3 rows carry `five`, blank or `3 pcs` on purpose |
| `unit_price` | text | Unit price on the bill, as text with commas |
| `amount` | text | Bill amount, as text with commas; 4 rows carry `n/a`, `-500`, `0` or blank on purpose, and 5 rows carry an amount that does not equal qty × unit price on purpose |
| `tax` | text | Tax on the bill (5% where present); blank where the legacy file had none — migrates as NULL |

## The planted defects (70 in total)

57 quarantine a row; 13 are warnings that migrate. The audit re-finds
all 70, plus 77 knock-on orphans the planting did not name (clean sales
lines pointing at a customer or product whose master row failed). Exact
counts and source rows are in `raw/defect_manifest.json`.

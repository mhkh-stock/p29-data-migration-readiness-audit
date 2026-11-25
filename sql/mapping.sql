-- P29 — source -> target column mapping (BillPro 2009 -> CloudERP).
-- Part 1: the mapping table itself — one row per source column.
-- Every source column is mapped: 21 of 21 (100% coverage).
-- Part 2: the transform SQL — staging -> target, applying exactly
-- the rules written in this table. Quarantine reasons are the same
-- codes the checks in src/checks.py assert against the manifest.
--
-- Part 2 depends on the audit tables valid_customers /
-- valid_products / valid_sales (one row_no per row that passed
-- validation), created by src/run_migration.py from the same rules
-- the loader applies — dates are normalised to ISO in staging by
-- the loader before this part runs, so the SQL below only ever
-- sees ISO dates and numeric money.
--
-- Normalisation rules used everywhere below:
--   * money text  -> REAL: strip commas, then CAST (fails on 'TBD' etc.)
--   * date text   -> ISO: the three legacy formats are normalised in
--     Python (src/run_migration.py) because SQLite has no strptime;
--     the SQL below only accepts an already-ISO date.
--   * prod_code   -> upper-case, hyphens/spaces removed ('P-012'='P012')
--   * status      -> 'Active' unless the legacy value is exactly
--     'Inactive' (case-insensitive); anything else is a warning, not
--     a failure, and is recorded as 'Active'.
--   * category    -> 'Uncategorised' when blank (warning, not failure).
--   * phone       -> NULL when blank (warning, not failure).

-- ================= Part 1: mapping rows =================
INSERT INTO column_mapping
  (source_system, source_table, source_column, target_system, target_table, target_column, transform_rule, required) VALUES
('BillPro 2009 (legacy)', 'customers_legacy.csv', 'cust_code',  'CloudERP', 'dim_customer', 'cust_code',        'Keep as-is; must be unique — later copies are quarantined as duplicate_cust_code', 'YES'),
('BillPro 2009 (legacy)', 'customers_legacy.csv', 'cust_name',  'CloudERP', 'dim_customer', 'cust_name',        'Keep as-is; trim whitespace', 'YES'),
('BillPro 2009 (legacy)', 'customers_legacy.csv', 'phone',      'CloudERP', 'dim_customer', 'phone',            'Keep as-is; blank becomes NULL (warning, migrates)', 'NO'),
('BillPro 2009 (legacy)', 'customers_legacy.csv', 'city',       'CloudERP', 'dim_customer', 'city',             'Keep as-is; trim whitespace', 'NO'),
('BillPro 2009 (legacy)', 'customers_legacy.csv', 'credit_limit','CloudERP','dim_customer', 'credit_limit_pkr', 'Strip commas, cast to number — unparseable rows are quarantined (unparseable_credit_limit)', 'YES'),
('BillPro 2009 (legacy)', 'customers_legacy.csv', 'since_date', 'CloudERP', 'dim_customer', 'since_date',       'Normalise DD/MM/YYYY, YYYY-MM-DD or DD-Mon-YYYY to ISO YYYY-MM-DD — unparseable rows are quarantined (unparseable_since_date)', 'YES'),
('BillPro 2009 (legacy)', 'customers_legacy.csv', 'status',     'CloudERP', 'dim_customer', 'status',           'Active unless legacy value is Inactive (case-insensitive); any other value becomes Active (warning, migrates)', 'NO'),
('BillPro 2009 (legacy)', 'products_legacy.csv',  'prod_code',  'CloudERP', 'dim_product',  'prod_code',        'Normalise: upper-case, remove hyphens/spaces — later copies are quarantined as duplicate_prod_code_normalised', 'YES'),
('BillPro 2009 (legacy)', 'products_legacy.csv',  'prod_name',  'CloudERP', 'dim_product',  'prod_name',        'Keep as-is; trim whitespace', 'YES'),
('BillPro 2009 (legacy)', 'products_legacy.csv',  'category',   'CloudERP', 'dim_product',  'category',         'Keep as-is; blank becomes Uncategorised (warning, migrates)', 'NO'),
('BillPro 2009 (legacy)', 'products_legacy.csv',  'unit_price', 'CloudERP', 'dim_product',  'unit_price_pkr',   'Strip commas, cast to number — blank or zero rows are quarantined (missing_or_zero_price)', 'YES'),
('BillPro 2009 (legacy)', 'products_legacy.csv',  'uom',        'CloudERP', 'dim_product',  'uom',              'Keep as-is', 'NO'),
('BillPro 2009 (legacy)', 'products_legacy.csv',  'stock_qty',  'CloudERP', '(not migrated)', '(not migrated)', 'Legacy stock count is a point-in-time figure, not a master attribute — carried in the lineage doc only, not loaded into CloudERP', 'NO'),
('BillPro 2009 (legacy)', 'sales_legacy.csv',     'bill_no',    'CloudERP', 'fact_sales',   'bill_no',          'Keep as-is', 'YES'),
('BillPro 2009 (legacy)', 'sales_legacy.csv',     'bill_date',  'CloudERP', 'fact_sales',   'bill_date',        'Normalise DD/MM/YYYY, YYYY-MM-DD or DD-Mon-YYYY to ISO YYYY-MM-DD — unparseable rows are quarantined (unparseable_bill_date)', 'YES'),
('BillPro 2009 (legacy)', 'sales_legacy.csv',     'cust_code',  'CloudERP', 'fact_sales',   'customer_key',     'Look up dim_customer by cust_code — unknown codes are quarantined (orphan_cust_code)', 'YES'),
('BillPro 2009 (legacy)', 'sales_legacy.csv',     'prod_code',  'CloudERP', 'fact_sales',   'product_key',      'Normalise then look up dim_product — unknown codes are quarantined (orphan_prod_code)', 'YES'),
('BillPro 2009 (legacy)', 'sales_legacy.csv',     'qty',        'CloudERP', 'fact_sales',   'qty',              'Cast to whole number above 0 — unparseable rows are quarantined (unparseable_qty)', 'YES'),
('BillPro 2009 (legacy)', 'sales_legacy.csv',     'unit_price', 'CloudERP', 'fact_sales',   'unit_price_pkr',   'Strip commas, cast to number', 'YES'),
('BillPro 2009 (legacy)', 'sales_legacy.csv',     'amount',     'CloudERP', 'fact_sales',   'amount_pkr',       'Strip commas, cast to number — unparseable or zero rows are quarantined (unparseable_or_zero_amount); then checked: amount must equal qty x unit_price within 0.5% (amount_mismatch)', 'YES'),
('BillPro 2009 (legacy)', 'sales_legacy.csv',     'tax',        'CloudERP', 'fact_sales',   'tax_pkr',          'Strip commas, cast to number; blank becomes NULL', 'NO');

-- ================= Part 2: transform SQL =================
-- The three INSERTs below are run by src/run_migration.py in order,
-- AFTER the matching audit table exists: dim_customer, then
-- dim_product, then fact_sales. Sales validation reads the built
-- dims, so a sale whose customer or product failed to migrate is
-- quarantined as a knock-on orphan instead of vanishing in the JOIN.
-- The markers (-- == TRANSFORM ...) are how run_migration.py splits
-- this file; the SQL itself stays the readable, auditable form.

-- == TRANSFORM dim_customer ==
-- dim_customer (valid rows only: unique code, ISO date, numeric limit)
INSERT INTO dim_customer (cust_code, cust_name, phone, city, credit_limit_pkr, since_date, status)
SELECT
    cust_code,
    TRIM(cust_name),
    NULLIF(TRIM(phone), ''),
    TRIM(city),
    CAST(REPLACE(credit_limit, ',', '') AS REAL),
    since_date,  -- already normalised to ISO by the loader
    CASE WHEN LOWER(TRIM(status)) = 'inactive' THEN 'Inactive' ELSE 'Active' END
FROM stg_customers
WHERE row_no IN (SELECT row_no FROM valid_customers);

-- == TRANSFORM dim_product ==
-- dim_product (valid rows only: unique normalised code, price > 0)
INSERT INTO dim_product (prod_code, prod_name, category, unit_price_pkr, uom)
SELECT
    UPPER(REPLACE(REPLACE(prod_code, '-', ''), ' ', '')),
    TRIM(prod_name),
    CASE WHEN TRIM(category) = '' THEN 'Uncategorised' ELSE TRIM(category) END,
    CAST(REPLACE(unit_price, ',', '') AS REAL),
    TRIM(uom)
FROM stg_products
WHERE row_no IN (SELECT row_no FROM valid_products);

-- == TRANSFORM fact_sales ==
-- fact_sales (valid rows only — see valid_sales)
INSERT INTO fact_sales (bill_no, bill_date, customer_key, product_key, qty, unit_price_pkr, amount_pkr, tax_pkr)
SELECT
    s.bill_no,
    s.bill_date,  -- already normalised to ISO by the loader
    c.customer_key,
    p.product_key,
    CAST(s.qty AS INTEGER),
    CAST(REPLACE(s.unit_price, ',', '') AS REAL),
    CAST(REPLACE(s.amount, ',', '') AS REAL),
    CASE WHEN TRIM(s.tax) = '' THEN NULL ELSE CAST(REPLACE(s.tax, ',', '') AS REAL) END
FROM stg_sales s
JOIN dim_customer c ON c.cust_code = s.cust_code
JOIN dim_product p
  ON p.prod_code = UPPER(REPLACE(REPLACE(s.prod_code, '-', ''), ' ', ''))
WHERE s.row_no IN (SELECT row_no FROM valid_sales);

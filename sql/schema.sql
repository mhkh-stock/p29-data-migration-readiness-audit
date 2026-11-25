-- P29 — Data Migration Readiness Audit: target schema (CloudERP).
-- Staging tables hold the legacy CSVs verbatim (all text, as exported).
-- Target tables are the clean star-lite schema the ERP will load.
-- migration_log records every run; quarantine holds every row that
-- failed migration, with its reason. The .db rebuilds from the
-- scripts and is never committed.
-- Run: sqlite3 data/processed/migration.db < sql/schema.sql
-- (or via src/run_migration.py, which runs all three SQL files).

DROP TABLE IF EXISTS stg_customers;
DROP TABLE IF EXISTS stg_products;
DROP TABLE IF EXISTS stg_sales;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS column_mapping;
DROP TABLE IF EXISTS migration_log;
DROP TABLE IF EXISTS quarantine;

-- ---------- staging: legacy files, verbatim ----------
CREATE TABLE stg_customers (
    row_no       INTEGER PRIMARY KEY,   -- 1-based line in the source file
    cust_code    TEXT,
    cust_name    TEXT,
    phone        TEXT,
    city         TEXT,
    credit_limit TEXT,
    since_date   TEXT,
    status       TEXT
);

CREATE TABLE stg_products (
    row_no     INTEGER PRIMARY KEY,
    prod_code  TEXT,
    prod_name  TEXT,
    category   TEXT,
    unit_price TEXT,
    uom        TEXT,
    stock_qty  TEXT
);

CREATE TABLE stg_sales (
    row_no     INTEGER PRIMARY KEY,
    bill_no    TEXT,
    bill_date  TEXT,
    cust_code  TEXT,
    prod_code  TEXT,
    qty        TEXT,
    unit_price TEXT,
    amount     TEXT,
    tax        TEXT
);

-- ---------- target: CloudERP star-lite schema ----------
CREATE TABLE dim_customer (
    customer_key    INTEGER PRIMARY KEY,
    cust_code       TEXT NOT NULL UNIQUE,   -- legacy code, as the ERP key
    cust_name       TEXT NOT NULL,
    phone           TEXT,                   -- NULL when the legacy file had none
    city            TEXT,
    credit_limit_pkr REAL NOT NULL,
    since_date      TEXT NOT NULL,          -- ISO YYYY-MM-DD
    status          TEXT NOT NULL           -- Active / Inactive only
);

CREATE TABLE dim_product (
    product_key     INTEGER PRIMARY KEY,
    prod_code       TEXT NOT NULL UNIQUE,   -- normalised: upper-case, no hyphens
    prod_name       TEXT NOT NULL,
    category        TEXT NOT NULL,          -- 'Uncategorised' when legacy had none
    unit_price_pkr  REAL NOT NULL,
    uom             TEXT
);

CREATE TABLE fact_sales (
    sale_key        INTEGER PRIMARY KEY,
    bill_no         TEXT NOT NULL,
    bill_date       TEXT NOT NULL,          -- ISO YYYY-MM-DD
    customer_key    INTEGER NOT NULL REFERENCES dim_customer(customer_key),
    product_key     INTEGER NOT NULL REFERENCES dim_product(product_key),
    qty             INTEGER NOT NULL,
    unit_price_pkr  REAL NOT NULL,
    amount_pkr      REAL NOT NULL,
    tax_pkr         REAL,
    UNIQUE (bill_no, product_key, qty, unit_price_pkr, amount_pkr)
);

-- ---------- audit artefacts ----------
CREATE TABLE column_mapping (
    mapping_id    INTEGER PRIMARY KEY,
    source_system TEXT NOT NULL,            -- 'BillPro 2009 (legacy)'
    source_table  TEXT NOT NULL,
    source_column TEXT NOT NULL,
    target_system TEXT NOT NULL,            -- 'CloudERP'
    target_table  TEXT NOT NULL,
    target_column TEXT NOT NULL,
    transform_rule TEXT NOT NULL,           -- plain-language rule, applied in mapping.sql
    required      TEXT NOT NULL             -- YES / NO (row fails without it)
);

CREATE TABLE migration_log (
    log_id          INTEGER PRIMARY KEY,
    run_id          TEXT NOT NULL,          -- one id per run_migration.py run
    step            TEXT NOT NULL,          -- load / transform / reconcile
    table_name      TEXT NOT NULL,
    rows_in         INTEGER NOT NULL,
    rows_out        INTEGER NOT NULL,
    rows_quarantined INTEGER NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL
);

CREATE TABLE quarantine (
    quarantine_id INTEGER PRIMARY KEY,
    source_table  TEXT NOT NULL,            -- customers / products / sales
    source_row_no INTEGER NOT NULL,
    source_key    TEXT,                     -- cust_code / prod_code / bill_no
    reason        TEXT NOT NULL,            -- short machine code, e.g. orphan_cust_code
    detail        TEXT NOT NULL             -- what was wrong, in plain words
);

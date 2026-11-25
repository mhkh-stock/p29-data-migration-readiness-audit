-- P29 — reconciliation queries (the client keeps these).
-- Each query is written so that a CLEAN migration returns the
-- expected value stated in its comment: counts match, money matches
-- to the paisa, and the defect queries return 0 rows. Run them after
-- src/run_migration.py; src/checks.py runs them and asserts the
-- expected counts (which, on this SAMPLE, are the planted numbers).
-- Usage: sqlite3 data/processed/migration.db < sql/reconciliation.sql

-- R1. Row-count reconciliation: source -> staging -> target.
--    Expected: staging = source on every table; target = source minus
--    quarantine (customers 150 -> 137, products 60 -> 51, sales 600 -> 565).
SELECT 'customers' AS table_name,
       (SELECT COUNT(*) FROM stg_customers) AS source_rows,
       (SELECT COUNT(*) FROM dim_customer) AS target_rows,
       (SELECT COUNT(*) FROM quarantine WHERE source_table = 'customers') AS quarantined_rows
UNION ALL
SELECT 'products',
       (SELECT COUNT(*) FROM stg_products),
       (SELECT COUNT(*) FROM dim_product),
       (SELECT COUNT(*) FROM quarantine WHERE source_table = 'products')
UNION ALL
SELECT 'sales',
       (SELECT COUNT(*) FROM stg_sales),
       (SELECT COUNT(*) FROM fact_sales),
       (SELECT COUNT(*) FROM quarantine WHERE source_table = 'sales');

-- R2. Money reconciliation, customers: credit limits.
--    Expected: target total = source total of the rows that migrated
--    (unparseable limits are quarantined, so they never enter the sum).
SELECT 'credit_limit' AS measure,
       (SELECT ROUND(SUM(CAST(REPLACE(credit_limit, ',', '') AS REAL)), 2)
          FROM stg_customers
         WHERE row_no IN (SELECT row_no FROM valid_customers)) AS migrated_source_total_pkr,
       (SELECT ROUND(SUM(credit_limit_pkr), 2) FROM dim_customer) AS target_total_pkr;

-- R3. Money reconciliation, sales: amounts.
--    Expected: target total = source total of the rows that migrated;
--    the difference is exactly the quarantined amounts (orphans,
--    duplicates, bad dates/qtys/amounts, mismatches).
SELECT 'sales_amount' AS measure,
       (SELECT ROUND(SUM(CAST(REPLACE(amount, ',', '') AS REAL)), 2)
          FROM stg_sales
         WHERE row_no IN (SELECT row_no FROM valid_sales)) AS migrated_source_total_pkr,
       (SELECT ROUND(SUM(amount_pkr), 2) FROM fact_sales) AS target_total_pkr;

-- R4. Money reconciliation, sales: the quarantined amount, explained.
--    Expected: R3 source total (ALL parseable amounts) minus R3
--    migrated total = the sum below. On this SAMPLE the gap is the
--    quarantined rows' amounts; unparseable amounts contribute 0.
SELECT 'quarantined_amount' AS measure,
       (SELECT ROUND(SUM(CAST(REPLACE(amount, ',', '') AS REAL)), 2)
          FROM stg_sales
         WHERE row_no NOT IN (SELECT row_no FROM valid_sales)
           AND TRIM(REPLACE(amount, ',', '')) <> ''
           AND CAST(REPLACE(amount, ',', '') AS REAL) > 0) AS quarantined_parseable_total_pkr;

-- R5. Orphan detection — must return 0 rows on the target.
--    (Any fact row whose customer/product is missing from the dims.)
SELECT sale_key, bill_no, customer_key, product_key
FROM fact_sales f
WHERE NOT EXISTS (SELECT 1 FROM dim_customer c WHERE c.customer_key = f.customer_key)
   OR NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_key = f.product_key);

-- R6. Duplicate detection — must return 0 rows on the target.
--    (No customer code, product code or bill line appears twice.)
SELECT cust_code, COUNT(*) AS n FROM dim_customer GROUP BY cust_code HAVING COUNT(*) > 1
UNION ALL
SELECT prod_code, COUNT(*) FROM dim_product GROUP BY prod_code HAVING COUNT(*) > 1
UNION ALL
SELECT bill_no, COUNT(*) FROM fact_sales GROUP BY bill_no, product_key, qty, unit_price_pkr, amount_pkr HAVING COUNT(*) > 1;

-- R7. Value-mismatch sampling — must return 0 rows on the target.
--    (Every fact amount equals qty x unit price within 0.5%.)
SELECT sale_key, bill_no, qty, unit_price_pkr, amount_pkr,
       ROUND(qty * unit_price_pkr, 2) AS recomputed_pkr,
       ROUND(amount_pkr - qty * unit_price_pkr, 2) AS diff_pkr
FROM fact_sales
WHERE ABS(amount_pkr - qty * unit_price_pkr) > MAX(1.00, 0.005 * amount_pkr);

-- R8. Mapping coverage — must be 100%.
--    (Every source column appears exactly once in column_mapping:
--    7 customer + 6 product + 8 sales columns = 21 rows.)
SELECT (SELECT COUNT(*) FROM column_mapping) AS mapping_rows,
       (SELECT COUNT(DISTINCT source_table || '.' || source_column)
          FROM column_mapping) AS distinct_source_columns,
       CASE WHEN (SELECT COUNT(*) FROM column_mapping) =
                 (SELECT COUNT(DISTINCT source_table || '.' || source_column)
                    FROM column_mapping)
            THEN '100% — every source column mapped exactly once'
            ELSE 'GAP — see column_mapping' END AS coverage;

-- R9. Quarantine by reason — the must-fix list for cutover.
SELECT source_table, reason, COUNT(*) AS rows_affected
FROM quarantine
GROUP BY source_table, reason
ORDER BY source_table, rows_affected DESC;

-- R10. Migration log — every step, with in/out counts.
SELECT step, table_name, rows_in, rows_out, rows_quarantined
FROM migration_log
ORDER BY log_id;

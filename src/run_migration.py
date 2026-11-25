"""P29 — run the migration: legacy CSVs -> staging -> CloudERP target.

Loads the three legacy files verbatim into staging, validates every
row in Python (this file is the single source of truth for the
rules), writes the valid row lists to the audit tables
valid_customers / valid_products / valid_sales, then runs
sql/mapping.sql (mapping table + transform SQL) to build the target
star-lite schema, and records the migration log + quarantine.

Validation order (first failing reason wins — the quarantine reason):
  customers: duplicate code -> unparseable since_date ->
             unparseable credit_limit.  Warnings (migrate anyway):
             blank phone (NULL), invalid status (becomes Active).
  products:  duplicate normalised code -> missing/zero price.
             Warning: missing category (becomes 'Uncategorised').
  sales:     duplicate bill line -> unparseable bill_date ->
             unparseable qty -> unparseable/zero amount ->
             amount mismatch (qty x unit_price != amount, > 0.5%) ->
             orphan cust_code (customer not in the MIGRATED dim —
             including knock-on orphans, where the customer exists
             in the source file but its own row failed migration) ->
             orphan prod_code (same rule).  Intrinsic row defects are
             checked BEFORE references on purpose: the quarantine
             reason then tells the client what to fix on that row
             first, and an orphan is always a row that is otherwise
             clean — it only needs its master fixed.

Order of work: customers and products are validated and transformed
first, so sales validation reads the built dims. A sale is never
silently dropped by the SQL JOIN — if its customer or product did
not migrate, it is quarantined with the reason.

Dates are normalised to ISO in staging as they are validated, so the
SQL transform only ever sees ISO dates.

Usage:  python3 src/run_migration.py   (rebuilds data/processed/migration.db)
"""
import csv
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "processed" / "migration.db"
OUT = ROOT / "outputs"
SQL = ROOT / "sql"

DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y")
MONEY_RE = re.compile(r"^-?\d+(\.\d+)?$")


def parse_date(text):
    text = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_money(text):
    text = (text or "").strip().replace(",", "")
    if not MONEY_RE.match(text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def norm_code(code):
    return (code or "").strip().upper().replace("-", "").replace(" ", "")


def main():
    run_id = "run-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((SQL / "schema.sql").read_text())

    # Split sql/mapping.sql: Part 1 (mapping-table inserts) runs now;
    # the three transform INSERTs run one at a time, after the
    # matching audit table exists. Markers: "-- == TRANSFORM <table> ==".
    mapping_text = (SQL / "mapping.sql").read_text()
    part1, _, rest = mapping_text.partition("-- == TRANSFORM dim_customer ==")
    transforms = {}
    for chunk in ("-- == TRANSFORM dim_customer ==" + rest).split("-- == TRANSFORM "):
        if not chunk.strip():
            continue
        name, _, sql = chunk.partition("==")
        transforms[name.strip()] = sql
    conn.executescript(part1)

    log_rows = []
    quarantine = []  # (source_table, row_no, source_key, reason, detail)
    warnings = []    # (source_table, row_no, source_key, detail)

    def log(step, table, rows_in, rows_out, rows_q):
        now = datetime.now().isoformat(timespec="seconds")
        log_rows.append((run_id, step, table, rows_in, rows_out, rows_q, now, now))

    # ---------- load staging (verbatim) ----------
    def load_csv(name, table, cols):
        with open(RAW / name, newline="") as f:
            rows = list(csv.DictReader(f))
        for i, r in enumerate(rows, start=1):
            conn.execute(
                f"INSERT INTO {table} (row_no, {', '.join(cols)}) "
                f"VALUES ({', '.join(['?'] * (len(cols) + 1))})",
                [i] + [r[c] for c in cols])
        log("load", table.replace("stg_", ""), len(rows), len(rows), 0)
        return rows

    cust_rows = load_csv("customers_legacy.csv", "stg_customers",
                         ["cust_code", "cust_name", "phone", "city",
                          "credit_limit", "since_date", "status"])
    prod_rows = load_csv("products_legacy.csv", "stg_products",
                         ["prod_code", "prod_name", "category",
                          "unit_price", "uom", "stock_qty"])
    sale_rows = load_csv("sales_legacy.csv", "stg_sales",
                         ["bill_no", "bill_date", "cust_code", "prod_code",
                          "qty", "unit_price", "amount", "tax"])

    # ---------- validate customers ----------
    valid_cust = []
    seen_codes = set()
    for i, r in enumerate(cust_rows, start=1):
        code = (r["cust_code"] or "").strip()
        if code in seen_codes:
            quarantine.append(("customers", i, code, "duplicate_cust_code",
                               f"cust_code {code} already used by an earlier row — later copy rejected"))
            continue
        iso = parse_date(r["since_date"])
        if iso is None:
            quarantine.append(("customers", i, code, "unparseable_since_date",
                               f"since_date {r['since_date']!r} is not a real date in any legacy format"))
            continue
        limit = parse_money(r["credit_limit"])
        if limit is None:
            quarantine.append(("customers", i, code, "unparseable_credit_limit",
                               f"credit_limit {r['credit_limit']!r} is not a number"))
            continue
        # Only a row that will migrate reserves its code.
        seen_codes.add(code)
        conn.execute("UPDATE stg_customers SET since_date = ? WHERE row_no = ?", (iso, i))
        if not (r["phone"] or "").strip():
            warnings.append(("customers", i, code, "blank phone — migrates as NULL"))
        if (r["status"] or "").strip().lower() not in ("active", "inactive"):
            warnings.append(("customers", i, code,
                             f"status {r['status']!r} is not Active/Inactive — migrates as Active"))
        valid_cust.append(i)
    conn.execute("CREATE TABLE valid_customers (row_no INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO valid_customers VALUES (?)", [(n,) for n in valid_cust])
    conn.executescript(transforms["dim_customer"])
    q_cust = len(cust_rows) - len(valid_cust)
    log("transform", "customers", len(cust_rows), len(valid_cust), q_cust)

    # ---------- validate products ----------
    valid_prod = []
    seen_prod = set()
    for i, r in enumerate(prod_rows, start=1):
        ncode = norm_code(r["prod_code"])
        if ncode in seen_prod:
            quarantine.append(("products", i, r["prod_code"], "duplicate_prod_code_normalised",
                               f"prod_code {r['prod_code']!r} normalises to {ncode}, already used — later copy rejected"))
            continue
        price = parse_money(r["unit_price"])
        if price is None or price <= 0:
            quarantine.append(("products", i, r["prod_code"], "missing_or_zero_price",
                               f"unit_price {r['unit_price']!r} is blank, zero or not a number"))
            continue
        # Only a row that will migrate reserves its code.
        seen_prod.add(ncode)
        if not (r["category"] or "").strip():
            warnings.append(("products", i, r["prod_code"],
                             "blank category — migrates as 'Uncategorised'"))
        valid_prod.append(i)
    conn.execute("CREATE TABLE valid_products (row_no INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO valid_products VALUES (?)", [(n,) for n in valid_prod])
    conn.executescript(transforms["dim_product"])
    q_prod = len(prod_rows) - len(valid_prod)
    log("transform", "products", len(prod_rows), len(valid_prod), q_prod)

    # ---------- validate sales (against the MIGRATED dims) ----------
    valid_sale = []
    seen_lines = set()
    # A sale can only migrate if its customer and product migrated.
    # Codes that exist in the source file but whose master row failed
    # are knock-on orphans — quarantined here, never dropped silently.
    cust_codes = {r[0] for r in conn.execute("SELECT cust_code FROM dim_customer")}
    prod_codes = {r[0] for r in conn.execute("SELECT prod_code FROM dim_product")}
    for i, r in enumerate(sale_rows, start=1):
        key = (r["bill_no"], r["prod_code"], r["qty"], r["unit_price"], r["amount"])
        if key in seen_lines:
            quarantine.append(("sales", i, r["bill_no"], "duplicate_bill_line",
                               f"bill {r['bill_no']} line for {r['prod_code']} is an exact copy of an earlier line"))
            continue
        iso = parse_date(r["bill_date"])
        if iso is None:
            quarantine.append(("sales", i, r["bill_no"], "unparseable_bill_date",
                               f"bill_date {r['bill_date']!r} is not a real date in any legacy format"))
            continue
        try:
            qty = int((r["qty"] or "").strip())
            if str(qty) != (r["qty"] or "").strip():
                raise ValueError
        except ValueError:
            quarantine.append(("sales", i, r["bill_no"], "unparseable_qty",
                               f"qty {r['qty']!r} is not a whole number"))
            continue
        if qty <= 0:
            quarantine.append(("sales", i, r["bill_no"], "unparseable_qty",
                               f"qty {qty} is not above 0"))
            continue
        amount = parse_money(r["amount"])
        if amount is None or amount <= 0:
            quarantine.append(("sales", i, r["bill_no"], "unparseable_or_zero_amount",
                               f"amount {r['amount']!r} is blank, zero, negative or not a number"))
            continue
        price = parse_money(r["unit_price"])
        if price is None:
            quarantine.append(("sales", i, r["bill_no"], "unparseable_or_zero_amount",
                               f"unit_price {r['unit_price']!r} is not a number"))
            continue
        if abs(amount - qty * price) > max(1.00, 0.005 * amount):
            quarantine.append(("sales", i, r["bill_no"], "amount_mismatch",
                               f"amount PKR {amount:,.2f} does not equal qty {qty} x unit price PKR {price:,.2f} "
                               f"(= PKR {qty * price:,.2f})"))
            continue
        # References last: an orphan is always a row that is otherwise
        # clean — it only needs its master fixed.
        if (r["cust_code"] or "").strip() not in cust_codes:
            code = (r["cust_code"] or "").strip()
            if code in { (c["cust_code"] or "").strip() for c in cust_rows }:
                detail = (f"cust_code {code!r} exists in the customer file but its master "
                          f"row failed migration — fix the customer first, then re-run")
            else:
                detail = f"cust_code {code!r} does not exist in the customer file"
            quarantine.append(("sales", i, r["bill_no"], "orphan_cust_code", detail))
            continue
        if norm_code(r["prod_code"]) not in prod_codes:
            code = (r["prod_code"] or "").strip()
            if norm_code(code) in { norm_code(p["prod_code"]) for p in prod_rows }:
                detail = (f"prod_code {code!r} exists in the product file but its master "
                          f"row failed migration — fix the product first, then re-run")
            else:
                detail = f"prod_code {code!r} does not exist in the product file"
            quarantine.append(("sales", i, r["bill_no"], "orphan_prod_code", detail))
            continue
        conn.execute("UPDATE stg_sales SET bill_date = ? WHERE row_no = ?", (iso, i))
        # Only a row that will migrate reserves its bill line.
        seen_lines.add(key)
        valid_sale.append(i)
    conn.execute("CREATE TABLE valid_sales (row_no INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO valid_sales VALUES (?)", [(n,) for n in valid_sale])
    conn.executescript(transforms["fact_sales"])
    q_sale = len(sale_rows) - len(valid_sale)
    log("transform", "sales", len(sale_rows), len(valid_sale), q_sale)

    # ---------- quarantine + log ----------
    conn.executemany(
        "INSERT INTO quarantine (source_table, source_row_no, source_key, reason, detail) "
        "VALUES (?, ?, ?, ?, ?)", quarantine)
    total_in = len(cust_rows) + len(prod_rows) + len(sale_rows)
    total_out = len(valid_cust) + len(valid_prod) + len(valid_sale)
    log("reconcile", "all_tables", total_in, total_out, len(quarantine))
    conn.executemany(
        "INSERT INTO migration_log (run_id, step, table_name, rows_in, rows_out, "
        "rows_quarantined, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        log_rows)
    conn.commit()

    # ---------- extracts ----------
    OUT.mkdir(parents=True, exist_ok=True)
    proc = ROOT / "data" / "processed"
    for name, query in [
        ("dim_customer.csv", "SELECT * FROM dim_customer ORDER BY customer_key"),
        ("dim_product.csv", "SELECT * FROM dim_product ORDER BY product_key"),
        ("fact_sales.csv", "SELECT * FROM fact_sales ORDER BY sale_key"),
    ]:
        rows = conn.execute(query).fetchall()
        cols = [d[0] for d in conn.execute(query).description]
        with open(proc / name, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
    with open(OUT / "quarantine.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_table", "source_row_no", "source_key", "reason", "detail"])
        w.writerows(quarantine)
    with open(OUT / "migration_log.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "step", "table_name", "rows_in", "rows_out",
                    "rows_quarantined", "started_at", "finished_at"])
        w.writerows(log_rows)
    with open(ROOT / "data" / "processed" / "migration_warnings.json", "w") as f:
        import json
        json.dump([{"source_table": t, "source_row_no": n, "source_key": k, "detail": d}
                   for t, n, k, d in warnings], f, indent=2)
    conn.close()

    print(f"run {run_id}")
    print(f"customers: {len(cust_rows)} source -> {len(valid_cust)} target, {q_cust} quarantined")
    print(f"products:  {len(prod_rows)} source -> {len(valid_prod)} target, {q_prod} quarantined")
    print(f"sales:     {len(sale_rows)} source -> {len(valid_sale)} target, {q_sale} quarantined")
    print(f"total:     {total_in} source -> {total_out} target, {len(quarantine)} quarantined, "
          f"{len(warnings)} warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())

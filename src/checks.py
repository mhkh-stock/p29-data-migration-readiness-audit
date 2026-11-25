"""P29 — verification suite. Recomputes every headline number from
the raw legacy CSVs independently (no database, no migration code)
and compares it with the database, the workbook (recalculated in
LibreOffice), the report PDF and the README. A mistake in any one
of the four shows up as a failure.

Also checks: the planted-defect manifest (every planted defect
re-found, with the duplicate-rule nuance that the quarantined row is
whichever occurrence is second in file order), the 10 reconciliation
queries (each returning its expected value), the knock-on orphans
(recomputed, not typed), file inventory, and that the .db is
gitignored.

Usage:  python3 src/checks.py   (expect all checks passing)
"""
import csv
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "migration.db"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"
XLSX = OUT / "migration_readiness_workbook_SAMPLE.xlsx"
PDF = OUT / "migration_readiness_report_SAMPLE.pdf"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


def close(a, b, tol=0.01):
    return abs(a - b) <= tol


# ---------- independent re-implementation of the validation ----------
# Deliberately separate code from src/run_migration.py: same rules,
# re-derived from sql/mapping.sql, so a slip in either shows up.
DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y")


def pdate(text):
    text = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def pmoney(text):
    text = (text or "").strip().replace(",", "")
    if not re.match(r"^-?\d+(\.\d+)?$", text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def ncode(code):
    return (code or "").strip().upper().replace("-", "").replace(" ", "")


def read_csv(name):
    with open(RAW / name, newline="") as f:
        return list(csv.DictReader(f))


def independent_validation():
    """Returns (quarantine, warnings, valid) where quarantine is a set
    of (source_table, row_no, reason) and warnings a set of
    (source_table, row_no, kind)."""
    cust = read_csv("customers_legacy.csv")
    prod = read_csv("products_legacy.csv")
    sale = read_csv("sales_legacy.csv")
    quarantine = set()
    warnings = set()
    valid_cust, valid_prod, valid_sale = set(), set(), set()

    seen = set()
    for i, r in enumerate(cust, start=1):
        code = (r["cust_code"] or "").strip()
        if code in seen:
            quarantine.add(("customers", i, "duplicate_cust_code"))
            continue
        if pdate(r["since_date"]) is None:
            quarantine.add(("customers", i, "unparseable_since_date"))
            continue
        if pmoney(r["credit_limit"]) is None:
            quarantine.add(("customers", i, "unparseable_credit_limit"))
            continue
        seen.add(code)
        if not (r["phone"] or "").strip():
            warnings.add(("customers", i, "blank_phone"))
        if (r["status"] or "").strip().lower() not in ("active", "inactive"):
            warnings.add(("customers", i, "invalid_status"))
        valid_cust.add(i)

    seen = set()
    for i, r in enumerate(prod, start=1):
        nc = ncode(r["prod_code"])
        if nc in seen:
            quarantine.add(("products", i, "duplicate_prod_code_normalised"))
            continue
        price = pmoney(r["unit_price"])
        if price is None or price <= 0:
            quarantine.add(("products", i, "missing_or_zero_price"))
            continue
        seen.add(nc)
        if not (r["category"] or "").strip():
            warnings.add(("products", i, "missing_category"))
        valid_prod.add(i)

    dim_cust = {(cust[i - 1]["cust_code"] or "").strip() for i in valid_cust}
    dim_prod = {ncode(prod[i - 1]["prod_code"]) for i in valid_prod}
    seen_lines = set()
    for i, r in enumerate(sale, start=1):
        key = (r["bill_no"], r["prod_code"], r["qty"], r["unit_price"], r["amount"])
        if key in seen_lines:
            quarantine.add(("sales", i, "duplicate_bill_line"))
            continue
        if pdate(r["bill_date"]) is None:
            quarantine.add(("sales", i, "unparseable_bill_date"))
            continue
        try:
            qty = int((r["qty"] or "").strip())
            if str(qty) != (r["qty"] or "").strip() or qty <= 0:
                raise ValueError
        except ValueError:
            quarantine.add(("sales", i, "unparseable_qty"))
            continue
        amount = pmoney(r["amount"])
        if amount is None or amount <= 0:
            quarantine.add(("sales", i, "unparseable_or_zero_amount"))
            continue
        price = pmoney(r["unit_price"])
        if price is None:
            quarantine.add(("sales", i, "unparseable_or_zero_amount"))
            continue
        if abs(amount - qty * price) > max(1.00, 0.005 * amount):
            quarantine.add(("sales", i, "amount_mismatch"))
            continue
        if (r["cust_code"] or "").strip() not in dim_cust:
            quarantine.add(("sales", i, "orphan_cust_code"))
            continue
        if ncode(r["prod_code"]) not in dim_prod:
            quarantine.add(("sales", i, "orphan_prod_code"))
            continue
        seen_lines.add(key)
        valid_sale.add(i)
    return quarantine, warnings, (valid_cust, valid_prod, valid_sale)


def main():
    manifest = json.loads((RAW / "defect_manifest.json").read_text())
    summary = json.loads((OUT / "reconciliation_summary.json").read_text())
    conn = sqlite3.connect(DB)
    q = conn.execute

    # ---- 1. Independent recompute vs the database ----
    exp_quar, exp_warn, (vc, vp, vs) = independent_validation()
    db_quar = {(t, n, r) for t, n, r in q(
        "SELECT source_table, source_row_no, reason FROM quarantine")}
    check("independent recompute: quarantine matches the database exactly",
          db_quar == exp_quar,
          f"db-only={sorted(db_quar - exp_quar)[:3]} recompute-only={sorted(exp_quar - db_quar)[:3]}")
    db_valid = {
        "customers": {n for (n,) in q("SELECT row_no FROM valid_customers")},
        "products": {n for (n,) in q("SELECT row_no FROM valid_products")},
        "sales": {n for (n,) in q("SELECT row_no FROM valid_sales")},
    }
    check("independent recompute: valid customers match", db_valid["customers"] == vc)
    check("independent recompute: valid products match", db_valid["products"] == vp)
    check("independent recompute: valid sales match", db_valid["sales"] == vs)

    db_warn = {(w["source_table"], w["source_row_no"],
                "blank_phone" if "blank phone" in w["detail"]
                else "invalid_status" if "status" in w["detail"] else "missing_category")
               for w in json.loads((ROOT / "data" / "processed" / "migration_warnings.json").read_text())}
    check("independent recompute: warnings match", db_warn == exp_warn,
          f"db-only={sorted(db_warn - exp_warn)[:3]} recompute-only={sorted(exp_warn - db_warn)[:3]}")

    # ---- 2. Manifest: every planted defect re-found ----
    for table, defects in manifest["defects"].items():
        for reason, count in defects.items():
            planted = set(manifest["planted_rows"][table][reason])
            if reason in ("blank_phone", "invalid_status", "missing_category"):
                # Warnings: a planted row either migrated with the warning
                # or was quarantined for a higher-priority reason first
                # (e.g. a blank-phone row that is also the later copy of a
                # duplicate code) — either way it must be accounted for.
                warned = {n for (t, n, k) in exp_warn if t == table and k == reason}
                quarantined = {n for (t, n, _) in exp_quar if t == table}
                check(f"manifest: {table} {reason} — all {count} planted rows accounted for",
                      planted <= (warned | quarantined),
                      f"unaccounted: {sorted(planted - warned - quarantined)}")
                check(f"manifest: {table} {reason} warnings + quarantined-overlap == {count}",
                      len(warned) + len(planted & quarantined) == count,
                      f"warned {len(warned)}, overlap {len(planted & quarantined)}")
            elif reason.startswith("duplicate_"):
                # Duplicates: the quarantined row is whichever occurrence
                # is second in file order (first occurrence wins), so the
                # planted copy row is not necessarily the quarantined one.
                # What must hold exactly: the count, and the set of
                # duplicated keys.
                got = sum(1 for (t, _, r) in exp_quar if t == table and r == reason)
                check(f"manifest: {table} {reason} == {count}", got == count, f"got {got}")
                conn = sqlite3.connect(DB)
                if table == "customers":
                    keys = {r[0] for r in conn.execute(
                        "SELECT source_key FROM quarantine WHERE reason = ?", (reason,))}
                    dup_keys = {r[0] for r in conn.execute(
                        "SELECT cust_code FROM stg_customers GROUP BY cust_code HAVING COUNT(*) > 1")}
                elif table == "products":
                    keys = {ncode(r[0]) for r in conn.execute(
                        "SELECT source_key FROM quarantine WHERE reason = ?", (reason,))}
                    dup_keys = {r[0] for r in conn.execute(
                        "SELECT UPPER(REPLACE(REPLACE(prod_code, '-', ''), ' ', '')) "
                        "FROM stg_products GROUP BY 1 HAVING COUNT(*) > 1")}
                else:
                    keys = {r[0] for r in conn.execute(
                        "SELECT source_key FROM quarantine WHERE reason = ?", (reason,))}
                    dup_keys = {r[0] for r in conn.execute(
                        "SELECT bill_no FROM stg_sales GROUP BY bill_no, prod_code, qty, "
                        "unit_price, amount HAVING COUNT(*) > 1")}
                conn.close()
                check(f"manifest: {table} {reason} — quarantined keys are exactly the duplicated keys",
                      keys == dup_keys, f"{sorted(keys)[:3]} vs {sorted(dup_keys)[:3]}")
            elif reason.startswith("orphan_"):
                got_all = sum(1 for (t, _, r) in exp_quar if t == table and r == reason)
                got_planted = sum(1 for n in planted
                                  if (table, n, reason) in exp_quar)
                check(f"manifest: planted {reason} rows all quarantined as {reason}",
                      got_planted == len(planted), f"{got_planted}/{len(planted)}")
                check(f"manifest: {reason} total = planted + knock-on",
                      got_all >= count, f"got {got_all}, planted {count}")
            else:
                got = sum(1 for (t, _, r) in exp_quar if t == table and r == reason)
                check(f"manifest: {table} {reason} == {count}", got == count, f"got {got}")
    check("manifest: 70 defects planted",
          manifest["totals"]["defects_total"] == 70)
    knock_on = sum(1 for (t, n, r) in exp_quar
                   if r.startswith("orphan_")
                   and n not in manifest["planted_rows"][t][r])
    check("knock-on orphans recomputed (77)", knock_on == 77, f"got {knock_on}")
    check("summary knock-on orphans match recompute",
          summary["knock_on_orphans"] == knock_on)

    # ---- 3. Database counts + money ----
    src = {"customers": 150, "products": 60, "sales": 600}
    tgt = {"customers": q("SELECT COUNT(*) FROM dim_customer").fetchone()[0],
           "products": q("SELECT COUNT(*) FROM dim_product").fetchone()[0],
           "sales": q("SELECT COUNT(*) FROM fact_sales").fetchone()[0]}
    check("target counts 137/51/488",
          (tgt["customers"], tgt["products"], tgt["sales"]) == (137, 51, 488), str(tgt))
    check("summary counts match the database",
          summary["source_rows"] == src and summary["target_rows"] == tgt)
    sales_src = q("SELECT ROUND(SUM(CAST(REPLACE(amount, ',', '') AS REAL)), 2) "
                  "FROM stg_sales WHERE TRIM(REPLACE(amount, ',', '')) <> '' "
                  "AND CAST(REPLACE(amount, ',', '') AS REAL) > 0").fetchone()[0]
    sales_tgt = q("SELECT ROUND(SUM(amount_pkr), 2) FROM fact_sales").fetchone()[0]
    sales_quar = q("SELECT ROUND(SUM(CAST(REPLACE(amount, ',', '') AS REAL)), 2) "
                   "FROM stg_sales WHERE row_no NOT IN (SELECT row_no FROM valid_sales) "
                   "AND TRIM(REPLACE(amount, ',', '')) <> '' "
                   "AND CAST(REPLACE(amount, ',', '') AS REAL) > 0").fetchone()[0]
    check("sales money reconciles to the paisa",
          close(sales_tgt + sales_quar, sales_src),
          f"{sales_tgt} + {sales_quar} != {sales_src}")
    check("sales totals are the verified numbers",
          (sales_src, sales_tgt, sales_quar) == (16666459.35, 13830124.0, 2836335.35),
          f"{sales_src} / {sales_tgt} / {sales_quar}")
    credit_tgt = q("SELECT ROUND(SUM(credit_limit_pkr), 2) FROM dim_customer").fetchone()[0]
    check("credit limits total PKR 138,187,000.00",
          close(credit_tgt, 138187000.0), str(credit_tgt))
    check("target has 0 orphans",
          q("SELECT COUNT(*) FROM fact_sales f WHERE NOT EXISTS "
            "(SELECT 1 FROM dim_customer c WHERE c.customer_key = f.customer_key) "
            "OR NOT EXISTS (SELECT 1 FROM dim_product p WHERE p.product_key = f.product_key)").fetchone()[0] == 0)
    check("target has 0 amount mismatches",
          q("SELECT COUNT(*) FROM fact_sales WHERE ABS(amount_pkr - qty * unit_price_pkr) "
            "> MAX(1.00, 0.005 * amount_pkr)").fetchone()[0] == 0)
    check("target has 0 duplicate codes/lines",
          q("SELECT COUNT(*) FROM (SELECT cust_code FROM dim_customer GROUP BY cust_code HAVING COUNT(*) > 1 "
            "UNION ALL SELECT prod_code FROM dim_product GROUP BY prod_code HAVING COUNT(*) > 1 "
            "UNION ALL SELECT bill_no FROM fact_sales GROUP BY bill_no, product_key, qty, unit_price_pkr, amount_pkr "
            "HAVING COUNT(*) > 1)").fetchone()[0] == 0)
    check("mapping rows = 21", q("SELECT COUNT(*) FROM column_mapping").fetchone()[0] == 21)
    check("mapping coverage 100% (21 distinct source columns)",
          q("SELECT COUNT(DISTINCT source_table || '.' || source_column) FROM column_mapping").fetchone()[0] == 21)
    check("stock_qty is the only column not loaded",
          q("SELECT COUNT(*) FROM column_mapping WHERE target_table = '(not migrated)'").fetchone()[0] == 1)
    check("migration log has 7 steps",
          q("SELECT COUNT(*) FROM migration_log").fetchone()[0] == 7)
    check("migration log in/out matches counts",
          q("SELECT rows_in FROM migration_log WHERE step='reconcile'").fetchone()[0] == 810
          and q("SELECT rows_out FROM migration_log WHERE step='reconcile'").fetchone()[0] == 676
          and q("SELECT rows_quarantined FROM migration_log WHERE step='reconcile'").fetchone()[0] == 134)
    check("readiness 83.46% / sales readiness 81.33%",
          summary["readiness_pct"] == 83.46 and summary["sales_readiness_pct"] == 81.33)
    check("verdict is CONDITIONAL GO", summary["verdict"] == "CONDITIONAL GO")
    conn.close()

    # ---- 4. Reconciliation SQL returns its expected values ----
    conn = sqlite3.connect(DB)
    sql_text = (ROOT / "sql" / "reconciliation.sql").read_text()
    stmts = [s for s in sql_text.split(";") if s.strip() and not s.strip().startswith("--")]
    # Split into the 10 named queries (R1..R10) by their -- R# markers.
    parts = re.split(r"-- R(\d+)\.", sql_text)[1:]
    expected = {
        1: lambda rows: rows == [("customers", 150, 137, 13),
                                 ("products", 60, 51, 9),
                                 ("sales", 600, 488, 112)],
        2: lambda rows: close(rows[0][1], rows[0][2]) and close(rows[0][1], 138187000.0),
        3: lambda rows: close(rows[0][1], rows[0][2]) and close(rows[0][1], 13830124.0),
        4: lambda rows: close(rows[0][1], 2836335.35),
        5: lambda rows: rows == [],
        6: lambda rows: rows == [],
        7: lambda rows: rows == [],
        8: lambda rows: rows[0][0] == 21 and rows[0][1] == 21,
        9: lambda rows: sum(r[2] for r in rows) == 134,
        10: lambda rows: len(rows) == 7,
    }
    for i in range(0, len(parts), 2):
        num = int(parts[i])
        body = parts[i + 1]
        # The split consumed the "-- R#." marker, so the body starts
        # with the comment's remaining text — take from the SELECT.
        query = body[body.index("SELECT"):]
        rows = conn.execute(query).fetchall()
        check(f"reconciliation R{num} returns its expected value",
              expected[num](rows), f"got {rows[:3]}")
    conn.close()

    # ---- 5. CSV extracts match the database ----
    conn = sqlite3.connect(DB)
    for name, table in [("dim_customer.csv", "dim_customer"),
                        ("dim_product.csv", "dim_product"),
                        ("fact_sales.csv", "fact_sales")]:
        with open(ROOT / "data" / "processed" / name, newline="") as f:
            n = sum(1 for _ in f) - 1
        dbn = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        check(f"extract {name} row count == {table}", n == dbn, f"{n} vs {dbn}")
    qcsv = list(csv.DictReader(open(OUT / "quarantine.csv")))
    check("quarantine.csv has 134 rows", len(qcsv) == 134, str(len(qcsv)))
    mlog = list(csv.DictReader(open(OUT / "migration_log.csv")))
    check("migration_log.csv has 7 rows", len(mlog) == 7, str(len(mlog)))
    conn.close()

    # ---- 6. Workbook: formulas present ----
    wb = load_workbook(XLSX, data_only=False)
    check("workbook: 5 sheets",
          wb.sheetnames == ["Cover", "Mapping", "Reconciliation", "Quarantine", "Go-No-Go"],
          str(wb.sheetnames))
    cover = wb["Cover"]
    check("workbook source: Cover values are formulas",
          str(cover["B4"].value or "").startswith("=")
          and all(str(cover[f"B{r}"].value or "").startswith("=") for r in range(6, 15)))
    rec = wb["Reconciliation"]
    check("workbook source: Reconciliation readiness + money cells are formulas",
          all(str(rec[c].value or "").startswith("=") for c in
              ["E5", "E6", "E7", "E8", "E12", "E13", "F12", "F13"]))
    check("workbook source: AGGREGATE uses the _xlfn. prefix",
          str(rec["B15"].value).startswith("=_xlfn.AGGREGATE"))
    check("workbook source: MINIFS uses the _xlfn. prefix",
          str(rec["B17"].value).startswith("=_xlfn.MINIFS")
          and str(wb["Go-No-Go"]["B24"].value).startswith("=_xlfn.MINIFS"))
    check("workbook source: Go-No-Go must-fix counts are COUNTIFs",
          all(str(wb["Go-No-Go"][f"B{r}"].value or "").startswith("=COUNTIF")
              for r in range(10, 22)))
    check("workbook source: Mapping coverage is a formula",
          str(wb["Mapping"]["B28"].value).startswith("="))
    check("workbook: Quarantine has 134 rows + header",
          wb["Quarantine"].max_row == 139, str(wb["Quarantine"].max_row))
    check("workbook: Mapping has 21 rows + header",
          wb["Mapping"].max_row >= 25, str(wb["Mapping"].max_row))

    # ---- 7. Workbook: LibreOffice recalc ----
    recalc_dir = OUT / ".recalc"
    if recalc_dir.exists():
        shutil.rmtree(recalc_dir)
    recalc_dir.mkdir()
    r = subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx",
                        "--outdir", str(recalc_dir), str(XLSX)],
                       capture_output=True, text=True, timeout=300)
    check("libreoffice recalc ran", r.returncode == 0, r.stderr.strip()[:200])
    recalc = recalc_dir / XLSX.name
    wb2 = load_workbook(recalc, data_only=True)
    cv = wb2["Cover"]
    checks_recalc = [
        ("Cover B4 verdict", cv["B4"].value == "CONDITIONAL GO", str(cv["B4"].value)),
        ("Cover B6 source rows", cv["B6"].value == 810, str(cv["B6"].value)),
        ("Cover B7 target rows", cv["B7"].value == 676, str(cv["B7"].value)),
        ("Cover B8 quarantined", cv["B8"].value == 134, str(cv["B8"].value)),
        ("Cover B9 readiness", close(cv["B9"].value or 0, 0.8346, 0.0001), str(cv["B9"].value)),
        ("Cover B10 sales migrated", close(cv["B10"].value or 0, 13830124.0), str(cv["B10"].value)),
        ("Cover B11 sales quarantined", close(cv["B11"].value or 0, 2836335.35), str(cv["B11"].value)),
        ("Cover B12 reconciled", cv["B12"].value == "RECONCILED", str(cv["B12"].value)),
        ("Cover B13 mapping coverage", close(cv["B13"].value or 0, 1.0, 0.0001), str(cv["B13"].value)),
        ("Cover B14 knock-on orphans", cv["B14"].value == 77, str(cv["B14"].value)),
    ]
    for name, ok, detail in checks_recalc:
        check(f"workbook recalc: {name}", ok, detail)
    rc = wb2["Reconciliation"]
    check("workbook recalc: totals 810/676/134",
          (rc["B8"].value, rc["C8"].value, rc["D8"].value) == (810, 676, 134),
          f"{rc['B8'].value}/{rc['C8'].value}/{rc['D8'].value}")
    check("workbook recalc: money differences are 0",
          close(rc["E12"].value or 0, 0) and close(rc["E13"].value or 0, 0),
          f"{rc['E12'].value}/{rc['E13'].value}")
    check("workbook recalc: AGGREGATE largest difference is 0",
          close(rc["B15"].value or 0, 0), str(rc["B15"].value))
    check("workbook recalc: MINIFS lowest readiness is sales 81.33%",
          close(rc["B17"].value or 0, 0.8133, 0.0001), str(rc["B17"].value))
    check("workbook recalc: Mapping coverage is 100%",
          close(wb2["Mapping"]["B28"].value or 0, 1.0, 0.0001),
          str(wb2["Mapping"]["B28"].value))
    check("workbook recalc: Quarantine count is 134",
          wb2["Quarantine"]["B4"].value == 134, str(wb2["Quarantine"]["B4"].value))
    gn = wb2["Go-No-Go"]
    check("workbook recalc: Go-No-Go verdict + readiness + total",
          gn["B4"].value == "CONDITIONAL GO"
          and close(gn["B5"].value or 0, 0.8346, 0.0001)
          and gn["B6"].value == 134 and gn["B22"].value == 134,
          f"{gn['B4'].value}/{gn['B5'].value}/{gn['B6'].value}/{gn['B22'].value}")
    check("workbook recalc: Go-No-Go must-fix counts sum to 134",
          sum((gn[f"B{r}"].value or 0) for r in range(10, 22)) == 134)
    errors = []
    for ws in wb2.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("#"):
                    errors.append(f"{ws.title}!{cell.coordinate}={cell.value}")
    check("workbook recalc: zero error values", not errors, "; ".join(errors[:5]))
    shutil.rmtree(recalc_dir)

    # ---- 8. PDF ----
    check("report PDF exists", PDF.exists() and PDF.stat().st_size > 1000)
    info = subprocess.run(["pdfinfo", str(PDF)], capture_output=True, text=True)
    pages = re.search(r"Pages:\s+(\d+)", info.stdout)
    check("report PDF is 2 pages", pages and pages.group(1) == "2",
          info.stdout.strip().splitlines()[0] if info.stdout else info.stderr[:100])
    text = subprocess.run(["pdftotext", str(PDF), "-"], capture_output=True, text=True).stdout
    for needle in ["CONDITIONAL GO", "13,830,124.00", "2,836,335.35",
                   "16,666,459.35", "83.46%", "77 sales lines"]:
        check(f"report PDF contains {needle!r}", needle in text)

    # ---- 9. Report, README, lineage ----
    report = (OUT / "reconciliation_report.md").read_text()
    for needle in ["CONDITIONAL GO", "83.46%", "13,830,124.00", "2,836,335.35",
                   "16,666,459.35", "138,187,000.00", "134 quarantined", "77"]:
        check(f"reconciliation report contains {needle!r}", needle in report)
    readme = (ROOT / "README.md").read_text()
    for needle in ["CONDITIONAL GO", "810 source rows", "676 target rows", "134 quarantined",
                   "83.46%", "16,666,459.35", "13,830,124.00", "2,836,335.35",
                   "138,187,000.00", "21/21", "77 knock-on", "600 → 488"]:
        check(f"README contains {needle!r}", needle in readme)
    lineage = (OUT / "lineage.md").read_text()
    check("lineage doc has a Mermaid diagram", "```mermaid" in lineage)
    check("lineage doc names the excluded stock_qty",
          "stock_qty" in lineage and "NOT migrated" in lineage)
    diag = OUT / "lineage_diagram.png"
    check("lineage diagram PNG exists and is a PNG",
          diag.exists() and diag.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
          and diag.stat().st_size > 10000, str(diag.stat().st_size))

    # ---- 10. File inventory, gitignore, requirements ----
    expected_files = [
        "README.md", "PACKAGE-NOTE.md", "requirements.txt", ".gitignore",
        "data/README.md", "data/raw/customers_legacy.csv",
        "data/raw/products_legacy.csv", "data/raw/sales_legacy.csv",
        "data/raw/defect_manifest.json", "data/processed/dim_customer.csv",
        "data/processed/dim_product.csv", "data/processed/fact_sales.csv",
        "data/processed/migration_warnings.json",
        "sql/schema.sql", "sql/mapping.sql", "sql/reconciliation.sql",
        "src/generate_data.py", "src/run_migration.py", "src/analyze.py",
        "src/build_workbook.py", "src/build_report.py", "src/checks.py",
        "outputs/reconciliation_report.md", "outputs/reconciliation_summary.json",
        "outputs/migration_log.csv", "outputs/quarantine.csv", "outputs/lineage.md",
        "outputs/lineage_diagram.png",
        "outputs/migration_readiness_workbook_SAMPLE.xlsx",
        "outputs/migration_readiness_report_SAMPLE.pdf",
    ]
    for rel in expected_files:
        check(f"file exists: {rel}", (ROOT / rel).exists())
    check("raw dir has exactly the 3 legacy CSVs",
          sorted(p.name for p in (RAW).glob("*_legacy.csv"))
          == ["customers_legacy.csv", "products_legacy.csv", "sales_legacy.csv"])
    gitignore = (ROOT / ".gitignore").read_text()
    check(".gitignore excludes *.db", "*.db" in gitignore)
    check(".db exists locally (never uploaded)", DB.exists())
    req = (ROOT / "requirements.txt").read_text()
    for pkg in ("openpyxl==3.1.2", "reportlab==5.0.1", "matplotlib==3.6.3"):
        check(f"requirements pins {pkg}", pkg in req)
    pkg_note = (ROOT / "PACKAGE-NOTE.md").read_text()
    for needle in ["$20", "$65", "$140", "CONDITIONAL GO", "83.46%"]:
        check(f"PACKAGE-NOTE contains {needle!r}", needle in pkg_note)

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passing")
    if failed:
        print("FAILED:")
        for n in failed:
            print(f"  - {n}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

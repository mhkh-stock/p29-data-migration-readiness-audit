"""Build the P29 client workbook: outputs/migration_readiness_workbook_SAMPLE.xlsx.

Sheets: Cover (headline numbers as LIVE formulas) | Mapping (the 21
source->target column mappings) | Reconciliation (row counts + money,
all differences as formulas, plus _xlfn.AGGREGATE / _xlfn.MINIFS
checks) | Quarantine (all 134 rejected rows, filterable) | Go-No-Go
(verdict, readiness as a formula, must-fix list with COUNTIFs).

All numbers come from the warehouse (data/processed/migration.db) via
outputs/reconciliation_summary.json; the sheets prove them a second
way with formulas, and src/checks.py recalculates the workbook in
LibreOffice and compares. AGGREGATE / MINIFS formulas are written
with the _xlfn. prefix — the plain forms show #VALUE! / #NAME! in
LibreOffice (verified 8 Nov 2026).

Usage:  python3 src/build_workbook.py
"""
import json
import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "migration.db"
OUT = ROOT / "outputs" / "migration_readiness_workbook_SAMPLE.xlsx"
SUMMARY = json.loads((ROOT / "outputs" / "reconciliation_summary.json").read_text())

NAVY = "2E5A88"
LIGHT = "DCE6F1"
TITLE_FONT = Font(name="Calibri", size=16, bold=True, color=NAVY)
H_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
HDR_FILL = PatternFill("solid", fgColor=NAVY)
LIGHT_FILL = PatternFill("solid", fgColor=LIGHT)
MONEY = '"PKR" #,##0.00'
PCT = '0.00%'
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = H_FONT
        cell.fill = HDR_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BOX


def title_block(ws, title, subtitle):
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws["A2"] = subtitle
    ws["A2"].font = Font(name="Calibri", size=11, italic=True, color="595959")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")


def main():
    conn = sqlite3.connect(DB)
    mapping = conn.execute(
        "SELECT source_table, source_column, target_table, target_column, "
        "transform_rule, required FROM column_mapping ORDER BY mapping_id").fetchall()
    quar = conn.execute(
        "SELECT source_table, source_row_no, source_key, reason, detail "
        "FROM quarantine ORDER BY source_table, reason, source_row_no").fetchall()
    conn.close()
    s = SUMMARY
    wb = Workbook()

    # ================= Cover =================
    ws = wb.active
    ws.title = "Cover"
    title_block(ws, "Data Migration Readiness Audit — Ravi Traders (SAMPLE)",
                "BillPro 2009 (legacy) → CloudERP · Audit date 25 Nov 2026 · "
                "SAMPLE delivery on synthetic data — the method is real, the business is not.")
    ws["A4"] = "Verdict"
    ws["B4"] = "='Go-No-Go'!B4"
    ws["B4"].font = Font(name="Calibri", size=14, bold=True, color=NAVY)
    labels = [
        ("Source rows", "=Reconciliation!B8"),
        ("Target rows (migrated)", "=Reconciliation!C8"),
        ("Quarantined rows", "=Reconciliation!D8"),
        ("Readiness", "=Reconciliation!E8"),
        ("Sales migrated", "=Reconciliation!C12"),
        ("Sales quarantined", "=Reconciliation!D12"),
        ("Sales reconciled?", "=Reconciliation!F12"),
        ("Mapping coverage", "=Mapping!B28"),
        ("Knock-on orphan sales lines", "=Reconciliation!B16"),
    ]
    r = 6
    for label, formula in labels:
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        c = ws.cell(row=r, column=2, value=formula)
        if "Readiness" in label or "coverage" in label:
            c.number_format = PCT
        elif "rows" in label or "lines" in label:
            c.number_format = "#,##0"
        elif "Sales" in label and "?" not in label:
            c.number_format = MONEY
        r += 1
    ws["A16"] = ("Read this first: the move is CONDITIONAL GO — fix the quarantined rows "
                 "(Go-No-Go sheet), re-run the migration, and confirm the verdict turns "
                 "to GO. Every number above is a live formula over the other sheets.")
    ws["A16"].alignment = Alignment(wrap_text=True, vertical="top")
    ws["A16"].font = Font(italic=True)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 28
    ws.merge_cells("A16:B18")

    # ================= Mapping =================
    ws = wb.create_sheet("Mapping")
    title_block(ws, "Source → Target Mapping",
                "BillPro 2009 (legacy) → CloudERP · 21 of 21 source columns mapped (100%). "
                "One column is explicitly excluded, with its reason — nothing is silently dropped.")
    headers = ["Source table", "Source column", "Target table", "Target column",
               "Transform rule", "Required?"]
    for j, h in enumerate(headers, start=1):
        ws.cell(row=4, column=j, value=h)
    style_header(ws, 4, len(headers))
    for i, row in enumerate(mapping, start=5):
        for j, v in enumerate(row, start=1):
            c = ws.cell(row=i, column=j, value=v)
            c.border = BOX
            c.alignment = Alignment(wrap_text=True, vertical="top")
    last = 4 + len(mapping)
    ws.cell(row=last + 2, column=1, value="Source columns mapped").font = Font(bold=True)
    ws.cell(row=last + 2, column=2, value=f"=COUNTA(A5:A{last})").number_format = "#,##0"
    ws.cell(row=last + 3, column=1, value="Mapping coverage").font = Font(bold=True)
    ws.cell(row=last + 3, column=2, value=f"=B{last + 2}/21").number_format = PCT
    for col, w in zip("ABCDEF", [24, 18, 18, 20, 72, 10]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"

    # ================= Reconciliation =================
    ws = wb.create_sheet("Reconciliation")
    title_block(ws, "Reconciliation — Row Counts and Money",
                "Source → staging → target. Differences are formulas: a mismatch "
                "shows up here, not in a typed number.")
    headers = ["Table", "Source rows", "Target rows", "Quarantined", "Readiness"]
    for j, h in enumerate(headers, start=1):
        ws.cell(row=4, column=j, value=h)
    style_header(ws, 4, len(headers))
    order = [("customers", 5), ("products", 6), ("sales", 7)]
    for name, row in order:
        ws.cell(row=row, column=1, value=name)
        ws.cell(row=row, column=2, value=s["source_rows"][name]).number_format = "#,##0"
        ws.cell(row=row, column=3, value=s["target_rows"][name]).number_format = "#,##0"
        ws.cell(row=row, column=4, value=s["quarantined_rows"][name]).number_format = "#,##0"
        c = ws.cell(row=row, column=5, value=f"=IF(B{row}=0,0,C{row}/B{row})")
        c.number_format = PCT
    # NOTE: the totals row is row 8 in the sheet, but Cover references
    # B7/C7/D7/E7 — so totals live on row 7? No: rows 5,6,7 are the
    # three tables; totals go on row 8. Cover formulas are fixed below
    # to point at row 8. (Kept explicit to avoid a silent mismatch.)
    ws.cell(row=8, column=1, value="TOTAL").font = Font(bold=True)
    for col in "BCD":
        c = ws.cell(row=8, column=ord(col) - 64, value=f"=SUM({col}5:{col}7)")
        c.number_format = "#,##0"
        c.font = Font(bold=True)
    c = ws.cell(row=8, column=5, value="=IF(B8=0,0,C8/B8)")
    c.number_format = PCT
    c.font = Font(bold=True)

    # money reconciliation
    ws["A10"] = "Money reconciliation"
    ws["A10"].font = Font(bold=True, size=12, color=NAVY)
    mheaders = ["Measure", "Source (parseable)", "Migrated", "Quarantined",
                "Difference (must be 0)", "Status"]
    for j, h in enumerate(mheaders, start=1):
        ws.cell(row=11, column=j, value=h)
    style_header(ws, 11, len(mheaders))
    ws.cell(row=12, column=1, value="Sales amounts")
    ws.cell(row=12, column=2, value=s["money"]["sales_source_parseable_pkr"]).number_format = MONEY
    ws.cell(row=12, column=3, value=s["money"]["sales_target_pkr"]).number_format = MONEY
    ws.cell(row=12, column=4, value=s["money"]["sales_quarantined_pkr"]).number_format = MONEY
    ws.cell(row=12, column=5, value="=B12-C12-D12").number_format = MONEY
    ws.cell(row=12, column=6, value='=IF(ABS(E12)<0.01,"RECONCILED","MISMATCH")')
    ws.cell(row=12, column=7, value="=ABS(E12)").number_format = MONEY
    ws.cell(row=13, column=1, value="Credit limits")
    ws.cell(row=13, column=2, value=s["money"]["credit_migrated_source_pkr"]).number_format = MONEY
    ws.cell(row=13, column=3, value=s["money"]["credit_target_pkr"]).number_format = MONEY
    ws.cell(row=13, column=4, value=0).number_format = MONEY
    ws.cell(row=13, column=5, value="=B13-C13-D13").number_format = MONEY
    ws.cell(row=13, column=6, value='=IF(ABS(E13)<0.01,"RECONCILED","MISMATCH")')
    ws.cell(row=13, column=7, value="=ABS(E13)").number_format = MONEY
    ws.cell(row=11, column=7, value="Abs difference").font = H_FONT
    ws.cell(row=11, column=7).fill = HDR_FILL
    ws.cell(row=11, column=7).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.cell(row=11, column=7).border = BOX
    # formula checks: largest money difference (must be 0) and lowest
    # per-table readiness — _xlfn. prefix so LibreOffice calculates them.
    ws["A15"] = "Largest money difference across measures (must be PKR 0.00)"
    ws["A15"].font = Font(bold=True)
    ws["B15"] = "=_xlfn.AGGREGATE(14,6,G12:G13,1)"
    ws["B15"].number_format = MONEY
    ws["A16"] = "Knock-on orphan sales lines (clean rows blocked by a failed master)"
    ws["A16"].font = Font(bold=True)
    ws["B16"] = s["knock_on_orphans"]
    ws["B16"].number_format = "#,##0"
    ws["A17"] = "Lowest per-table readiness"
    ws["A17"].font = Font(bold=True)
    ws["B17"] = "=_xlfn.MINIFS(E5:E7,A5:A7,\"<>\")"
    ws["B17"].number_format = PCT
    for col, w in zip("ABCDEFG", [26, 20, 16, 16, 24, 14, 16]):
        ws.column_dimensions[col].width = w

    # ================= Quarantine =================
    ws = wb.create_sheet("Quarantine")
    title_block(ws, "Quarantine — Every Row That Cannot Migrate Yet",
                f"{len(quar)} rows, each with its reason. Fix the row (or its master), "
                "re-run the migration, and it leaves this sheet.")
    ws.cell(row=4, column=1, value="Quarantined rows:").font = Font(bold=True)
    ws.cell(row=4, column=2, value=f"=COUNTA(A6:A{5 + len(quar)})").number_format = "#,##0"
    qheaders = ["Source table", "Source row", "Key", "Reason", "Detail"]
    for j, h in enumerate(qheaders, start=1):
        ws.cell(row=5, column=j, value=h)
    style_header(ws, 5, len(qheaders))
    for i, row in enumerate(quar, start=6):
        for j, v in enumerate(row, start=1):
            c = ws.cell(row=i, column=j, value=v)
            c.border = BOX
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if j == 2:
                c.number_format = "#,##0"
    ws.auto_filter.ref = f"A5:E{5 + len(quar)}"
    ws.freeze_panes = "A6"
    for col, w in zip("ABCDE", [14, 12, 14, 30, 90]):
        ws.column_dimensions[col].width = w

    # ================= Go-No-Go =================
    ws = wb.create_sheet("Go-No-Go")
    title_block(ws, "Go / No-Go — Verdict and Conditions",
                "The verdict is CONDITIONAL GO: the move can go ahead once every "
                "condition below is met and the migration is re-run to a clean GO.")
    ws["A4"] = "Verdict"
    ws["A4"].font = Font(bold=True, size=12)
    ws["B4"] = s["verdict"]
    ws["B4"].font = Font(bold=True, size=14, color=NAVY)
    ws["A5"] = "Readiness (target ÷ source rows)"
    ws["A5"].font = Font(bold=True)
    ws["B5"] = "=Reconciliation!E8"
    ws["B5"].number_format = PCT
    ws["A6"] = "Rows to fix before cutover"
    ws["A6"].font = Font(bold=True)
    ws["B6"] = "=Reconciliation!D8"
    ws["B6"].number_format = "#,##0"

    ws["A8"] = "Must-fix list (counts are live COUNTIFs over the Quarantine sheet)"
    ws["A8"].font = Font(bold=True, size=12, color=NAVY)
    mheaders = ["Reason", "Rows", "Fix"]
    for j, h in enumerate(mheaders, start=1):
        ws.cell(row=9, column=j, value=h)
    style_header(ws, 9, len(mheaders))
    fixes = [
        ("duplicate_cust_code", "Keep the first occurrence; correct or delete the copy"),
        ("unparseable_credit_limit", "Confirm the real credit limit with the customer"),
        ("unparseable_since_date", "Confirm the date from the paper file"),
        ("missing_or_zero_price", "Set the selling price before the move"),
        ("duplicate_prod_code_normalised", "Keep the first occurrence; correct or delete the copy"),
        ("orphan_cust_code", "Add the missing customer, or correct the code on the bill"),
        ("orphan_prod_code", "Add the missing product, or correct the code on the bill"),
        ("duplicate_bill_line", "Keep the first copy; drop the duplicate"),
        ("amount_mismatch", "Re-check the bill against qty × unit price — do not guess"),
        ("unparseable_or_zero_amount", "Confirm the real amount from the paper bill"),
        ("unparseable_bill_date", "Confirm the date from the paper bill"),
        ("unparseable_qty", "Confirm the quantity from the paper bill"),
    ]
    qlast = 5 + len(quar)
    for i, (reason, fix) in enumerate(fixes, start=10):
        ws.cell(row=i, column=1, value=reason)
        ws.cell(row=i, column=2,
               value=f'=COUNTIF(Quarantine!$D$6:$D${qlast},A{i})').number_format = "#,##0"
        ws.cell(row=i, column=3, value=fix)
    ws.cell(row=22, column=1, value="TOTAL to fix").font = Font(bold=True)
    ws.cell(row=22, column=2, value="=SUM(B10:B21)").number_format = "#,##0"
    ws.cell(row=22, column=2).font = Font(bold=True)
    ws["A24"] = "Earliest affected source row among orphan product lines"
    ws["A24"].font = Font(bold=True)
    ws["B24"] = (f'=_xlfn.MINIFS(Quarantine!$B$6:$B${qlast},'
                 f'Quarantine!$D$6:$D${qlast},"orphan_prod_code")')
    ws["B24"].number_format = "#,##0"
    ws["A25"] = "Conditions for cutover"
    ws["A25"].font = Font(bold=True, size=12, color=NAVY)
    conditions = [
        "1. Fix the 12 master rows (3 customer dates, 4 credit limits, 5 product prices) — this alone unblocks 77 sales lines.",
        "2. Fix or drop the duplicate codes (6 customer, 4 product).",
        "3. Resolve the 14 planted orphan codes (8 customer, 6 product).",
        "4. Re-check the 16 bad bill values (4 dates, 3 quantities, 4 amounts, 5 mismatches) against the paper bills.",
        "5. Re-run the migration and confirm the verdict is GO — zero quarantined rows, money still reconciled.",
    ]
    for i, cond in enumerate(conditions, start=26):
        c = ws.cell(row=i, column=1, value=cond)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A26:C26")
    ws.merge_cells("A27:C27")
    ws.merge_cells("A28:C28")
    ws.merge_cells("A29:C29")
    ws.merge_cells("A30:C30")
    for col, w in zip("ABC", [32, 12, 72]):
        ws.column_dimensions[col].width = w

    wb.save(OUT)
    print(f"workbook: {OUT} ({len(quar)} quarantine rows, {len(mapping)} mappings)")


if __name__ == "__main__":
    main()

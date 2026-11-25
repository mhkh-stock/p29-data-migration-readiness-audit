"""P29 — generate the SAMPLE legacy source files for Ravi Traders.

Fictional wholesaler "Ravi Traders, Lahore" moving from a legacy
desktop billing system (BillPro 2009) to a new cloud ERP (CloudERP).
The three legacy CSVs carry realistic legacy mess, planted on
disjoint rows so every defect count can be verified exactly:

  customers (150 rows): 6 duplicate codes, 8 blank phones,
      4 unparseable credit limits, 3 unparseable since-dates,
      2 invalid statuses                    (23 defects)
  products (60 rows): 4 duplicate codes after normalisation
      (hyphen dropped, e.g. P-012 vs P012), 5 blank/zero prices,
      3 missing categories                  (12 defects)
  sales (600 rows): 8 orphan customer codes, 6 orphan product
      codes, 5 duplicate bill lines, 4 unparseable bill dates,
      3 unparseable quantities, 4 unparseable/zero amounts,
      5 amount mismatches (qty x price != amount)  (35 defects)

70 defects in total. 57 of them quarantine the row; 13 are warnings
(blank phone, invalid status, missing category) that migrate with a
documented default. The manifest records the planted counts as the
generator plants them — nothing is hand-typed.

Seed 29, deterministic: re-running regenerates byte-identical files.
Usage:  python3 src/generate_data.py
"""
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SEED = 29

FIRST = ["Ahmed", "Bilal", "Usman", "Ali", "Hassan", "Fatima", "Ayesha",
         "Zainab", "Omar", "Sana", "Imran", "Nadia", "Tariq", "Maryam",
         "Shahid", "Hina", "Kamran", "Rabia", "Faisal", "Mehwish"]
LAST = ["Khan", "Malik", "Sheikh", "Butt", "Chaudhry", "Raza", "Ahmed",
        "Hussain", "Qureshi", "Siddiqui", "Iqbal", "Anwar", "Gill",
        "Rana", "Baig", "Mirza"]
CITIES = ["Lahore", "Karachi", "Faisalabad", "Rawalpindi", "Multan",
          "Gujranwala", "Sialkot", "Peshawar", "Islamabad", "Hyderabad"]
PRODUCTS = [
    ("LED Bulb 9W", "Electronics"), ("Ceiling Fan 56in", "Electronics"),
    ("Electric Iron", "Electronics"), ("Extension Board 5m", "Electronics"),
    ("Rice Cooker 1.8L", "Home & Kitchen"), ("Non-stick Tawa", "Home & Kitchen"),
    ("Dinner Set 24pc", "Home & Kitchen"), ("Steel Glass Set", "Home & Kitchen"),
    ("Basmati Rice 5kg", "Groceries"), ("Cooking Oil 5L", "Groceries"),
    ("Sugar 5kg", "Groceries"), ("Washing Powder 3kg", "Groceries"),
    ("Cotton Lawn 3pc", "Clothing"), ("Men Kurta", "Clothing"),
    ("Bed Sheet Double", "Clothing"), ("Towel Set", "Clothing"),
    ("Hammer 500g", "Hardware"), ("Screwdriver Set", "Hardware"),
    ("PVC Pipe 4in 10ft", "Hardware"), ("Wall Paint 4L", "Hardware"),
]
BASE_PRICE = {"Electronics": (900, 8500), "Home & Kitchen": (450, 6500),
              "Groceries": (280, 4200), "Clothing": (650, 5200),
              "Hardware": (180, 3800)}


def fmt_money(n):
    """Legacy style: amounts as text with thousand separators."""
    return f"{n:,}"


def fmt_date(d, style):
    if style == 0:
        return d.strftime("%d/%m/%Y")
    if style == 1:
        return d.strftime("%Y-%m-%d")
    return d.strftime("%d-%b-%Y")


def main():
    rng = random.Random(SEED)
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {"seed": SEED, "scenario": "Ravi Traders — BillPro 2009 to CloudERP",
                "defects": {}, "planted_rows": {}}

    def plant(table, dtype, n, rows=None):
        manifest["defects"].setdefault(table, {})[dtype] = n
        if rows is not None:
            # 1-based source-file row numbers, so the audit can prove
            # each planted defect was re-found (not just counted).
            manifest["planted_rows"].setdefault(table, {})[dtype] = sorted(rows)

    # ---------------- customers ----------------
    customers = []
    start = date(2018, 1, 1)
    for i in range(1, 151):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        since = start + timedelta(days=rng.randrange(0, 2900))
        customers.append({
            "cust_code": f"C-{i:03d}",
            "cust_name": name,
            "phone": f"03{rng.randrange(10, 99)}-{rng.randrange(1000000, 9999999)}",
            "city": rng.choice(CITIES),
            "credit_limit": fmt_money(rng.randrange(50, 2001) * 1000),
            "since_date": fmt_date(since, rng.randrange(3)),
            "status": rng.choice(["Active", "Active", "Active", "Inactive"]),
        })
    idx = list(range(150))
    rng.shuffle(idx)
    # 6 duplicate codes (later rows copy an earlier row's code).
    # Sources are rows with blank phones (idx[6:12]) — warnings only,
    # so the originals still migrate and the copies are true duplicates.
    dup_rows = idx[:6]
    for j, r in enumerate(dup_rows):
        customers[r]["cust_code"] = customers[idx[6 + j]]["cust_code"]
    plant("customers", "duplicate_cust_code", 6, [r + 1 for r in dup_rows])
    # 8 blank phones
    for r in idx[6:14]:
        customers[r]["phone"] = ""
    plant("customers", "blank_phone", 8, [r + 1 for r in idx[6:14]])
    # 4 unparseable credit limits
    for r, bad in zip(idx[14:18], ["TBD", "n/a", "1,2x,000", ""]):
        customers[r]["credit_limit"] = bad
    plant("customers", "unparseable_credit_limit", 4, [r + 1 for r in idx[14:18]])
    # 3 unparseable since dates
    for r, bad in zip(idx[18:21], ["32/13/2021", "not-a-date", ""]):
        customers[r]["since_date"] = bad
    plant("customers", "unparseable_since_date", 3, [r + 1 for r in idx[18:21]])
    # 2 invalid statuses
    for r, bad in zip(idx[21:23], ["maybe", "X"]):
        customers[r]["status"] = bad
    plant("customers", "invalid_status", 2, [r + 1 for r in idx[21:23]])

    with open(RAW / "customers_legacy.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(customers[0]))
        w.writeheader()
        w.writerows(customers)

    # ---------------- products ----------------
    products = []
    for i, (name, cat) in enumerate(PRODUCTS, start=1):
        lo, hi = BASE_PRICE[cat]
        products.append({
            "prod_code": f"P-{i:03d}",
            "prod_name": name,
            "category": cat,
            "unit_price": fmt_money(rng.randrange(lo, hi + 1)),
            "uom": rng.choice(["pcs", "pcs", "pcs", "box", "set"]),
            "stock_qty": str(rng.randrange(0, 400)),
        })
    # extra products to reach 60 rows
    for i in range(21, 61):
        name, cat = rng.choice(PRODUCTS)
        lo, hi = BASE_PRICE[cat]
        products.append({
            "prod_code": f"P-{i:03d}",
            "prod_name": f"{name} (Variant {i - 20})",
            "category": cat,
            "unit_price": fmt_money(rng.randrange(lo, hi + 1)),
            "uom": "pcs",
            "stock_qty": str(rng.randrange(0, 400)),
        })
    pidx = list(range(60))
    rng.shuffle(pidx)
    # 4 duplicate codes after normalisation (hyphen dropped).
    # Copies take the codes of CLEAN rows (pidx[12:16]) — copying a
    # defective row would make the two defects interact and the
    # counts would no longer match the manifest exactly.
    for j, r in enumerate(pidx[:4]):
        products[r]["prod_code"] = products[pidx[12 + j]]["prod_code"].replace("-", "")
    plant("products", "duplicate_prod_code_normalised", 4, [r + 1 for r in pidx[:4]])
    # 5 blank/zero prices
    for r, bad in zip(pidx[4:9], ["", "0", "", "0", ""]):
        products[r]["unit_price"] = bad
    plant("products", "missing_or_zero_price", 5, [r + 1 for r in pidx[4:9]])
    # 3 missing categories
    for r in pidx[9:12]:
        products[r]["category"] = ""
    plant("products", "missing_category", 3, [r + 1 for r in pidx[9:12]])

    with open(RAW / "products_legacy.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(products[0]))
        w.writeheader()
        w.writerows(products)

    # ---------------- sales ----------------
    cust_codes = [c["cust_code"] for c in customers]
    prod_codes = [p["prod_code"] for p in products]
    prod_price = {}
    for p in products:
        try:
            prod_price[p["prod_code"]] = float(p["unit_price"].replace(",", ""))
        except ValueError:
            prod_price[p["prod_code"]] = None
    # Codes whose master row failed migration (bad date/credit for
    # customers, missing/zero price for products) — sales pointing at
    # them are knock-on orphans, found by the audit, not planted.
    absent_cust = {customers[r]["cust_code"] for r in idx[14:21]}
    absent_prod = {products[r]["prod_code"].replace("-", "").upper()
                   for r in pidx[4:9]}
    sales = []
    base = date(2026, 1, 1)
    for i in range(600):
        pc = rng.choice(prod_codes)
        price = prod_price[pc]
        if price is None or price <= 0:
            # The bill itself still carries a real price even when the
            # product master has none — the sale is not the defect.
            price = float(rng.randrange(300, 5000))
        qty = rng.randrange(1, 21)
        amount = round(qty * price, 2)
        sales.append({
            "bill_no": f"B-{1001 + i}",
            "bill_date": fmt_date(base + timedelta(days=rng.randrange(0, 181)),
                                  rng.randrange(3)),
            "cust_code": rng.choice(cust_codes),
            "prod_code": pc,
            "qty": str(qty),
            "unit_price": fmt_money(int(price)) if price == int(price) else f"{price:,.2f}",
            "amount": fmt_money(int(amount)) if amount == int(amount) else f"{amount:,.2f}",
            "tax": fmt_money(int(round(amount * 0.05))) if rng.random() < 0.7 else "",
        })
    sidx = list(range(600))
    rng.shuffle(sidx)
    # 8 orphan customer codes
    for j, r in enumerate(sidx[:8]):
        sales[r]["cust_code"] = f"C-{900 + j}"
    plant("sales", "orphan_cust_code", 8, [r + 1 for r in sidx[:8]])
    # 6 orphan product codes
    for j, r in enumerate(sidx[8:14]):
        sales[r]["prod_code"] = f"P-{900 + j}"
    plant("sales", "orphan_prod_code", 6, [r + 1 for r in sidx[8:14]])
    # 5 duplicate bill lines (exact copies of earlier CLEAN rows whose
    # customer and product both migrate — copying a row that itself
    # fails migration would make the counts stop matching the manifest).
    dup_sources = [r for r in sidx[35:]
                   if sales[r]["cust_code"] not in absent_cust
                   and sales[r]["prod_code"].replace("-", "").upper() not in absent_prod][:5]
    for j, r in enumerate(sidx[14:19]):
        sales[r] = dict(sales[dup_sources[j]])
    plant("sales", "duplicate_bill_line", 5, [r + 1 for r in sidx[14:19]])
    # 4 unparseable bill dates
    for r, bad in zip(sidx[19:23], ["40/02/2026", "not-a-date", "", "2026-02-30"]):
        sales[r]["bill_date"] = bad
    plant("sales", "unparseable_bill_date", 4, [r + 1 for r in sidx[19:23]])
    # 3 unparseable quantities
    for r, bad in zip(sidx[23:26], ["five", "", "3 pcs"]):
        sales[r]["qty"] = bad
    plant("sales", "unparseable_qty", 3, [r + 1 for r in sidx[23:26]])
    # 4 unparseable / zero amounts
    for r, bad in zip(sidx[26:30], ["n/a", "-500", "0", ""]):
        sales[r]["amount"] = bad
    plant("sales", "unparseable_or_zero_amount", 4, [r + 1 for r in sidx[26:30]])
    # 5 amount mismatches (qty x price != amount, off by 5-20%)
    for r in sidx[30:35]:
        qty = int(sales[r]["qty"])
        price = float(sales[r]["unit_price"].replace(",", ""))
        wrong = round(qty * price * rng.choice([1.08, 0.9, 1.15, 0.85, 1.2]), 2)
        sales[r]["amount"] = fmt_money(int(wrong)) if wrong == int(wrong) else f"{wrong:,.2f}"
    plant("sales", "amount_mismatch", 5, [r + 1 for r in sidx[30:35]])

    with open(RAW / "sales_legacy.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sales[0]))
        w.writeheader()
        w.writerows(sales)

    manifest["totals"] = {
        "customers_rows": 150, "products_rows": 60, "sales_rows": 600,
        "defects_total": sum(sum(v.values()) for v in manifest["defects"].values()),
    }
    with open(RAW / "defect_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"customers: 150 rows, products: 60 rows, sales: 600 rows")
    print(f"defects planted: {manifest['totals']['defects_total']}")
    for t, d in manifest["defects"].items():
        print(f"  {t}: {d}")


if __name__ == "__main__":
    main()

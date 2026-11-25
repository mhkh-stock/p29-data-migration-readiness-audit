# P29 — Package Note (Fiverr-ready)

**Gig title:** I will audit your data migration readiness — mapping, reconciliation and a go/no-go verdict before you move systems

**What the client gets:** a migration-readiness audit of their legacy
export before they move systems — every source column mapped to its
target (with the transform rule written in plain words), a target
database built in the clean schema (SQLite star-lite: customer /
product dimensions + sales fact), a row-count + money reconciliation
that proves the move to the paisa, a quarantine file with every row
that cannot migrate yet and its reason, a lineage doc tracing every
target column back to its source file and rule, a live-formula Excel
workbook (cover + mapping + reconciliation + quarantine + go/no-go),
a 2-page report they can hand to the owner, and a verdict — GO,
CONDITIONAL GO or NO-GO — with the exact conditions for cutover.
Delivered as a GitHub repo they can re-run themselves on the next
system move.

**Honest note (in the repo, stated plainly):** this is a sample
delivery on synthetic data — a fictional wholesaler, 3 legacy files,
810 rows, 676 migrated, 134 quarantined, verdict CONDITIONAL GO. The
skill and the method are real, the business is not. The audit never
invents a price, date, quantity or amount — a missing value is
quarantined, not guessed — and stock quantities are deliberately not
migrated (they are a point-in-time count, not a master attribute).

## Tiers (Hashir's band)

| Tier | Price | Delivery | Includes |
|---|---|---|---|
| Basic | $20 | 2 days | The mapping for one system move (up to 3 source files): the source→target column map with transform rules, the row-count reconciliation, the quarantine list with every rejected row and its reason |
| Standard | $65 | 4 days | Everything in Basic + the target database built in the clean schema (SQLite, queryable), the money reconciliation to the paisa (source = migrated + quarantined), the lineage doc (every target column traced to its source file and rule), the live Excel workbook (cover + mapping + reconciliation + quarantine + go/no-go), the 2-page report PDF, the verdict with conditions for cutover |
| Premium | $140 | 6 days | Everything in Standard + up to 10 source files (or 3 systems' exports), the knock-on cascade analysis (which master rows block the most detail rows, and the cheapest fix order), a second migration run after the client fixes the first batch — to show the verdict moving toward GO, the 10 reconciliation queries left with the client for the next migration, 1 revision round |

**What's NOT included:** fixing their legacy system or its export
(this service quarantines the bad rows and names the cause — fixing
the export itself is quoted separately); running the actual cutover
(this service audits readiness and proves the migration — the cutover
itself, with its downtime and rollback plan, is a separate engagement);
guessing missing values (this service never invents a price, date,
quantity or amount — a flagged row waits for the client's own
knowledge); migrating stock quantities (this service deliberately
leaves them out — stock must be physically counted at cutover);
a live cloud migration (this service is a local audit + a target
database they load — a managed cloud move is quoted separately).

**Delivery time note:** counts from the day the client shares the
legacy exports (or a sample of them) and names the target system, not
from order placement.

**Proof this service works:** this repo's SAMPLE — 3 legacy files
(150 customers, 60 products, 600 sales, Jan–Jun 2026), 810 source
rows, 676 migrated, 134 quarantined, readiness 83.46%, sales
PKR 16,666,459.35 reconciled to the paisa
(PKR 13,830,124.00 migrated + PKR 2,836,335.35 quarantined), credit
limits PKR 138,187,000.00 reconciled, mapping coverage 21/21 (100%),
target holding 0 orphans, 0 mismatches and 0 duplicates, 70 defects
planted and all re-found, the cascade finding that fixing 12 master
rows unblocks 77 sales lines at once, 11 rows migrated with a warning
and nothing hidden, a verified 2-page report PDF, a workbook whose
formulas were recalculated in LibreOffice with zero error values, and
a full verification suite passing — plus 5 conditions for cutover the
owner can act on, in fix order.

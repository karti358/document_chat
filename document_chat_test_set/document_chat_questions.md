# Document Chat Test Set — Question & Expected Answer Bank

## Purpose

This question bank is designed to evaluate a document-chat / RAG system against the accompanying synthetic document set.

The questions intentionally cover:

- Single-document retrieval
- Cross-document retrieval
- Entity resolution
- Exact-value retrieval
- Numeric reconciliation
- Duplicate detection
- Contradiction / nuance handling
- Table and spreadsheet understanding
- Image/OCR retrieval
- Presentation-text retrieval
- Code understanding
- Temporal reasoning
- Policy vs. contract distinction
- Multi-hop questions
- Questions requiring evidence from 2–5 different files
- Questions where the answer should **not** overclaim what the documents establish

### Source files

| File | Format | Main information |
|---|---|---|
| `vendor_policy.md` | Markdown | 30-day refund window, Net-30 terms, duplicate-billing policy |
| `contract_acme.pdf` | PDF | Acme contract, PO-1042, signing date, payment/refund/duplicate-billing terms |
| `q3_invoices.xlsx` | XLSX | Q3 invoice records, vendors, PO IDs, amounts, dates, regions |
| `q3_summary.csv` | CSV | Regional invoice totals |
| `q3_review.pptx` | PPTX | Review statement about Acme and PO-1042 |
| `invoice_scan.png` | PNG | Visual invoice containing PO-1042 and $12,500 |
| `reconcile.py` | Python | Function that flags duplicate PO IDs |
| `readme.txt` | TXT | Dataset description |

---

# 1. Basic Single-Document Retrieval

## Q1. What is the refund window in the vendor policy?

**Expected answer:**  
The refund window is **30 days from the invoice date**.

**Source:** `vendor_policy.md`

**Tests:** Exact policy retrieval.

---

## Q2. What are the payment terms specified in the vendor policy?

**Expected answer:**  
The payment terms are **Net-30**.

**Source:** `vendor_policy.md`

**Tests:** Short factual retrieval.

---

## Q3. Which vendor is associated with PO-1042 in the contract?

**Expected answer:**  
**Acme Industrial Supplies Ltd.**

**Source:** `contract_acme.pdf`

---

## Q4. What is the contract ID associated with PO-1042?

**Expected answer:**  
The contract ID is **ACME-PO1042-2024**.

**Source:** `contract_acme.pdf`

---

## Q5. On what date was the Acme contract signed?

**Expected answer:**  
The contract was signed on **2024-03-01**.

**Source:** `contract_acme.pdf`

---

## Q6. What does `reconcile.py` do?

**Expected answer:**  
It defines `flag_duplicate_po_ids(rows)`, which counts how many times each `po_id` occurs and returns the rows whose `po_id` occurs more than once.

**Source:** `reconcile.py`

---

## Q7. What is the amount of invoice INV-240701?

**Expected answer:**  
**$12,500.00**

**Source:** `q3_invoices.xlsx`

---

## Q8. What is the amount shown on the scanned invoice?

**Expected answer:**  
**$12,500.00**

**Source:** `invoice_scan.png`

---

# 2. Cross-Document Entity Resolution

## Q9. Which purchase order connects the Acme contract, the two duplicate-looking Q3 invoices, the review presentation, and the scanned invoice?

**Expected answer:**  
**PO-1042**.

**Sources:** `contract_acme.pdf`, `q3_invoices.xlsx`, `q3_review.pptx`, `invoice_scan.png`

**Tests:** Entity resolution across four formats.

---

## Q10. Which vendor is associated with the purchase order PO-1042?

**Expected answer:**  
**Acme Industrial Supplies Ltd.**

**Sources:** `contract_acme.pdf`, `q3_invoices.xlsx`, `invoice_scan.png`

---

## Q11. Find all documents that mention or identify PO-1042.

**Expected answer:**  
The relevant documents are:

- `vendor_policy.md` — discusses purchase orders and duplicate invoices, but does not need to identify PO-1042 as a specific transaction.
- `contract_acme.pdf` — identifies PO-1042.
- `q3_invoices.xlsx` — contains two PO-1042 rows.
- `q3_review.pptx` — explicitly mentions PO-1042.
- `invoice_scan.png` — shows PO-1042.
- `reconcile.py` — contains generic PO-ID duplicate detection but does not specifically contain PO-1042.
- `readme.txt` — describes PO-1042 as the central purchase order.

**Tests:** Broad retrieval and distinction between direct and indirect references.

---

# 3. Multi-Hop Contract + Invoice Questions

## Q12. The contract says the vendor is Acme and was signed on 2024-03-01. What purchase order does it cover, and what two invoice IDs for that PO appear in Q3?

**Expected answer:**  
The contract covers **PO-1042**. The two Q3 invoices are:

- `INV-240701`
- `INV-240718`

**Sources:** `contract_acme.pdf`, `q3_invoices.xlsx`

---

## Q13. How much do the two PO-1042 invoices total?

**Expected answer:**  
Each invoice is **$12,500.00**, so together they total:

**$25,000.00**

**Source:** `q3_invoices.xlsx`

---

## Q14. The review presentation says Acme paid twice on PO-1042. Does the spreadsheet show two invoices for that PO?

**Expected answer:**  
Yes. The spreadsheet contains two PO-1042 rows:

- `INV-240701` — $12,500.00
- `INV-240718` — $12,500.00

However, the presence of two invoices alone does not establish that two payments were actually made.

**Sources:** `q3_invoices.xlsx`, `q3_review.pptx`

**Important expected reasoning:**  
The system should distinguish **two invoices** from **two confirmed payments**.

---

## Q15. Does the scanned invoice corroborate either of the PO-1042 spreadsheet records?

**Expected answer:**  
Yes. The scanned invoice shows:

- PO: **PO-1042**
- Invoice: **INV-240701**
- Date: **2024-07-05**
- Amount: **$12,500.00**

These match the corresponding spreadsheet row.

**Sources:** `invoice_scan.png`, `q3_invoices.xlsx`

---

## Q16. What evidence supports the statement that PO-1042 may have been billed twice?

**Expected answer:**  
There are several pieces of evidence:

1. `q3_invoices.xlsx` contains two invoices for PO-1042.
2. Both invoices have an amount of $12,500.00.
3. `q3_review.pptx` explicitly states that Acme paid twice on PO-1042.
4. `vendor_policy.md` says duplicate invoices for the same purchase order must be investigated.
5. `contract_acme.pdf` says multiple invoices referencing PO-1042 should be reconciled before treating them as separate payable obligations.

**Important nuance:**  
These documents establish that two invoices exist and that a review document characterizes the situation as double payment. They do **not independently provide bank/payment records proving that two payments actually settled**.

---

# 4. Numeric Reconciliation

## Q17. What is the total invoice amount for the West region according to the spreadsheet?

**Expected answer:**  
The West-region invoices are:

- PO-1042 / INV-240701 — $12,500
- PO-1042 / INV-240718 — $12,500
- PO-1088 / INV-240812 — $4,700

Total:

**$29,700**

**Source:** `q3_invoices.xlsx`

---

## Q18. What West-region total is reported in the CSV?

**Expected answer:**  
**$29,700.00**

**Source:** `q3_summary.csv`

---

## Q19. Do the regional totals in the CSV reconcile to the spreadsheet?

**Expected answer:**  
Yes.

| Region | Spreadsheet total | CSV total |
|---|---:|---:|
| West | $29,700 | $29,700 |
| North | $8,200 | $8,200 |
| South | $6,400 | $6,400 |
| East | $9,100 | $9,100 |

All regional totals match.

---

## Q20. What is the total Q3 invoice value across all regions?

**Expected answer:**  

- West: $29,700
- North: $8,200
- South: $6,400
- East: $9,100

Total:

**$53,400.00**

**Sources:** `q3_invoices.xlsx`, `q3_summary.csv`

---

## Q21. What percentage of the total Q3 invoice value belongs to the West region?

**Expected answer:**  

\[
\frac{29,700}{53,400}\times100 \approx 55.62\%
\]

So approximately **55.6%**.

**Sources:** `q3_summary.csv` or `q3_invoices.xlsx`

**Tests:** Retrieval + arithmetic.

---

## Q22. Excluding PO-1042, what is the total value of the remaining invoices?

**Expected answer:**  

Total Q3 value = $53,400.

PO-1042 value = $25,000.

Therefore:

\[
53,400 - 25,000 = 28,400
\]

**Answer: $28,400.00**

---

# 5. Duplicate Detection

## Q23. Which `po_id` appears more than once in the spreadsheet?

**Expected answer:**  
**PO-1042** appears twice.

**Source:** `q3_invoices.xlsx`

---

## Q24. Which function in `reconcile.py` can be used to identify duplicate PO IDs?

**Expected answer:**  
`flag_duplicate_po_ids(rows)`

**Source:** `reconcile.py`

---

## Q25. How does `flag_duplicate_po_ids()` determine whether a PO is duplicated?

**Expected answer:**  
It:

1. Iterates through the input rows.
2. Counts occurrences of each `po_id`.
3. Iterates through the rows again.
4. Returns rows whose `po_id` has a count greater than 1.

---

## Q26. If the spreadsheet rows were passed to `flag_duplicate_po_ids`, which invoices would be returned as duplicates?

**Expected answer:**  
The two rows for PO-1042:

- `INV-240701`
- `INV-240718`

**Sources:** `q3_invoices.xlsx`, `reconcile.py`

---

## Q27. Is the duplicate-detection function itself proof that a duplicate payment occurred?

**Expected answer:**  
No.

The function only detects repeated `po_id` values in the input records. It does not inspect bank transactions, payment status, settlement records, or payment dates.

**Source:** `reconcile.py`

**Tests:** Avoiding unsupported inference.

---

# 6. Policy + Contract Reasoning

## Q28. What does the vendor policy say should happen when duplicate invoices reference the same purchase order?

**Expected answer:**  
They must be **investigated before payment**.

**Source:** `vendor_policy.md`

---

## Q29. What does the Acme contract say should be reconciled when multiple invoices reference PO-1042?

**Expected answer:**  
The parties should reconcile:

- invoice numbers,
- amounts,
- dates,
- line items,

before treating the invoices as separate payable obligations.

**Source:** `contract_acme.pdf`

---

## Q30. Are the policy and contract consistent about duplicate invoices?

**Expected answer:**  
Yes, at a high level. Both require additional review/reconciliation rather than automatically treating repeated invoices as separate valid obligations.

The policy states that duplicate invoice submissions for the same PO must be investigated before payment. The contract specifies reconciliation of invoice numbers, amounts, dates, and line items.

**Sources:** `vendor_policy.md`, `contract_acme.pdf`

---

## Q31. What is the refund window under the policy, and what does the Acme contract say about refunds?

**Expected answer:**  
The policy gives a **30-day refund window from the invoice date**.

The Acme contract says eligible refunds or credits may be requested within **30 days of the invoice date**, subject to review.

**Sources:** `vendor_policy.md`, `contract_acme.pdf`

---

## Q32. If an invoice is dated July 5, 2024, what date is 30 days after the invoice date?

**Expected answer:**  
**August 4, 2024.**

**Tests:** Date arithmetic + policy retrieval.

---

## Q33. If invoice INV-240701 dated July 5, 2024 is eligible for a refund, what is the stated deadline under the 30-day rule?

**Expected answer:**  
**August 4, 2024**, assuming the 30-day period is counted as 30 calendar days from the invoice date.

**Sources:** `vendor_policy.md`, `q3_invoices.xlsx`, `invoice_scan.png`

---

# 7. Net-30 Reasoning

## Q34. What payment terms apply to Acme invoices?

**Expected answer:**  
The documents specify **Net-30** payment terms.

**Sources:** `vendor_policy.md`, `contract_acme.pdf`, `invoice_scan.png`

---

## Q35. What would be the nominal due date for invoice INV-240701 dated July 5, 2024 under Net-30 terms?

**Expected answer:**  
**August 4, 2024.**

**Tests:** Contract/policy retrieval + date arithmetic.

---

## Q36. Does the document set contain evidence that INV-240701 was actually paid on August 4?

**Expected answer:**  
No.

The documents provide invoice information and payment terms, but they do not contain a payment transaction record establishing the actual settlement date.

---

# 8. Image / OCR Questions

## Q37. What purchase order number appears on the invoice image?

**Expected answer:**  
**PO-1042**

**Source:** `invoice_scan.png`

---

## Q38. What invoice number appears on the invoice image?

**Expected answer:**  
**INV-240701**

**Source:** `invoice_scan.png`

---

## Q39. What vendor appears on the scanned invoice?

**Expected answer:**  
**Acme Industrial Supplies Ltd.**

**Source:** `invoice_scan.png`

---

## Q40. Does the invoice image agree with the spreadsheet about the amount for INV-240701?

**Expected answer:**  
Yes. Both show **$12,500.00**.

**Sources:** `invoice_scan.png`, `q3_invoices.xlsx`

---

## Q41. What payment terms are visible on the scanned invoice?

**Expected answer:**  
**Net-30**

**Source:** `invoice_scan.png`

---

# 9. Presentation Retrieval

## Q42. What does the Q3 review presentation say about Acme and PO-1042?

**Expected answer:**  
It states:

**“Acme paid twice on PO-1042.”**

It also identifies the two invoice IDs and says each invoice amount is $12,500.00.

**Source:** `q3_review.pptx`

---

## Q43. Which two invoice IDs are mentioned in the review presentation?

**Expected answer:**  

- `INV-240701`
- `INV-240718`

**Source:** `q3_review.pptx`

---

## Q44. Does the presentation's statement "paid twice" have direct payment-record support elsewhere in the provided documents?

**Expected answer:**  
Not directly.

The spreadsheet confirms two invoices for PO-1042, but it does not contain a payment-status or settlement field. The other documents also do not provide bank/payment transaction records.

Therefore, the document set supports **duplicate invoicing / two invoice records**, while the claim of **two completed payments** appears as a statement in the presentation rather than independently verified payment evidence.

---

# 10. Code Understanding

## Q45. What input structure does `flag_duplicate_po_ids()` expect?

**Expected answer:**  
An iterable of dictionaries/rows where each row contains a `po_id` key. Other keys can also be present.

---

## Q46. What does the function return?

**Expected answer:**  
A list containing the rows whose `po_id` occurs more than once in the input.

---

## Q47. What happens if a PO occurs exactly once?

**Expected answer:**  
Its row is not returned.

---

## Q48. What happens if a PO occurs three times?

**Expected answer:**  
All three rows for that PO are returned, because its count is greater than 1.

---

## Q49. Does the function identify duplicate invoice numbers?

**Expected answer:**  
No. It specifically counts `po_id` values.

---

## Q50. Does the function compare invoice amounts?

**Expected answer:**  
No. It only examines the `po_id` field.

---

## Q51. Does the function prove that two invoices represent the same economic transaction?

**Expected answer:**  
No. A repeated `po_id` only identifies a repeated purchase-order reference. Further reconciliation of invoice numbers, amounts, dates, line items, and payment records is required.

**Sources:** `reconcile.py`, `contract_acme.pdf`, `vendor_policy.md`

---

# 11. High-Value Multi-Hop Questions

## Q52. Build a chain of evidence connecting the Acme contract to the scanned invoice.

**Expected answer:**

1. `contract_acme.pdf` identifies **Acme Industrial Supplies Ltd.**
2. The contract identifies **PO-1042**.
3. `q3_invoices.xlsx` contains invoices for PO-1042 from Acme.
4. `invoice_scan.png` identifies **Acme Industrial Supplies Ltd.**
5. The image identifies **PO-1042** and **INV-240701**.
6. The spreadsheet contains **INV-240701** for PO-1042 with an amount of **$12,500.00**, matching the image.

---

## Q53. Which documents independently corroborate the $12,500 amount associated with INV-240701?

**Expected answer:**  
The amount appears in:

- `q3_invoices.xlsx`
- `invoice_scan.png`

The review presentation also states that each of the two PO-1042 invoices is $12,500.00.

**Sources:** `q3_invoices.xlsx`, `invoice_scan.png`, `q3_review.pptx`

---

## Q54. What facts are independently repeated across at least three different files?

**Expected answer:**

### PO-1042
Appears across the contract, spreadsheet, presentation, image, and readme.

### Acme
Appears across the contract, spreadsheet, presentation, image, and readme.

### Duplicate-invoice concern
Appears in the policy, contract, spreadsheet, presentation, and code/readme context.

### $12,500 amount
Appears in the spreadsheet, presentation, and invoice image.

### Net-30
Appears in the policy, contract, and invoice image.

---

## Q55. What is the strongest cross-file evidence that INV-240701 is a real invoice record in this synthetic dataset?

**Expected answer:**  
The spreadsheet contains `INV-240701` as a structured invoice record, while the invoice image independently displays the same invoice ID, PO-1042, date, vendor, and amount.

---

# 12. Questions Requiring Arithmetic + Retrieval

## Q56. If both PO-1042 invoices were valid and payable, what would be the total payable amount?

**Expected answer:**  
**$25,000.00**

Calculation:

\[
12,500 + 12,500 = 25,000
\]

---

## Q57. What proportion of Acme's total Q3 invoices is represented by PO-1042?

**Expected answer:**  
Acme's Q3 invoices are:

- PO-1042 / INV-240701 — $12,500
- PO-1042 / INV-240718 — $12,500
- PO-1088 / INV-240812 — $4,700

Acme total:

\[
12,500 + 12,500 + 4,700 = 29,700
\]

PO-1042 share:

\[
\frac{25,000}{29,700}\times100 \approx 84.18\%
\]

So approximately **84.2%**.

**Source:** `q3_invoices.xlsx`

---

## Q58. How much larger is the PO-1042 total than the PO-1088 invoice?

**Expected answer:**  

\[
25,000 - 4,700 = 20,300
\]

**Answer: $20,300.00**

---

## Q59. What percentage of the West-region total is represented by PO-1042?

**Expected answer:**

\[
\frac{25,000}{29,700}\times100 \approx 84.18\%
\]

Approximately **84.2%**.

---

# 13. Questions About Document Consistency

## Q60. Is there a contradiction between the spreadsheet and CSV?

**Expected answer:**  
No. The regional totals in the CSV exactly match the totals calculated from the spreadsheet.

---

## Q61. Is there a contradiction between the scanned invoice and the spreadsheet?

**Expected answer:**  
No. For INV-240701, both identify:

- Acme Industrial Supplies Ltd.
- PO-1042
- $12,500.00
- 2024-07-05

---

## Q62. Is there a contradiction between the policy and contract regarding refund timing?

**Expected answer:**  
No material contradiction is present. Both specify a **30-day** period associated with the invoice date.

---

## Q63. Is the presentation's "paid twice" statement fully established by the spreadsheet?

**Expected answer:**  
No.

The spreadsheet establishes two invoices, not two completed payments. The presentation makes the stronger claim about payment.

---

# 14. Evidence Quality / Grounding Questions

## Q64. Does the document set contain bank statements proving two payments for PO-1042?

**Expected answer:**  
No.

There are no bank statements, payment transaction records, settlement IDs, or payment-status fields in the supplied files.

---

## Q65. Can we conclude that Acme committed fraud based solely on these documents?

**Expected answer:**  
No.

The documents establish a duplicate-invoice situation and contain a presentation stating that Acme paid twice, but they do not provide sufficient evidence to establish fraud.

The policy and contract explicitly call for investigation/reconciliation of duplicate invoices.

---

## Q66. Can we conclude that the two PO-1042 invoices are necessarily erroneous?

**Expected answer:**  
No.

Two invoices sharing a purchase order may require review, but the contract explicitly says that multiple invoices should be reconciled before treating them as separate payable obligations. The documents do not provide enough information about line items or payment records to determine whether the invoices are legitimately separate.

---

## Q67. What information would be needed to determine whether PO-1042 was actually paid twice?

**Expected answer:**  
Useful additional evidence would include:

- payment transaction records,
- payment status for each invoice,
- bank transaction IDs,
- settlement dates,
- invoice line items,
- purchase-order line items,
- credit notes or reversals,
- accounts-payable ledger entries.

This follows the reconciliation requirements described in the contract and policy.

---

# 15. Temporal Reasoning

## Q68. Which came first: the Acme contract signing or the PO-1042 invoices?

**Expected answer:**  
The contract was signed on **2024-03-01**.

The PO-1042 invoices are dated **2024-07-05** and **2024-07-18**.

Therefore, the contract signing preceded both invoices.

---

## Q69. How many days after the contract signing was INV-240701 issued?

**Expected answer:**  
From 2024-03-01 to 2024-07-05 is **126 days**.

---

## Q70. How many days separate the two PO-1042 invoice dates?

**Expected answer:**  
July 5 to July 18 is **13 days**.

---

## Q71. Which PO-1042 invoice is shown in the scanned image?

**Expected answer:**  
**INV-240701**, dated **2024-07-05**.

---

# 16. Questions Designed to Test Retrieval Precision

## Q72. What is the invoice amount for PO-1051?

**Expected answer:**  
**$8,200.00**

**Source:** `q3_invoices.xlsx`

---

## Q73. Which vendor issued invoice INV-240812?

**Expected answer:**  
**Acme Industrial Supplies Ltd.**

---

## Q74. Which region contains PO-1051?

**Expected answer:**  
**North**

---

## Q75. Which region contains PO-1063?

**Expected answer:**  
**South**

---

## Q76. Which region contains PO-1077?

**Expected answer:**  
**East**

---

## Q77. Which region contains all three Acme invoice records?

**Expected answer:**  
**West**

The Acme records are PO-1042 twice and PO-1088 once.

---

# 17. Aggregate Questions

## Q78. Which vendor has the largest total invoice value in the spreadsheet?

**Expected answer:**  
Acme Industrial Supplies Ltd. has:

\[
12,500 + 12,500 + 4,700 = 29,700
\]

The other vendors have:

- Borealis Components: $8,200
- Cedar Tools: $6,400
- Delta Fasteners: $9,100

Thus Acme's total is **$29,700**.

---

## Q79. How many invoice records are in the spreadsheet?

**Expected answer:**  
There are **6 invoice records**.

---

## Q80. How many unique purchase orders are in the spreadsheet?

**Expected answer:**  
There are **5 unique purchase orders**:

- PO-1042
- PO-1051
- PO-1063
- PO-1077
- PO-1088

---

## Q81. How many vendors are represented?

**Expected answer:**  
There are **4 vendors**:

- Acme Industrial Supplies Ltd.
- Borealis Components
- Cedar Tools
- Delta Fasteners

---

## Q82. How many invoices belong to Acme?

**Expected answer:**  
**3 invoices**.

Two are for PO-1042 and one is for PO-1088.

---

# 18. Complex Multi-File Investigation Questions

## Q83. Investigate PO-1042 as if you were preparing a reconciliation note. What facts can be established from the documents?

**Expected answer:**

- Vendor: **Acme Industrial Supplies Ltd.**
- Purchase order: **PO-1042**
- Contract signed: **2024-03-01**
- Q3 invoice 1: **INV-240701**, dated 2024-07-05, $12,500
- Q3 invoice 2: **INV-240718**, dated 2024-07-18, $12,500
- Combined invoice value: **$25,000**
- Both invoices are in the **West** region.
- The presentation states: **“Acme paid twice on PO-1042.”**
- The policy requires duplicate invoice submissions for the same PO to be investigated before payment.
- The contract requires reconciliation of invoice numbers, amounts, dates, and line items before treating multiple invoices as separate payable obligations.
- The supplied files do not contain independent payment transaction records.

**Conclusion expected from a grounded system:**  
There is clear evidence of two invoices for PO-1042 and a documented concern about duplicate payment, but actual payment settlement should be verified using payment records.

---

## Q84. Cross-check every available source for PO-1042 and identify which facts are corroborated and which are only asserted.

**Expected answer:**

### Corroborated across multiple structured/primary-style sources

- PO-1042 exists.
- Vendor is Acme.
- Two Q3 invoice records exist.
- Each invoice is $12,500.
- INV-240701 is dated 2024-07-05.
- Net-30 terms apply.
- Duplicate invoices require investigation/reconciliation.

### Asserted but not independently proven

- The presentation's statement that Acme **paid twice**.

There is no independent payment ledger or bank record in the dataset.

---

## Q85. If an analyst only searched the presentation, what important information would they miss?

**Expected answer:**  
They could miss:

- The actual structured invoice records in the XLSX.
- The exact invoice dates.
- The regional classification.
- The policy requirement to investigate duplicate invoices.
- The contract's detailed reconciliation requirements.
- The scanned invoice evidence for INV-240701.
- The code implementing duplicate PO detection.
- The CSV totals used for reconciliation.

**Tests:** Demonstrates why multi-document retrieval matters.

---

# 19. Questions With Potentially Misleading Premises

## Q86. How much did Acme definitely pay on PO-1042?

**Expected answer:**  
The documents show **$25,000 in two PO-1042 invoice records**, and the presentation says Acme paid twice. However, the dataset does not independently contain payment records confirming that $25,000 was actually paid.

---

## Q87. When did Acme make the second payment for PO-1042?

**Expected answer:**  
The supplied documents do not establish a payment date for a second payment.

The second invoice is dated **2024-07-18**, but an invoice date is not necessarily a payment date.

---

## Q88. Was the second PO-1042 invoice refunded?

**Expected answer:**  
The documents do not say that either PO-1042 invoice was refunded.

---

## Q89. Which employee approved the duplicate payment?

**Expected answer:**  
The supplied documents do not identify an employee who approved a duplicate payment.

---

## Q90. What bank account received the Acme payment?

**Expected answer:**  
The supplied documents do not contain bank-account information.

---

# 20. Code + Data Questions

## Q91. If `q3_invoices.xlsx` were converted into dictionaries and passed to `flag_duplicate_po_ids`, what would the function identify?

**Expected answer:**  
It would identify the two rows with **PO-1042**:

- `INV-240701`
- `INV-240718`

---

## Q92. Would the function flag INV-240701 and INV-240718 even though their invoice IDs are different?

**Expected answer:**  
Yes.

The function detects duplicate **PO IDs**, not duplicate invoice IDs.

---

## Q93. Would the function flag PO-1088?

**Expected answer:**  
No. PO-1088 appears only once.

---

## Q94. What limitation does `flag_duplicate_po_ids()` have for fraud detection?

**Expected answer:**  
It only detects repeated purchase-order identifiers. It cannot determine whether repeated invoices are legitimate, erroneous, fraudulent, paid, unpaid, refunded, or duplicates of the same line items.

---

# 21. End-to-End Questions

## Q95. Give a concise summary of the entire synthetic case.

**Expected answer:**  
Northstar Manufacturing has a synthetic vendor relationship with Acme Industrial Supplies Ltd. under PO-1042, with a contract signed on 2024-03-01. During Q3, two invoices reference PO-1042, each for $12,500, totaling $25,000. A presentation states that Acme paid twice, while the policy and contract require duplicate invoices to be investigated and reconciled. The spreadsheet records both invoices, the CSV reconciles regional totals, and the invoice image corroborates one of the invoices. The dataset does not contain independent payment records proving that both invoices were actually settled.

---

## Q96. What should an accounts-payable analyst verify before treating the two PO-1042 invoices as two valid payable obligations?

**Expected answer:**  
According to the contract and policy, the analyst should investigate/reconcile:

- invoice numbers,
- amounts,
- dates,
- line items,

and should also verify payment records/status to determine whether both invoices were actually paid.

---

## Q97. Does the CSV add information about individual invoices?

**Expected answer:**  
No. The CSV contains **regional aggregate totals**, not individual invoice records.

It can be used to verify that spreadsheet totals reconcile by region.

---

## Q98. Which file is best suited for programmatically detecting duplicate PO IDs?

**Expected answer:**  
`reconcile.py`, because it contains the `flag_duplicate_po_ids()` function.

The actual duplicate data is in `q3_invoices.xlsx`.

---

## Q99. Which file is best suited for visually verifying the invoice number and amount?

**Expected answer:**  
`invoice_scan.png`.

---

## Q100. Which files should be consulted to fully investigate the PO-1042 duplicate-invoice issue?

**Expected answer:**  
At minimum:

1. `q3_invoices.xlsx` — invoice records.
2. `contract_acme.pdf` — contractual requirements and Acme relationship.
3. `vendor_policy.md` — duplicate-invoice and payment/refund policy.
4. `q3_review.pptx` — review team's statement about the alleged double payment.
5. `invoice_scan.png` — visual corroboration of INV-240701.
6. `reconcile.py` — automated duplicate-PO detection logic.

The CSV is useful for regional reconciliation but is not essential to establishing the duplicate PO-1042 records.

---

# 22. Advanced RAG / Retrieval Evaluation Questions

## Q101. Find a fact that is present in both a policy document and an image.

**Expected answer:**  
**Net-30 payment terms** are stated in `vendor_policy.md` and shown on `invoice_scan.png`.

---

## Q102. Find a fact that appears in a PDF, spreadsheet, presentation, and image.

**Expected answer:**  
**PO-1042** appears in all four.

---

## Q103. Find a monetary amount that appears in three different file formats.

**Expected answer:**  
**$12,500.00** appears in:

- XLSX
- PPTX
- PNG

---

## Q104. Which file provides the aggregate information that can validate the spreadsheet without repeating its individual invoice rows?

**Expected answer:**  
`q3_summary.csv`.

---

## Q105. Which document provides contractual context that cannot be obtained from the invoice spreadsheet alone?

**Expected answer:**  
`contract_acme.pdf`.

It provides the contract ID, signing date, contractual payment/refund terms, and duplicate-invoice reconciliation requirement.

---

## Q106. Which document provides organizational policy context that differs from the specific Acme contract?

**Expected answer:**  
`vendor_policy.md`.

It describes the general vendor policy, whereas `contract_acme.pdf` describes the specific Acme agreement.

---

# 23. Expected Citation / Grounding Tests

For a system that supports citations, the following questions should cite the indicated files.

| Question | Expected evidence |
|---|---|
| What is the refund window? | `vendor_policy.md` |
| When was the contract signed? | `contract_acme.pdf` |
| Which PO is duplicated? | `q3_invoices.xlsx` |
| What is the West total? | `q3_summary.csv` and/or `q3_invoices.xlsx` |
| What does the presentation say? | `q3_review.pptx` |
| What amount appears in the image? | `invoice_scan.png` |
| What function detects duplicate POs? | `reconcile.py` |
| Why must duplicate invoices be reviewed? | `vendor_policy.md`, `contract_acme.pdf` |
| Are two payments actually proven? | Multiple files; absence of payment records should be stated |

---

# 24. Adversarial / Hallucination Tests

These questions are particularly useful for testing whether the document-chat system invents information.

## Q107. What was the payment transaction ID for the first Acme payment?

**Expected answer:**  
Not provided in the documents.

---

## Q108. What bank processed the Acme payment?

**Expected answer:**  
Not provided.

---

## Q109. Who in Northstar approved INV-240718?

**Expected answer:**  
Not provided.

---

## Q110. What were the line items on INV-240718?

**Expected answer:**  
The spreadsheet does not contain line-item details, and the provided invoice image corresponds to INV-240701. Therefore the line items for INV-240718 are not provided.

---

## Q111. What was Acme's bank account number?

**Expected answer:**  
Not provided.

---

## Q112. What exact date did Acme receive the second payment?

**Expected answer:**  
Not provided.

---

## Q113. Was the duplicate payment caused by an accounts-payable system bug?

**Expected answer:**  
Not established by the documents.

---

## Q114. Was Acme responsible for creating the duplicate invoice?

**Expected answer:**  
The documents do not establish responsibility.

---

# 25. Benchmark Questions for Multi-Hop Retrieval

## Q115. Starting from the contract signing date, identify the vendor, PO, first invoice, amount, and applicable payment terms.

**Expected answer:**

- Contract signing date: **2024-03-01**
- Vendor: **Acme Industrial Supplies Ltd.**
- PO: **PO-1042**
- First Q3 invoice: **INV-240701**
- First invoice amount: **$12,500.00**
- Payment terms: **Net-30**

**Sources:** `contract_acme.pdf`, `q3_invoices.xlsx`, `vendor_policy.md`

---

## Q116. Starting from the invoice image, trace the same transaction through the spreadsheet and contract.

**Expected answer:**

The image shows:

- Acme Industrial Supplies Ltd.
- PO-1042
- INV-240701
- 2024-07-05
- $12,500.00

The spreadsheet contains the same invoice ID, PO, date, vendor, and amount.

The contract identifies Acme as the vendor associated with PO-1042 and records the contract signing date as 2024-03-01.

---

## Q117. Starting from the Python duplicate-detection function, identify the actual duplicate in the invoice data and then find the policy governing what should happen next.

**Expected answer:**

1. `reconcile.py` flags repeated `po_id` values.
2. `q3_invoices.xlsx` shows that **PO-1042** occurs twice.
3. `vendor_policy.md` says duplicate invoice submissions for the same PO must be investigated before payment.
4. `contract_acme.pdf` additionally requires reconciliation of invoice numbers, amounts, dates, and line items.

---

## Q118. Use the CSV to verify whether the West-region invoices in the spreadsheet have been correctly aggregated, then identify the contribution of PO-1042.

**Expected answer:**

Spreadsheet West total:

\[
12,500 + 12,500 + 4,700 = 29,700
\]

CSV West total:

**$29,700**

PO-1042 contributes:

\[
12,500 + 12,500 = 25,000
\]

Thus PO-1042 represents approximately:

\[
25,000/29,700 \times 100 \approx 84.2\%
\]

of the West-region total.

---

# 26. Suggested Scoring Dimensions

A document-chat system can be evaluated on more than exact answer matching.

### Retrieval correctness
Did the system find the right document(s)?

### Cross-document retrieval
Did it retrieve multiple relevant files when the question required them?

### Entity resolution
Did it understand that `PO-1042`, Acme, and the invoice records refer to the same case?

### Numeric reasoning
Did it correctly calculate totals and percentages?

### Temporal reasoning
Did it distinguish invoice dates from payment dates?

### Evidence grounding
Did it distinguish what the documents prove from what they merely claim?

### Contradiction handling
Did it recognize that "two invoices" is not automatically equivalent to "two completed payments"?

### OCR/image retrieval
Did it extract PO, invoice number, date, and amount from the image?

### Code understanding
Did it understand what `flag_duplicate_po_ids()` actually does?

### Hallucination resistance
Did it refuse to invent payment IDs, bank details, approvers, line items, or payment dates?

### Citation quality
Did it cite the specific supporting document(s), rather than citing an unrelated retrieved file?

---

# 27. Compact Golden Set

For quick automated regression testing, these 15 questions cover most capabilities:

1. What is the refund window?
2. What are the payment terms?
3. Who is the vendor for PO-1042?
4. When was the Acme contract signed?
5. Which PO appears twice in the spreadsheet?
6. What are the two invoice IDs for PO-1042?
7. What is the combined value of the two PO-1042 invoices?
8. Does the scanned invoice match INV-240701?
9. What does the Q3 review presentation say about PO-1042?
10. Do the CSV regional totals reconcile to the spreadsheet?
11. What does `flag_duplicate_po_ids()` do?
12. Does the dataset prove that two payments actually occurred?
13. What does the policy require when duplicate invoices exist?
14. What does the contract require before treating multiple invoices as separate obligations?
15. Summarize the complete PO-1042 case using evidence from all relevant files.

## Golden Answers

1. **30 days from invoice date.**
2. **Net-30.**
3. **Acme Industrial Supplies Ltd.**
4. **2024-03-01.**
5. **PO-1042.**
6. **INV-240701 and INV-240718.**
7. **$25,000.00.**
8. **Yes; PO-1042, INV-240701, 2024-07-05, and $12,500 match.**
9. **“Acme paid twice on PO-1042.”**
10. **Yes; all four regional totals match.**
11. **It returns rows whose `po_id` occurs more than once.**
12. **No independent payment records are provided.**
13. **Investigate duplicate invoice submissions before payment.**
14. **Reconcile invoice numbers, amounts, dates, and line items.**
15. **Two PO-1042 invoices totaling $25,000 are recorded for Acme; the presentation says Acme paid twice, while the policy/contract require reconciliation, and no independent payment records prove two completed payments.**

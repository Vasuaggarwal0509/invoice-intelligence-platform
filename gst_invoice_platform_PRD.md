# GST Invoice Intelligence Platform — Complete Product & Startup Reference

## What This Document Is

This is your complete engineering, product, and startup reference for building an
AI-powered GST invoice ingestion, validation, and accounting entry platform.
It covers what to build, how to build it, why it's a real business, where the
research frontiers are, and why this gap exists despite large competitors in the market.

Read this before writing a single line of code.

---

## 1. The Problem — Precisely Stated

### What Actually Happens in an Indian SMB or CA Firm Today

A clothing wholesaler in Kanpur receives 200 purchase invoices per month from 60 vendors.
Each invoice arrives differently:
- Some as PDF email attachments
- Some as WhatsApp images (photographed paper invoices)
- Some as printed paper handed by delivery person
- Some as e-invoices from the government IRP portal (IRN + QR code)
- A few as Excel files from large vendors

The accountant or CA:
1. Opens each one manually
2. Reads the GSTIN, invoice number, date, HSN codes, taxable amount, CGST, SGST, IGST
3. Checks if the vendor's GSTIN is valid and active
4. Types all of this into Tally or Excel(mainly-csvs)
5. At month end, manually reconciles what was entered against GSTR-2B
   (what the government says your suppliers filed for you)
6. If there's a mismatch — supplier filed wrong or late — the ITC claim is blocked

**The real cost of this process:**
- 15-20 minutes per invoice on average
- 200 invoices = 50-60 hours per month of manual work per client
- A CA firm managing 30 clients does this 30 times over
- Errors cause blocked ITC — directly impacts working capital
- A ₹50 lakh ITC dispute with the GST department is not a paperwork problem.
  It is a business survival problem.

### Why Existing Solutions Don't Fully Solve This

| Solution | What It Does | What It Doesn't Do |
|---|---|---|
| Tally Prime | Accounting + GST filing | Manual data entry still required; no email ingestion; no AI extraction |
| Zoho Books | Cloud accounting | Same — user manually enters or uploads CSV; no bulk WhatsApp image processing |
| ClearTax | GST return filing | Takes already-structured data; doesn't handle raw invoice ingestion |
| AWS Textract | OCR extraction | Raw text only; no GST logic, no GSTIN validation, no Tally integration, no workflow |
| ChatGPT / Claude | Can read one invoice | No bulk processing, no automation, no API integrations, no audit trail, not a product |

**The gap is not OCR. The gap is the workflow that surrounds OCR.**

---

## 2. Why Big Tech Doesn't Solve This — The Honest Answer

This is one of the most important strategic questions. The answer is not that the problem is
technically too hard. The answer is structural.

### Reason 1: GST Compliance Is Hyperlocal and Changes Constantly

GST rules in India have changed 47 times since July 2017. HSN code classifications get updated.
E-invoicing thresholds shift. New return forms appear (GSTR-2B replaced GSTR-2A logic).
RCM applicability changes by sector. The threshold for e-way bill changes.

For a global company like Google, AWS, or Microsoft, maintaining a compliance engine that
tracks Indian GST rule changes in near-real-time requires a dedicated team of Indian
tax law experts, API integrations with the GSTN portal, and continuous updates.
This is unglamorous, low-margin maintenance work. Their total addressable market
for this investment doesn't justify it when they have global enterprise priorities.

### Reason 2: Integration Work Is Deep and Unglamorous

The value of this product comes from integrating with:
- GSTN portal APIs (IRN validation, GSTR-2B download)
- Tally via TallyPrime XML/JSON API
- Zoho Books API
- WhatsApp Business API (for image invoice ingestion)
- Gmail/Outlook APIs (for email attachment ingestion)
- Multiple Indian banks for payment status

Each integration requires understanding the specific quirks of that system.
Tally's XML format is 20 years old and deeply Indian-market-specific.
GSTN APIs require specific authentication flows and handle rate limits unpredictably.

AWS builds general-purpose tools. Solving Tally XML parsing at depth for the Indian SMB market
is not a product an AWS team will ever prioritize.

### Reason 3: The SMB Market in India Is Fragmented and Price-Sensitive

Enterprise customers (SAP, Oracle territory) already have solutions.
The gap is in the 14 million GST-registered businesses in India —
most of which are SMBs with ₹50L to ₹50Cr annual turnover.

These businesses:
- Will not pay ₹50,000/month for enterprise software
- Are not speaking to AWS sales teams
- Need something that works in Hindi as well as English
- Trust local vendors more than global platforms
- Need WhatsApp support, not Zendesk tickets

Global big tech structurally cannot serve this customer. Their minimum viable enterprise
contract size, support model, and product language make them irrelevant here.

### Reason 4: The Problem Requires Domain + Engineering Simultaneously

Building this correctly requires someone who understands:
- GST law deeply enough to know what GSTR-2B reconciliation actually means
- ML/OCR well enough to handle degraded invoice images from WhatsApp
- Tally's integration model deeply enough to push structured entries
- Indian banking and payment infrastructure

This combination — tax domain knowledge + ML engineering + accounting systems integration —
is rare. Large tech companies have the engineering but not the domain depth on the ground.
Indian CA firms have the domain depth but not the engineering. The gap is real.

---

## 3. Market Context — India and International

### India

India's GST system has recorded its highest-ever gross collection of 22.08 lakh crore rupees
in 2024-25, marking a robust 9.4% increase. With over 1.51 crore registered taxpayers,
mandatory e-invoicing now extends to businesses with turnover exceeding 5 crore rupees.

Key market facts for your startup planning:
- 1.51 crore (15.1 million) registered GST taxpayers
- ~1.2 million active CA firms and accounting practices in India
- E-invoicing mandatory for >₹5 Cr turnover — compliance pressure increasing
- Blockchain technology is emerging as a direction for immutable GST audit trails
  and real-time verification of supplier invoices against GSTN records
- The government is pushing toward fully digitized B2B and B2G transactions —
  this tailwind makes the product more necessary over time, not less

Your initial target segment: **CA firms managing 10-50 SMB clients each.**
A CA firm is a multiplier — sign one CA, get 20-40 SMB clients' invoice data flowing through
your platform. This is the distribution insight that makes the business model work.

### International Equivalents

This problem exists in every country with a VAT/GST system. Your architecture,
if built country-agnostic from the start, is globally exportable.

| Region | Tax System | Equivalent Problem |
|---|---|---|
| EU (27 countries) | VAT e-invoicing mandates (2024-2028 rollout) | Same reconciliation problem; Germany, France, Italy all going mandatory |
| UK | Making Tax Digital (MTD) | HMRC requires digital records and API-connected filing |
| Australia | GST + ATO e-invoicing | Peppol network adoption underway |
| Brazil | NF-e electronic invoice | Most mature e-invoicing system in the world — 20 years old, fully digital |
| Southeast Asia | Malaysia SST, Thailand VAT, Vietnam e-invoice | All rapidly digitalizing |

The global AP automation market is estimated at $6.17 billion in 2025
and is on track to reach $11.17 billion by 2030.

The unlock for international expansion: build the core extraction + validation engine to be
country-agnostic (pluggable tax rule engine), then add country-specific rule packs as modules.
India is your beachhead. EU VAT is your Series A expansion story.

### The Uncomfortable Market Truth

A September 2025 survey found that only 4% of respondents had fully automated AP
from invoice to payment with no manual touchpoints. And 48% said they had seen
little to no cost savings from their current AP tools.

77% of companies have partially automated accounts payable, yet only 40% of invoices
are processed fully automatically through touchless invoice processing.

This means the majority of the market has already bought something and is still unsatisfied.
That is not a bad sign — that is a displacement opportunity.
You are not selling to people who don't believe in automation.
You are selling to people who tried automation and got burned by partial solutions.

---

## 4. Product Definition — What You Are Actually Building

### Core Value Proposition (One Sentence)

> Invoices arrive by email, WhatsApp, or portal — structured, validated entries appear
> in Tally or Zoho Books automatically, with GST reconciliation done before your CA
> even opens their laptop.

### What "Baseline Scope" Means

Baseline scope = the minimum product that creates real value and can charge real money.
Do not add features beyond this until baseline is generating revenue.

**Baseline scope: 4 things working end-to-end**

1. **Ingest** — receive invoices from email attachment and PDF upload
2. **Extract** — pull GSTIN, invoice number, date, HSN codes, amounts (taxable, CGST, SGST, IGST, total)
3. **Validate** — check GSTIN on government API, flag mismatches, check against GSTR-2B
4. **Export** — push structured entry to Tally XML format or show structured table for manual approval

That's it. That's the baseline. Everything else is extension.

---

## 5. Full System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER                                │
│                                                                       │
│  Email (Gmail/Outlook)  WhatsApp Business API  Manual Upload  IRP    │
│         │                      │                    │           │    │
└─────────┴──────────────────────┴────────────────────┴───────────┘    │
                                 │                                       │
                    ┌────────────▼────────────┐                         │
                    │   INGESTION SERVICE      │                         │
                    │   (FastAPI + Celery)     │                         │
                    │   - Dedup detection      │                         │
                    │   - File type routing    │                         │
                    │   - Job queue entry      │                         │
                    └────────────┬────────────┘                         │
                                 │                                       │
          ┌──────────────────────┼──────────────────────┐               │
          │                      │                      │               │
┌─────────▼─────────┐  ┌────────▼────────┐  ┌─────────▼──────────┐    │
│   OCR PIPELINE    │  │  E-INVOICE      │  │   IMAGE PIPELINE   │    │
│   (pdfplumber +   │  │  PARSER         │  │   (PaddleOCR +     │    │
│    PaddleOCR)     │  │  (IRP JSON/XML) │  │    deskew/enhance) │    │
│   Text PDFs       │  │  Structured     │  │   WhatsApp photos  │    │
└─────────┬─────────┘  └────────┬────────┘  └─────────┬──────────┘    │
          └──────────────────────┴──────────────────────┘               │
                                 │                                       │
                    ┌────────────▼────────────┐                         │
                    │   EXTRACTION ENGINE      │                         │
                    │   (Fine-tuned DeBERTa)   │                         │
                    │   - GSTIN extraction     │                         │
                    │   - Amount fields        │                         │
                    │   - HSN codes            │                         │
                    │   - Invoice metadata     │                         │
                    │   - Confidence scoring   │                         │
                    └────────────┬────────────┘                         │
                                 │                                       │
                    ┌────────────▼────────────┐                         │
                    │   VALIDATION ENGINE      │                         │
                    │   - GSTIN API check      │                         │
                    │   - GSTR-2B match        │                         │
                    │   - Duplicate detection  │                         │
                    │   - Tax math validation  │                         │
                    │   - HSN rate check       │                         │
                    └────────────┬────────────┘                         │
                                 │                                       │
          ┌──────────────────────┼──────────────────────┐               │
          │                      │                      │               │
┌─────────▼─────────┐  ┌────────▼────────┐  ┌─────────▼──────────┐    │
│   POSTGRESQL DB   │  │  REVIEW QUEUE   │  │   EXPORT ENGINE    │    │
│   (structured     │  │  (low-confidence│  │   - Tally XML      │    │
│    invoice store) │  │   + flagged)    │  │   - Zoho Books API │    │
└───────────────────┘  └────────┬────────┘  │   - Excel/CSV      │    │
                                 │           └───────────────────────┘   │
                    ┌────────────▼────────────┐                         │
                    │   DASHBOARD (React)      │                         │
                    │   - Invoice status board │                         │
                    │   - Validation flags     │                         │
                    │   - GSTR-2B reconcile    │                         │
                    │   - ITC tracker          │                         │
                    │   - Approve & export     │                         │
                    └─────────────────────────┘                         │
```

---

## 6. Technology Stack — With Justification

| Layer | Tool | Justification |
|---|---|---|
| API Framework | FastAPI | Async endpoints for WebSocket status updates; Pydantic for strict invoice field validation |
| Task Queue | Celery + Redis | Invoice processing is async-heavy; email polling, OCR, validation all run as background tasks |
| Database | PostgreSQL | ACID compliance is non-negotiable for financial data; relational schema for invoice/entity/vendor tables |
| OCR (text PDF) | pdfplumber | Best layout preservation for Indian invoice formats; handles tabular data better than PyMuPDF |
| OCR (image/scan) | PaddleOCR | Handles Hindi text on invoices; better than Tesseract on degraded photographs |
| Image preprocessing | OpenCV | Deskewing, denoising, contrast enhancement before OCR — critical for WhatsApp photos |
| NER Model | DeBERTa-base fine-tuned | Token classification for GSTIN, amounts, HSN codes, dates; you already have production experience |
| Tax validation | Custom rule engine (Python) | GST tax math rules (CGST+SGST vs IGST based on inter/intra-state), HSN rate lookup table |
| GSTIN validation | GSTN public API | Real-time taxpayer status check |
| GSTR-2B reconciliation | GSTN API + custom matching | Download 2B JSON, match against extracted invoice data |
| Deduplication | MinHash LSH | Approximate document similarity to catch duplicate invoice submissions |
| Email ingestion | Gmail API + IMAP | Poll connected mailboxes for new attachments |
| WhatsApp ingestion | WhatsApp Business API | Receive forwarded invoice images |
| Frontend | React + TailwindCSS | Dashboard, review queue, reconciliation view |
| Export: Tally | TallyPrime XML/JSON API | Direct ledger entry push |
| Export: Zoho | Zoho Books REST API | Bill creation endpoint |
| Monitoring | Prometheus + Grafana | Track: invoices/hour, extraction accuracy, validation pass rate, ITC captured |
| Deployment | Docker Compose (local) + Railway/AWS (prod) | Container-first from day one |
| Auth | JWT + role-based access | Accountant, CA, business owner roles with different permissions |

---

## 7. Database Schema

```sql
-- Businesses (your customers)
CREATE TABLE businesses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    gstin           TEXT UNIQUE,
    pan             TEXT,
    address         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Users (accountants, CAs, business owners)
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL,        -- 'owner' | 'accountant' | 'ca' | 'admin'
    business_id     UUID REFERENCES businesses(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Vendors (suppliers)
CREATE TABLE vendors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id     UUID REFERENCES businesses(id),
    name            TEXT NOT NULL,
    gstin           TEXT,
    gstin_status    TEXT,                 -- 'active' | 'cancelled' | 'suspended' | 'unverified'
    gstin_verified_at TIMESTAMPTZ,
    pan             TEXT,
    email           TEXT,
    phone           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Raw invoice files
CREATE TABLE invoice_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id     UUID REFERENCES businesses(id),
    filename        TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    source          TEXT NOT NULL,        -- 'email' | 'whatsapp' | 'upload' | 'irp'
    source_metadata JSONB,               -- email sender, whatsapp number, etc.
    status          TEXT DEFAULT 'queued',-- 'queued'|'processing'|'extracted'|'validated'|'approved'|'exported'|'failed'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    processed_at    TIMESTAMPTZ
);

-- Extracted invoice data
CREATE TABLE invoices (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id             UUID REFERENCES invoice_files(id),
    business_id         UUID REFERENCES businesses(id),
    vendor_id           UUID REFERENCES vendors(id),

    -- Core invoice fields
    invoice_number      TEXT,
    invoice_date        DATE,
    due_date            DATE,

    -- GST fields
    vendor_gstin        TEXT,
    buyer_gstin         TEXT,
    irn                 TEXT,             -- Invoice Reference Number (e-invoice)
    supply_type         TEXT,             -- 'B2B' | 'B2C' | 'B2BUR' | 'SEZWP' etc.
    transaction_type    TEXT,             -- 'intra_state' | 'inter_state'

    -- Amounts
    taxable_amount      NUMERIC(15,2),
    cgst_amount         NUMERIC(15,2),
    sgst_amount         NUMERIC(15,2),
    igst_amount         NUMERIC(15,2),
    cess_amount         NUMERIC(15,2),
    total_amount        NUMERIC(15,2),
    tds_amount          NUMERIC(15,2),

    -- Extraction metadata
    extraction_confidence FLOAT,          -- Overall confidence 0-1
    is_duplicate        BOOLEAN DEFAULT FALSE,
    duplicate_of        UUID REFERENCES invoices(id),

    -- Validation results
    gstin_valid         BOOLEAN,
    tax_math_valid      BOOLEAN,          -- Does CGST+SGST+taxable = total?
    gstr2b_matched      BOOLEAN,          -- Found in GSTR-2B?
    gstr2b_match_status TEXT,             -- 'matched'|'mismatch'|'not_found'|'pending'
    itc_eligible        BOOLEAN,

    -- Workflow
    flagged_review      BOOLEAN DEFAULT FALSE,
    flag_reasons        JSONB,            -- Array of flag reasons
    approved_by         UUID REFERENCES users(id),
    approved_at         TIMESTAMPTZ,
    exported_to         TEXT,             -- 'tally'|'zoho'|'csv'|null
    exported_at         TIMESTAMPTZ,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Line items (HSN-level detail)
CREATE TABLE invoice_line_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id      UUID REFERENCES invoices(id) ON DELETE CASCADE,
    description     TEXT,
    hsn_code        TEXT,
    hsn_description TEXT,
    quantity        NUMERIC(10,3),
    unit            TEXT,
    unit_price      NUMERIC(15,2),
    taxable_amount  NUMERIC(15,2),
    gst_rate        NUMERIC(5,2),         -- 5, 12, 18, 28
    cgst_rate       NUMERIC(5,2),
    sgst_rate       NUMERIC(5,2),
    igst_rate       NUMERIC(5,2),
    cgst_amount     NUMERIC(15,2),
    sgst_amount     NUMERIC(15,2),
    igst_amount     NUMERIC(15,2),
    confidence      FLOAT
);

-- Field-level extraction confidence (for review UI)
CREATE TABLE invoice_field_extractions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id      UUID REFERENCES invoices(id) ON DELETE CASCADE,
    field_name      TEXT NOT NULL,
    extracted_value TEXT,
    confidence      FLOAT,
    corrected_value TEXT,                 -- Human correction if any
    corrected_by    UUID REFERENCES users(id),
    corrected_at    TIMESTAMPTZ
);

-- GSTR-2B data (downloaded from GSTN)
CREATE TABLE gstr2b_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id     UUID REFERENCES businesses(id),
    return_period   TEXT NOT NULL,        -- '042026' (MMYYYY)
    supplier_gstin  TEXT NOT NULL,
    invoice_number  TEXT,
    invoice_date    DATE,
    taxable_amount  NUMERIC(15,2),
    igst            NUMERIC(15,2),
    cgst            NUMERIC(15,2),
    sgst            NUMERIC(15,2),
    itc_available   BOOLEAN,
    raw_data        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Processing audit log
CREATE TABLE processing_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         UUID REFERENCES invoice_files(id),
    step            TEXT NOT NULL,
    status          TEXT NOT NULL,
    duration_ms     INTEGER,
    error_message   TEXT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_invoices_business ON invoices(business_id);
CREATE INDEX idx_invoices_vendor ON invoices(vendor_id);
CREATE INDEX idx_invoices_status ON invoice_files(status);
CREATE INDEX idx_invoices_flagged ON invoices(flagged_review) WHERE flagged_review = TRUE;
CREATE INDEX idx_invoices_period ON invoices(invoice_date);
CREATE INDEX idx_gstr2b_period ON gstr2b_records(business_id, return_period);
CREATE INDEX idx_line_items_invoice ON invoice_line_items(invoice_id);
CREATE INDEX idx_field_extractions_invoice ON invoice_field_extractions(invoice_id);
```

---

## 8. The Validation Engine — Core Intelligence

This is what separates the product from a raw OCR tool. Every check here has a
real-world consequence for the business if it fails silently.

```python
class InvoiceValidator:

    def validate_gstin_format(self, gstin: str) -> ValidationResult:
        """
        GSTIN format: 15 characters
        Characters 1-2: State code (01-38)
        Characters 3-12: Supplier PAN
        Character 13: Entity number (1-9, A-Z)
        Character 14: 'Z' always
        Character 15: Checksum digit
        Compute checksum using modulo-36 algorithm.
        This catches typos without hitting the API.
        """

    def validate_gstin_active(self, gstin: str) -> ValidationResult:
        """
        Hit GSTN public API: https://api.cleartax.in/gstn/v1/{gstin}
        Check: taxpayer status = 'Active'
        If 'Cancelled' or 'Suspended' — ITC cannot be claimed.
        Cache result for 24 hours (GSTIN status doesn't change hourly).
        """

    def validate_tax_math(self, invoice: Invoice) -> ValidationResult:
        """
        For intra-state: taxable_amount * (cgst_rate + sgst_rate) / 100 = cgst + sgst
        For inter-state: taxable_amount * igst_rate / 100 = igst
        total = taxable + cgst + sgst + igst + cess - tds
        Tolerance: ±1 rupee (rounding variance in different ERP systems)
        If math fails: almost certainly an OCR extraction error.
        """

    def validate_hsn_rate(self, hsn_code: str, gst_rate: float) -> ValidationResult:
        """
        Lookup HSN code in the GST rate schedule (maintained as a local database table,
        updated quarterly from CBIC notifications).
        Flag if the extracted GST rate doesn't match the schedule for that HSN.
        Common fraud: applying 5% rate on goods that should be taxed at 18%.
        """

    def detect_duplicate(self, invoice: Invoice) -> ValidationResult:
        """
        Check: same vendor GSTIN + same invoice number + same invoice date + same amount
        This is an exact match duplicate check.
        Also run MinHash LSH on extracted text to catch near-duplicate submissions
        where one field was changed slightly to bypass exact match.
        Duplicate invoices are a significant source of AP fraud.
        """

    def match_gstr2b(self, invoice: Invoice, period: str) -> ValidationResult:
        """
        Download GSTR-2B JSON for the return period from GSTN API.
        Match by: supplier GSTIN + invoice number + invoice date
        If matched: itc_eligible = True, gstr2b_match_status = 'matched'
        If not found: gstr2b_match_status = 'not_found'
           — could mean supplier filed late. Flag for follow-up.
        If found with amount mismatch: gstr2b_match_status = 'mismatch'
           — supplier filed different amount. Serious issue. Flag immediately.
        """

    def validate_reverse_charge(self, invoice: Invoice) -> ValidationResult:
        """
        Certain categories require Reverse Charge Mechanism (RCM):
        - Unregistered supplier invoices above threshold
        - Specific service categories (legal, transport, security)
        Check vendor GSTIN registration status + service category from HSN.
        RCM invoices should not show GST charged by vendor.
        """
```

---

## 9. GST-Specific Business Logic — What Engineers Don't Know

This section documents the domain knowledge you need to build correctly.
Most engineers get this wrong because they treat GST as just "a tax." It's a system.

### The ITC (Input Tax Credit) Problem

ITC is the heart of GST. A business that buys goods pays GST.
It can offset that GST paid against GST it collects from its own customers.
This offset is the ITC.

**But ITC can only be claimed if:**
1. The supplier has filed their return (GSTR-1)
2. The government has matched it to your GSTR-2B
3. The invoice in your books matches exactly what the supplier filed
4. The supplier's GSTIN was active on the invoice date
5. The supply is not blocked (alcohol, personal use items, etc.)

A mismatch in any of these = ITC blocked = real cash impact.
Your validation engine protects businesses from losing ITC silently.

### E-Invoice vs Regular Invoice

Businesses above ₹5 Cr turnover must generate e-invoices through the government IRP portal.
An e-invoice has:
- IRN (Invoice Reference Number) — unique 64-char hash
- QR code — encodes key invoice fields signed by GSTN

Your platform should:
1. Detect if an invoice has a QR code
2. Decode the QR code
3. Compare decoded values against OCR-extracted values
4. Flag discrepancies (someone altered the PDF after IRN generation)

This QR verification feature is something NO current SMB product does well.

### The GSTR-2B vs GSTR-2A Confusion

- **GSTR-2A**: Real-time, updates as suppliers file. Not used for ITC claims.
- **GSTR-2B**: Static monthly statement, generated on 14th of each month.
  This is the source of truth for ITC eligibility.

Your reconciliation must use GSTR-2B, not 2A. Most non-specialist tools get this wrong.

### TDS on GST Invoices

Certain government buyers and large corporates deduct TDS (Tax Deducted at Source)
when paying vendors. This TDS is separate from income tax TDS.
Your extraction must identify TDS deduction fields and handle them correctly
in the Tally export (they map to a different ledger).

---

## 10. API Endpoints — Full Specification

```
AUTH
POST   /auth/signup
POST   /auth/login
POST   /auth/refresh

BUSINESSES
POST   /businesses/                     Create business profile
GET    /businesses/me                   Current user's business
PATCH  /businesses/me                   Update GSTIN, address, etc.

INVOICES
POST   /invoices/upload                 Upload one or more PDF/image files
POST   /invoices/email-sync             Trigger manual email mailbox sync
GET    /invoices/                       List invoices with filters (status, period, vendor, flag)
GET    /invoices/:id                    Full invoice detail + all validation results
PATCH  /invoices/:id/approve            Mark as approved
PATCH  /invoices/:id/reject             Mark as rejected with reason
PATCH  /invoices/:id/correct-field      Submit human correction for a field (triggers revalidation)

VALIDATION
POST   /invoices/:id/revalidate         Rerun all validation checks
GET    /invoices/:id/gstr2b-status      Get GSTR-2B match status for this invoice

VENDORS
GET    /vendors/                        List all vendors
POST   /vendors/verify-gstin            Verify a GSTIN against GSTN API
GET    /vendors/:id/invoices            All invoices from a specific vendor

GSTR-2B
POST   /gstr2b/sync/:period             Download and store GSTR-2B for a period
GET    /gstr2b/reconciliation/:period   Full reconciliation report for a period
GET    /gstr2b/itc-summary/:period      ITC eligible vs blocked summary

EXPORT
POST   /export/tally                    Body: {invoice_ids: [...]}  → Tally XML download
POST   /export/zoho                     Body: {invoice_ids: [...]}  → Push to Zoho Books API
POST   /export/csv                      Body: {invoice_ids: [...]}  → CSV download

ANALYTICS
GET    /analytics/dashboard             Total invoices, ITC claimed, flags, processing stats
GET    /analytics/vendor-health         Per-vendor GSTIN validity + filing consistency score
GET    /analytics/itc-tracker           Monthly ITC eligible vs claimed vs blocked
```

---

## 11. Frontend — Dashboard Design

### Page 1: Invoice Queue Dashboard

```
┌─────────────────────────────────────────────────────────────────────┐
│  📊 Invoice Intelligence          April 2026     [Sync Email]  [+]  │
├──────────┬──────────────────────────────────────────────────────────┤
│  FILTERS │  Showing: 47 invoices  │  Period: Apr 2026               │
│  Status  │                                                           │
│  ○ All   │  ⚠️ 8 need review  ✅ 31 validated  ⏳ 8 processing       │
│  ○ Flag  │                                                           │
│  ○ Done  ├──────────────────────────────────────────────────────────┤
│          │  VENDOR          │ AMOUNT  │ DATE    │ STATUS  │ ITC     │
│  PERIOD  ├──────────────────┼─────────┼─────────┼─────────┼─────────┤
│  Apr 26  │  Sharma Traders  │ ₹45,200 │ 3 Apr   │ ✅ Valid │ ✅ ₹6,840│
│  Mar 26  │  ABC Suppliers   │ ₹12,800 │ 1 Apr   │ ⚠️ Flag  │ ❓ Check│
│          │  XYZ Pharma      │ ₹89,400 │ 5 Apr   │ ✅ Valid │ ✅ ₹13,6k│
│  VENDORS │  Ravi Steel Co.  │ ₹2,340  │ 2 Apr   │ ❌ GSTIN │ ❌ None │
│  All ▼   │  ...             │         │         │         │         │
└──────────┴──────────────────────────────────────────────────────────┘
```

### Page 2: Invoice Detail View

```
┌──────────────────────────────┬──────────────────────────────────────┐
│   INVOICE: INV-2024-0892     │   VALIDATION RESULTS                  │
│   ABC Suppliers Pvt Ltd      │                                       │
│                              │   ✅ GSTIN format valid               │
│   [Invoice PDF/image here]   │   ✅ GSTIN active on GSTN             │
│                              │   ✅ Tax math correct                 │
│   Extracted Fields:          │   ⚠️ GSTR-2B: Not yet filed           │
│   ┌──────────────────────┐   │   ✅ No duplicate found               │
│   │ GSTIN  27AABCS... ✅│   │   ✅ HSN rate matches schedule        │
│   │ Inv No INV-0892   ✅│   │                                       │
│   │ Date   01/04/2026 ✅│   │   ITC STATUS                         │
│   │ Taxable₹10,847   ✅│   │   ⏳ Pending — supplier yet to file   │
│   │ CGST   ₹977.3    ✅│   │   Expected in GSTR-2B: May 14        │
│   │ SGST   ₹977.3    ✅│   │                                       │
│   │ Total  ₹12,802   ✅│   │   [Approve] [Reject] [Export Tally]  │
│   └──────────────────────┘   │                                       │
└──────────────────────────────┴──────────────────────────────────────┘
```

### Page 3: GSTR-2B Reconciliation

```
┌─────────────────────────────────────────────────────────────────────┐
│  GSTR-2B Reconciliation — April 2026                                │
│  Last synced: 14 Apr 2026, 11:42 AM          [Sync Now]            │
├─────────────────────────────────────────────────────────────────────┤
│  SUMMARY                                                             │
│  Total invoices in GSTR-2B:  234     Matched in our books: 218     │
│  Invoices only in GSTR-2B:   16      Invoices only in our books: 4 │
│  Amount mismatches:           3                                     │
├─────────────────────────────────────────────────────────────────────┤
│  ❌ MISMATCHES (3 invoices — action required)                        │
│  Vendor          Our Amount   GSTR-2B Amount   Difference           │
│  Ravi Steel Co.  ₹89,400      ₹89,000          ₹400 ⚠️             │
│  ...                                                                 │
├─────────────────────────────────────────────────────────────────────┤
│  ITC TRACKER                                                         │
│  Total eligible ITC:  ₹4,23,840    Claimed:  ₹3,89,200             │
│  Blocked (mismatch): ₹12,400       Pending:  ₹22,240               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 12. Build Sequence — Exact Order

```
Phase 1: Core Backend + Auth (Week 1)
├── PostgreSQL schema migrated (use Alembic)
├── FastAPI skeleton with /health
├── JWT auth: signup, login, refresh
└── Docker Compose: FastAPI + PostgreSQL + Redis

Phase 2: Upload + OCR (Week 2)
├── POST /invoices/upload — save file, create invoice_file record
├── Celery task: document type detection
├── pdfplumber extraction for text PDFs
├── PaddleOCR for image/scanned PDFs
└── Raw extracted text stored in DB

Phase 3: Extraction Engine (Week 3)
├── DeBERTa NER model loaded
├── Extract: GSTIN, amounts, dates, HSN codes
├── Confidence scoring per field
├── Store in invoices table + field_extractions table
└── Confidence threshold → flagged_review = TRUE

Phase 4: Validation Engine (Week 4)
├── GSTIN format validator (offline, no API call)
├── GSTIN active check via GSTN API
├── Tax math validator
├── Duplicate detection (exact match first, then MinHash)
└── Flag logic: any failed validation → flagged_review

Phase 5: GSTR-2B Integration (Week 5)
├── GSTN API authentication setup
├── GSTR-2B download and storage for a period
├── Reconciliation matching algorithm
├── ITC eligibility determination
└── /gstr2b/reconciliation/:period endpoint working

Phase 6: Export Engine (Week 6)
├── Tally XML format for ledger entries
├── CSV export
├── Zoho Books API bill creation (OAuth2 flow)
└── Approved invoices marked as exported

Phase 7: Email Ingestion (Week 7)
├── Gmail API OAuth integration
├── IMAP polling for new attachments
├── Filter: PDF attachments only, from known vendor emails
└── Auto-enqueue for processing

Phase 8: Dashboard Frontend (Week 8)
├── React app: Invoice queue, detail view, reconciliation
├── Status polling for processing jobs
├── Field-level confidence display with correction UI
└── Approve/reject/export actions

Phase 9: QR Code Verification (Week 9 — differentiator)
├── Detect QR code on invoice images (pyzbar)
├── Decode and parse IRP QR payload
├── Compare QR values against OCR-extracted values
└── Flag if tampering detected

Phase 10: Production (Week 10)
├── Docker Compose full stack working
├── Prometheus metrics instrumented
├── Deployed on Railway or AWS EC2
├── README with benchmark results
└── Demo video recorded
```

---

## 13. Baseline Scope vs Research Areas

### Baseline Scope (Build This First)

These are solved problems. Use existing tools. Don't research here.

- PDF text extraction → pdfplumber
- Scanned image OCR → PaddleOCR
- Named entity extraction → fine-tuned DeBERTa
- GSTIN validation → GSTN API
- GSTR-2B matching → exact string matching on invoice number + GSTIN
- Tally export → documented XML format
- Auth → JWT (standard)
- Async processing → Celery (standard)

### Research Areas (This Is Where Startups Win and Papers Get Written)

These are genuinely unsolved at scale. Each one is a competitive moat.

**Research Area 1: Low-Quality Invoice Image Enhancement**

WhatsApp-forwarded invoice photos are the hardest input.
They arrive at angle, with shadows, crumpled, photographed under bad lighting.
Current PaddleOCR accuracy on these: 60-70%.
Research direction: Super-resolution + denoising + geometric correction specifically
trained on Indian invoice photograph datasets.
Nobody has published a dataset of Indian invoice photographs with ground truth.
Building this dataset and training a specialized preprocessing model is a publishable
research contribution.

**Research Area 2: Vendor Name to GSTIN Disambiguation**

An invoice might say "Ravi Enterprises" but there are 47 GST registrations with that name.
The correct vendor must be matched to the correct GSTIN.
This is fundamentally an entity disambiguation problem.
Research direction: Train a similarity model on (vendor name, address, pin code, email)
→ GSTIN mapping. Use address normalization for Indian addresses (which are highly unstructured).
Indian address normalization alone is a research problem — no good open dataset exists.

**Research Area 3: HSN Code Prediction from Item Description**

Many small vendors write informal item descriptions ("steel rods 12mm dia")
instead of proper HSN codes. The platform must predict the correct HSN code from free text.
Research direction: Fine-tune a text classifier on the full 10,000+ entry HSN code schedule.
The complication: item descriptions on Indian invoices are often in Hinglish
(Hindi written in Roman script). Pure English models fail badly on these.
A multilingual model fine-tuned on Hinglish item descriptions is a clear research contribution.

**Research Area 4: ITC Risk Prediction**

Before the government publishes GSTR-2B, can you predict which invoices will fail reconciliation?
Research direction: Train a model on historical supplier filing behaviour patterns.
Suppliers who file late in one month tend to file late consistently.
A predictive ITC risk score (probability that this supplier's invoice will appear in GSTR-2B)
gives businesses advance warning to chase the supplier before month end.
This is a time-series classification problem on GST filing behaviour — genuinely novel.

**Research Area 5: Invoice Fraud Detection**

Duplicate invoice fraud, inflated invoices, shell company invoices — all real problems.
Research direction:
- Graph neural network on vendor-buyer-invoice networks to detect circular transaction patterns
- Anomaly detection on amount distributions per HSN code per vendor
- Detecting inconsistencies between QR code payload and invoice PDF content
ITC fraud costs the Indian government an estimated ₹50,000 Cr annually.
A fraud detection engine for invoice processors is a government procurement opportunity.

---

## 14. International Expansion Strategy

### Phase 1 (India — Months 0 to 18): Prove the Product

- 50 CA firms, 500 SMB end clients
- Focus: purchase invoice ingestion + GSTR-2B reconciliation
- Revenue model: ₹2,000-5,000/month per business or per-invoice pricing

### Phase 2 (Southeast Asia — Months 18 to 36): First International

Malaysia SST, Singapore GST, Vietnam e-invoicing are all modernizing simultaneously.
The GST logic is simpler than India (no CGST/SGST split, no ITC complexity).
Your extraction + validation engine ports directly; you swap the tax rule engine.
Target: accounting software providers in these markets as OEM/API partners.

### Phase 3 (EU VAT — Months 36+): The Large Market

The 2026 wave of global e-invoicing mandates across the EU, Latin America, and Asia-Pacific
requires businesses to process, validate, and report invoices in structured digital formats
that legacy AP tools were not designed to handle.

EU VAT e-invoicing mandates are rolling out country by country through 2028.
Germany alone has 3.5 million VAT-registered businesses.
Your architecture — pluggable tax rule engine, country-agnostic extraction,
validation framework — is the foundation for this expansion.
The Indian market is not just your target. It is your training ground.

### Monetization Models by Market

| Market | Model | Price Point |
|---|---|---|
| Indian SMBs direct | SaaS subscription | ₹1,500-4,000/month |
| Indian CA firms | Per-client pricing | ₹800-1,500/client/month |
| Indian enterprise | Annual contract + implementation | ₹5-20L/year |
| International (API) | Per-invoice pricing | $0.05-0.20/invoice |
| OEM (accounting SW) | Revenue share | 15-25% of subscription |

---

## 15. Why This Is a Better Portfolio Project Than Generic Document Intelligence

Concrete reasons for your understanding:

1. **Every validation check has a legal/financial consequence** — you cannot fake this in a notebook. The GSTIN validation, tax math check, GSTR-2B reconciliation — these must work correctly or they produce wrong financial entries.

2. **The schema complexity is real** — the invoice + line_items + gstr2b_records + field_extractions schema is what actual financial software schemas look like. Building and querying it teaches real database engineering.

3. **You will hit government API rate limits and failures** — the GSTN API is unreliable. Building retry logic, caching, and graceful degradation around a real external API is a systems engineering lesson no tutorial teaches.

4. **The domain is narrow enough to be excellent** — instead of "understands all documents," you claim "processes Indian GST purchase invoices with 97% accuracy." Narrow claims with proof are worth more than broad claims without it.

5. **Live demo has immediate value** — show a recruiter: "Upload this invoice PDF." They see structured data appear in 8 seconds with validation flags. That is more impressive than any document chatbot.

---

## 16. Common Mistakes to Avoid

- **Do not** try to handle all document types. Purchase invoices only for v1.
- **Do not** build a GST filing feature in v1. Ingestion + validation + export is the product.
- **Do not** use ChatGPT/Claude API as your extraction engine. Use DeBERTa. You need to explain how it works in interviews and you need it to be fast and offline.
- **Do not** store GSTINs without normalizing them (uppercase, trim whitespace) — matching will break.
- **Do not** build the WhatsApp integration before email + manual upload is working. WhatsApp Business API has approval delays.
- **Do not** skip the processing_log table. Silent failures in invoice processing have financial consequences.
- **Do not** cache GSTIN validation results for more than 24 hours. GSTIN status can change.
- **Do not** launch without a proper data privacy policy. You are processing financial documents. Even for a portfolio project, your deployed version should have HTTPS and proper auth.

---

*Document version: April 2026*
*Build target: May–August 2026*
*First paying customer target: September 2026*

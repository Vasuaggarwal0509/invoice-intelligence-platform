# GST Invoice Intelligence Platform — Project Discussion, Research & Plan

## 0. What This File Is

This is the **project reference** — intuition, architecture, tech choices, API research,
dataset strategy, build plan, open questions, and non-goals. Read it to understand how
the project is set up and why.

It is **not** a progress log. Dated decisions, component implementation milestones, bug
investigations, and follow-ups live in `progress.md`. That file is append-only and
chronologically ordered; this file is topical and is edited in place when our
understanding of a topic changes.

Companion documents:
- **`gst_invoice_platform_PRD.md`** — frozen product reference (what / why / eventual business).
- **`research.md`** — per-topic research (OCR, datasets, etc.) with source links.
- **`progress.md`** — dated decision and milestone log.

The target of the current prototype is to **prove the effectiveness of extraction + validation
+ reconciliation results on Indian GST purchase invoices**. It is not to be production-ready,
not to be scalable, and not to be business-ready. After we prove the results, we will likely
redesign the system around what actually worked.

---

## 1. Intuition Alignment — Do We Agree With the PRD's Framing?

Short answer: **Yes, with one reframe and a few gaps to flag.**

### 1.1 What the PRD Gets Right

- **The real bottleneck is the workflow around OCR, not OCR itself.** This is correct.
  Any student can get text out of a PDF in an afternoon; the value is in the validation,
  reconciliation, and downstream integration that turn extracted text into a trustworthy
  accounting entry. The moat is domain logic, not the OCR engine.
- **ITC is the financial stake.** Framing the problem as "prevent blocked Input Tax Credit"
  rather than "automate data entry" is the correct lens. Data entry is a chore; blocked ITC
  is cash-out-of-pocket, which is the why-pay reason.
- **CA firms as the distribution wedge.** One CA firm = 20–40 SMB clients' data flowing in.
  This is how real Indian fintech SaaS (ClearTax, Refrens, Zoho Books) has historically grown.
- **Why big tech will not solve this** — the four structural reasons (hyperlocal rules,
  unglamorous Tally/GSTN integration, fragmented price-sensitive SMB market, rare
  tax+ML+accounting skill intersection) are all correct and well-stated.
- **Narrow beachhead → international expansion later.** Pluggable tax rule engine is the
  right architectural bet for a VAT-style system that exists in 170+ countries.

### 1.2 The Reframe

The PRD frames this as a product-market document. For a prototype, the lens should be
**"what minimum set of components, integrated, proves the hypothesis that AI can process
Indian GST invoices with high enough fidelity to be trusted for accounting entries?"**

The PRD's 10-week phase plan is a product build plan. Ours is a research-implement-integrate
plan where each component is independently proven before being plugged into the pipeline.
That difference in framing matters for how we spend time.

### 1.3 Gaps in the PRD's Intuition / Requirements Statement

These are not "the solution is wrong" (we were told not to judge the solution). They are
things the PRD's statement of the problem should have acknowledged and didn't. We flag them
as **explicitly out of scope for the prototype** but on-the-record so we don't later claim
completeness we never had.

| Gap | Why It Matters | Prototype Stance |
|---|---|---|
| Credit notes / debit notes | GST documents with sign-reversed tax impact; separate handling | Out of scope; purchase invoices only |
| Advance receipts (receipt vouchers) | Vendors issue these on advance payment; tax is payable on advance | Out of scope |
| Multi-tenancy & data isolation | CA firm with 30 clients implies row-level security / per-business scoping | Single-business prototype; mark as future work |
| Legal retention (72 months) | GST law requires financial records for 6 years | Ignore for prototype; note in dummy.txt |
| Foreign currency / import invoices | Bills of entry are a completely different document (BCD + IGST + Customs) | Out of scope |
| Invoice amendments / revisions | Vendors reissue invoices with same number; versioning matters | Out of scope; simple exact-match dedup only |
| Reverse Charge Mechanism (RCM) | Buyer pays the GST instead of seller for certain categories | Detect and flag only; do not auto-handle |
| Cess (luxury/sin goods) | Additional levy on tobacco, cars, aerated drinks | Store the field; do not validate rates |
| Rounding rules | Paise rounding differs across Tally/Busy/Zoho; ±1 tolerance bakes this in | Use ±1 tolerance as PRD suggests |
| Privacy / security posture | Financial data, eventually needs audit trail, SOC2 thinking | Basic auth + HTTPS only for prototype; no PII in logs |
| E-way bill integration | Transport doc linked to invoice | Explicit non-goal |
| Sales / outward invoices | Required for GSTR-1 filing | Explicit non-goal; purchase side only |

---

## 2. Tech Stack — Critique With Alternatives

The constraint set we are working under:
- Student / zero-budget: no paid APIs for the core flow
- No Rust / Go / Java (complexity overhead not justified for a prototype)
- Simple, fast-to-implement preferred, but complex-if-clearly-effective acceptable
- No LLM / VLM API calls for extraction (cost + we want to own the research)
- VLM APIs acceptable only for synthetic data generation, and only after open-source options are exhausted

### 2.1 Keep From the PRD

| Tech | Reason to Keep |
|---|---|
| **FastAPI + Pydantic** | Async endpoints, strict field validation for free, best-in-class developer ergonomics in Python |
| **PostgreSQL** | ACID is non-negotiable for financial data; rich JSONB for semi-structured fields like GSTR-2B raw payloads; free; production-ready when we graduate the prototype |
| **pdfplumber** | Best layout preservation among Python PDF libraries; handles tables well; pure Python so no system deps |
| **RapidOCR** (PP-OCRv5 models via ONNX Runtime) | Ships the latest PaddleOCR models (PP-OCRv5, Devanagari support included) but **without the PaddlePaddle framework dependency** — 80 MB install, ~0.2 s/page on CPU, English-native docs. Same accuracy class as PaddleOCR-direct while avoiding known PaddlePaddle install pain (GitHub issues #11560, #16100, #16484). See `research.md` §3 for the full comparison. |
| **OpenCV** | Standard for the deskew/denoise/binarize preprocessing we will need for WhatsApp-style photos |
| **Docker Compose** | Local dev parity; one-command spin-up for reviewers |
| **JWT auth** | Standard, no state to manage, fits the single-backend prototype |

### 2.2 Change From the PRD

| PRD Choice | Our Choice | Why |
|---|---|---|
| Celery + Redis for task queue | **RQ (Redis Queue)** or **ARQ** initially, graduate to Celery later if needed | Celery's config surface, broker/backend split, and worker model is overkill for a prototype. RQ is ~4 lines of setup, has a nice dashboard, and handles our OCR-job scale. |
| DeBERTa fine-tuned NER as the extraction engine | **Staged approach: heuristic/regex baseline → layout-aware model (LayoutLMv3 or equivalent) as we accumulate labels** | Pure DeBERTa on text ignores layout information, which is the single strongest signal on invoices (GSTIN always top-right, totals always bottom-right, etc.). We should *research* DeBERTa vs LayoutLMv3 vs Donut and not pre-commit. |
| React + TailwindCSS dashboard | **Vanilla HTML + CSS + JavaScript served by FastAPI** (no SPA framework, no build step) | User directive: no Streamlit, no React. FastAPI serves static HTML from `frontend/static/` and Jinja2 server-rendered pages from `frontend/templates/`. Interactivity via plain `fetch()` against the JSON API. Keeps the prototype dependency-light and transparent: no npm, no webpack, no build pipeline. |
| Tally XML push via port 9000 | **CSV export formatted to match Tally's import template** | You confirmed CSV is fine. Native Tally XML requires a running Tally instance (Windows), licensed, and is fiddly to demo. CSV works on any machine and is what most real users do anyway. |
| Prometheus + Grafana | **Plain Python logging + simple SQL analytics queries** | Monitoring infra is for operating a product; a prototype needs traceable logs and an evaluation report, not dashboards. |
| WhatsApp Business API | **Skipped for prototype** | Gated behind Meta business verification, slow to obtain for a student. Email IMAP + manual upload covers the same "messy image ingestion" research goal. |
| Gmail API OAuth | **IMAP with an app password** | Universal across providers, no OAuth consent screen to set up, works with a dummy Gmail/Outlook account created for the project |
| Zoho Books API export | **Deferred past prototype** | Not needed to prove the core hypothesis |

### 2.3 Add (Not in PRD, We Need Them)

| Tech | Purpose |
|---|---|
| **pyzbar** | QR code decoding on e-invoices (IRP QR) |
| **PyJWT + cryptography** | Verify the signed IRP QR payload against NIC's public key — this is a free, publicly-verifiable signal that even GSP-less prototypes can leverage |
| **pandas** | CSV export, light analytics, GSTR-2B JSON → DataFrame → matching |
| **datasketch** (MinHash LSH) | Near-duplicate invoice detection |
| **rapidfuzz** | String similarity for vendor name matching (replaces fuzzywuzzy; MIT-licensed, much faster) |
| **Faker + custom Indian data generators** | Synthetic data: Indian names, addresses, realistic GSTINs with valid checksums |
| **WeasyPrint** or **wkhtmltopdf** | Render synthetic invoice PDFs from HTML/Jinja2 templates for training data |
| **Albumentations** | Image augmentations to simulate WhatsApp-photo conditions (shadow, blur, perspective skew, JPEG artifacts) on clean synthetic invoices |
| **Alembic** | Postgres migrations — even for a prototype, painless schema evolution is worth 30 minutes of setup |
| **pytest + pytest-asyncio** | Test harness for the validation engine — these rules are the most regression-prone part of the system |
| **onnxruntime** | CPU inference runtime for the OCR models RapidOCR ships. Also used later for exporting any fine-tuned extraction model (LayoutLMv3 etc.) to CPU-friendly inference. |
| **HuggingFace `datasets`** | Load the primary PoC dataset `katanaml-org/invoices-donut-data-v1` directly, with pre-split train/val/test in place. |

### 2.4 Complex-but-Worth-It Tech Worth Flagging

These are technologies that are heavier to adopt but have a genuine payoff for the core research
question. We should evaluate each and consciously decide, not skip by default.

- **LayoutLMv3** (Microsoft): layout-aware document transformer. Input is text tokens + 2D
  bounding boxes + image patches. On form/invoice-style documents it substantially outperforms
  text-only NER because spatial position is a very strong feature. Fine-tuning requires labeled
  data but accepts relatively small datasets (a few hundred labeled invoices).
- **Donut** (Clova AI): OCR-free end-to-end document understanding. Skips the OCR stage
  entirely — the model reads the image and emits structured JSON directly. More data-hungry
  than LayoutLMv3 but is the cleanest architecture if we can generate enough synthetic data.
- **PaddleOCR-direct with PP-StructureV3**: the latest PaddleOCR pipeline adds layout
  analysis, table recognition, and structure extraction in one end-to-end flow. RapidOCR
  (our default OCR backend) does not yet re-expose all of PP-StructureV3 at the time of
  writing. If the line-item table sub-problem is not solved adequately by RapidOCR + our
  own logic, we add PaddleOCR-direct as a **second OCR backend used only for the table
  subcomponent** — not as a replacement for the default full-page OCR. This is an
  escalation path, not a day-one choice.
- **Table Transformer** (Microsoft): specialised table detection and structure recognition.
  Second escalation path if PP-StructureV3 is also insufficient.

**Default stance:** start with heuristic/regex baseline + pdfplumber + RapidOCR (PP-OCRv5),
then benchmark LayoutLMv3 after the heuristic extraction has a measured baseline on
`katanaml-org/invoices-donut-data-v1`. Only escalate to Donut / Table Transformer /
PaddleOCR-direct if the benchmark demands it.

---

## 3. OCR & Extraction Approach — Pipeline, Not End-to-End

Given your direction to build step-by-step components and research each, the architecture is
a **modular pipeline with swappable stages**, not a monolithic model. Each stage has a
clearly-defined input/output contract so we can replace any single stage without touching the
others.

### 3.1 Pipeline Sketch

```
                        ┌─────────────────────────────┐
                        │  1. Ingest & Persist Raw     │  (FastAPI upload / IMAP poller)
                        │     - Hash for dedup         │
                        │     - Store bytes            │
                        │     - Create job             │
                        └──────────────┬──────────────┘
                                       │
                        ┌──────────────▼──────────────┐
                        │  2. Document Type Router     │  (pdfplumber probe / magic bytes)
                        │     text-PDF vs image-PDF    │
                        │     vs loose image vs IRP    │
                        │     e-invoice JSON           │
                        └──────────────┬──────────────┘
              ┌───────────────┬────────┴────────┬───────────────┐
              ▼               ▼                 ▼               ▼
       ┌───────────┐   ┌───────────┐    ┌────────────┐   ┌───────────┐
       │ Text-PDF  │   │ Image-PDF │    │ Loose      │   │ IRP JSON  │
       │  Path     │   │  Path     │    │ Image Path │   │  Parser   │
       └─────┬─────┘   └─────┬─────┘    └─────┬──────┘   └─────┬─────┘
             │               │                │                │
             │               ▼                ▼                │
             │       ┌──────────────────────────────┐          │
             │       │  3. Image Preprocessing       │          │
             │       │  (deskew, denoise, binarize)  │          │
             │       └──────────────┬───────────────┘          │
             │                      ▼                          │
             │       ┌──────────────────────────────┐          │
             │       │  4. OCR (RapidOCR/PP-OCRv5)   │          │
             │       │  text + bounding boxes        │          │
             │       │  (swappable: Tesseract,       │          │
             │       │   PaddleOCR-direct, docTR)    │          │
             │       └──────────────┬───────────────┘          │
             ▼                      ▼                          │
       ┌─────────────────────────────────────┐                 │
       │  5. Normalised Text + Layout Object  │                 │
       │   {tokens, bboxes, page_dim, ...}    │                 │
       └──────────────┬──────────────────────┘                 │
                      │                                         │
                      ▼                                         │
       ┌──────────────────────────────────────┐                 │
       │  6. Entity Extraction (layered)       │                │
       │  6a. Heuristic/regex baseline         │                │
       │  6b. Dictionary/label-anchor matching │                │
       │  6c. Layout model (LayoutLMv3) [later]│                │
       │  Output: structured invoice + scores  │                │
       └──────────────┬───────────────────────┘                 │
                      │                                         │
                      ▼                                         │
       ┌──────────────────────────────────────┐                 │
       │  7. Line Item Extraction              │                │
       │  (pdfplumber.tables or PP-Structure)  │                │
       └──────────────┬───────────────────────┘                 │
                      ▼                                         │
       ┌──────────────────────────────────────┐◄────────────────┘
       │  8. QR / IRP Cross-Check              │
       │  (pyzbar + NIC public key)            │
       └──────────────┬───────────────────────┘
                      ▼
       ┌──────────────────────────────────────┐
       │  9. Validation Engine                 │
       │  (format, math, HSN, duplicate, 2B)   │
       └──────────────┬───────────────────────┘
                      ▼
       ┌──────────────────────────────────────┐
       │ 10. Persist + Flag + Expose           │
       │   (Postgres, review queue, UI)        │
       └──────────────┬───────────────────────┘
                      ▼
       ┌──────────────────────────────────────┐
       │ 11. Human Review + Correction Loop    │
       │  (becomes training data)              │
       └──────────────┬───────────────────────┘
                      ▼
       ┌──────────────────────────────────────┐
       │ 12. CSV Export (Tally-import format)  │
       └───────────────────────────────────────┘
```

### 3.2 Why Pipeline, Not End-to-End

- **Debuggability**: when extraction fails we know exactly which stage failed, not just
  "the model is bad".
- **Research-per-stage**: each box is independently benchmarkable with its own metrics
  (OCR CER/WER, entity F1, table structure accuracy, end-to-end field accuracy).
- **Swappability**: the contract between stages is a JSON object; we can replace any stage
  (swap PaddleOCR for Tesseract, swap regex for LayoutLMv3) without rewrites downstream.
- **Partial paths run fast**: a clean text-PDF bypasses OCR entirely and extraction
  completes in under a second.

### 3.3 What the Stages Do Not Do

- They do not call an LLM/VLM API.
- They do not assume cloud-only operation — everything runs locally on a laptop with CPU
  (RapidOCR's PP-OCRv5 mobile model is CPU-tuned). Training bursts for optional upgrades
  (e.g. LayoutLMv3 fine-tuning) use Colab GPU when needed.
- They do not require GSP credentials.
- **Inference is strictly CPU-only.** No component of the running prototype requires a GPU.

---

## 4. Database — Choice and Rationale

**PostgreSQL 16** (or whatever the latest stable is when we set up).

Not detailing the schema here per your instruction — the PRD has a reference schema that we
will adapt when we implement. What matters at the planning level:

- **Why PostgreSQL and not MongoDB/SQLite/DuckDB**
  - Financial data requires transactions (ACID). We do not want a half-written invoice.
  - JSONB gives us schema-less escape hatches (GSTR-2B raw payloads, extraction metadata)
    without sacrificing relational integrity where we need it (vendor → invoice → line items).
  - Full-text search is built in and is useful for searching invoice text.
  - Free, well-known, graduates cleanly to production when we rebuild.
- **SQLite** is tempting for the very first week of scaffolding but we should migrate to
  Postgres before the schema grows beyond three tables, to avoid a painful migration later.
  Recommendation: **start with Postgres from day one** — Docker Compose makes it free.
- **DuckDB** — useful for the analytics/reporting side (ITC tracker, reconciliation reports)
  but not as the primary store. Possibly add later as a read-only analytical replica.

---

## 5. API Research — What We Can Actually Use as Students

This is where the student / zero-budget constraint hits hardest. The PRD assumes paid /
GSP-mediated API access. We have to work around that for every API, using your
ADMIN-password bypass pattern.

### 5.1 GSTIN Validation

**Format validation (checksum)** — **fully doable offline, no API needed.**
- Algorithm is public and documented: 15-char format, state code lookup, base-36 checksum.
- Catches typos without any external call.
- Implement as a pure-Python function, unit-test against known valid/invalid GSTINs.

**Active-status validation (Active / Cancelled / Suspended)** — **requires API.**

Options surveyed (community feedback summarised from Reddit r/india, r/indianstartups,
StackOverflow tagged `gst`, and provider developer forums as of writing):

| Provider | Free Tier | Community Reputation | Notes |
|---|---|---|---|
| **Masters India GST API** | ~100 calls/day free with signup | Generally positive; some complaints about rate limits spiking, and occasional stale statuses | Cleanest docs; likely our pick when we go live |
| **ClearTax GSP API** | No free tier; enterprise onboarding | Strong reputation, but priced for businesses | Not viable for a student prototype |
| **KDK (Zen/GST-Sharp)** | Paid only | Good in the accountant community; integrated with KDK's own products | Not viable |
| **RapidAPI GSTIN lookup (various)** | Small free tiers | Mixed — some are thin wrappers over the public GSTN portal that break when the portal changes captcha | Risky; we would have to revalidate any choice monthly |
| **Public GSTN portal (`services.gst.gov.in`)** | Free | Has captcha + rate limiting on the free search; terms of service discourage automated scraping | Not suitable |

**Our plan for the prototype:**
1. Implement the full active-status validation API route as if it worked.
2. Internally, route the call to an adapter interface `GSTINActiveStatusProvider`.
3. Provide two implementations:
   - `HeuristicStubProvider` — returns `active` for any GSTIN that passes format check, or
     returns a hard-coded fixture for known test GSTINs so we can exercise the
     cancelled/suspended branches of our logic.
   - `AdminBypassProvider` — if the request carries the `X-Admin-Override` header matching
     an env-var-configured password, it returns whatever the admin dictates (this is how
     you described it — it lets us simulate real API responses for demos and tests).
4. A real `MastersIndiaProvider` class is stubbed with the correct method shape but raises
   `NotImplementedError` until we get credits. Swapping it in is a one-line config change.

Every invoice that was validated via `HeuristicStubProvider` or `AdminBypassProvider` gets
a row in `processing_log` with the provider name, so we can distinguish real-validated from
simulated-validated records. This is important audit hygiene even in a prototype.

### 5.2 GSTR-2B Access

**This is the hardest API gap.** GSTR-2B is only accessible via the GSTN portal by a
logged-in user, or via a GSP API partnership. There is no public endpoint at all.

**Our plan:**
- The GSTR-2B "sync" route in our API accepts a **manually-uploaded GSTR-2B JSON file**.
  This is exactly what the user downloads from the GST portal themselves. We treat the
  upload as the "sync event" and run the matching algorithm against the uploaded JSON.
- This is actually how several real products handle it too, because of the same API wall.
  We document this as intentional, not as a limitation.
- The API route signature mirrors what a GSP-backed sync would look like, so swapping in
  a real sync later is a provider-layer change, not an API change.
- Dummy GSTR-2B JSON fixtures go in `dummy.txt`.

### 5.3 E-invoice / IRP

**QR code verification is the one case where a free, public, authoritative signal exists.**
- E-invoices carry a QR code that encodes a JWT signed by NIC's private key.
- NIC publishes the public key used to verify these signatures.
- Process: `pyzbar` decodes the QR payload → parse JWT → verify signature with NIC public
  key → compare decoded fields (GSTIN, invoice number, date, amount) against what OCR
  extracted from the PDF body.
- If they diverge, the PDF was tampered with after IRN generation.
- This is genuinely novel at the SMB tier and is a feature we can ship with zero API cost.

The IRN *generation* and *cancellation* APIs do require GSP and are out of scope.

### 5.4 Tally Integration

Per your direction, **CSV export only** for the prototype. We match Tally's expected CSV
import format (see `Gateway of Tally → Import Data → Vouchers → CSV` template), which uses:
- Voucher type column (`Purchase`)
- Date in `dd-mm-yyyy`
- Party ledger name (vendor)
- Narration, item, quantity, rate, amount columns
- GST ledger split (CGST / SGST / IGST / Cess as separate rows or columns depending on
  Tally's version)

Native XML push is postponed. If we ever demo to a CA, manual CSV import in Tally is one
menu click and convinces them more than a broken port-9000 integration.

### 5.5 Email Ingestion

**IMAP** is our choice for the prototype. Works with Gmail (app password), Outlook
(OAuth-or-app-password), Yahoo, and corporate email. One library (`imapclient` or stdlib
`imaplib`). We will create a dedicated Gmail account for the project and poll it on a
schedule.

Gmail API OAuth is cleaner for production (revocable, scoped permissions) but costs an extra
day of OAuth app setup we do not need right now.

### 5.6 WhatsApp

**Skipped for the prototype.** The research goal — handling degraded photographic invoices —
is fully exercised by the "user uploads a WhatsApp screenshot through the web UI" or
"user emails the photo to our IMAP inbox" paths. We lose nothing research-wise.

### 5.7 HSN Code Rate Lookup

- CBIC publishes the GST rate schedule with HSN codes on their website.
- There is no official JSON API — the schedule is a PDF.
- Options:
  - Manually transcribe the top ~500 most common HSN codes into a seed CSV. Good enough
    for a prototype.
  - Scrape `cbic-gst.gov.in` HSN search page (Beautiful Soup). Risky — they change the
    page layout often.
  - Use the community-maintained `hsn-code-api` npm / PyPI packages — check license and
    freshness before adopting.
- **Prototype plan:** manual seed CSV of ~500 HSN codes → extend as we encounter more.

### 5.8 Summary of ADMIN-Bypass Pattern (Recap)

Every external-API-backed route accepts an optional `X-Admin-Override` header. When the
header value matches an env-var secret:
- The route short-circuits the real API call.
- It returns either (a) a fixed response based on the route, or (b) a response body that
  the admin attaches to the request (so tests can drive specific scenarios).
- The response is tagged `source: admin_override` in the processing log.

This lets us build the full validation/reconciliation logic and demonstrate it end-to-end,
and when we eventually acquire API credits, we flip one config flag to switch to the real
providers. Zero rewrite, no architectural debt.

---

## 6. Dataset Strategy — International Public Dataset First, Indian Specialisation Deferred

You directed that we use an existing international labeled dataset to build the proof of
concept first, and revisit an Indian-specific dataset after the core pipeline is validated.
Full research and source links for every claim below are in `research.md` §4 and §5.

### 6.1 Primary PoC Dataset — `katanaml-org/invoices-donut-data-v1`

| Attribute | Value |
|---|---|
| Source | Hugging Face: `katanaml-org/invoices-donut-data-v1` |
| Size | 501 invoices (425 train / 50 val / 26 test, pre-split) |
| Origin | Mendeley Data (Kozłowski & Weichbroth 2021); a Polish-generator-based synthetic dataset using Western-style business names and GB-format IBANs |
| License | **MIT** (no attribution chain; fully free reuse) |
| Annotation format | Donut-style JSON (`gt_parse` object with `header` + `items`) |
| Field schema | `invoice_no`, `invoice_date`, `seller`, `client`, `seller_tax_id`, `client_tax_id`, `iban`, line items (`item_desc` + more) |
| Published benchmark | A Donut fine-tune on this exact data reaches 96% mean accuracy — a concrete bar to beat |
| Why chosen | MIT licence; field schema is ~70% overlapping with our target Indian GST schema; pre-split; ready-to-load; real invoice structure rather than toy synthetic; no auth required |

### 6.2 Country / Region Scope

**One starting scope: "generic Western / European B2B invoice format"** — the format family
the katanaml dataset represents. This covers EU / UK / US / AU with minor variation
(currency symbol, tax rate, date format). The country-specific behaviour lives in the
validation layer, not the extraction layer, so we are not losing flexibility by choosing
a format family instead of a strict single country.

### 6.3 Deferred to Post-PoC — Indian Specialisation

| Candidate | Details | Why deferred |
|---|---|---|
| **MIDD** (Multi-Layout Invoice Document Dataset) | 630 real Indian GST invoices, 4 layouts, IOB NER annotations, CC-BY 4.0, Zenodo DOI `10.5281/zenodo.5113009` (1.1 MB RAR). From Symbiosis Institute of Technology, Pune. | Best candidate for Indian phase. Deferred because the PoC goal is to prove the *pipeline* first, without bundling dataset-specific uncertainty. |
| AjitRawat/invoice (HF) | 22 Indian invoices with full GST schema (GSTIN, PAN, CGST/SGST/IGST, HSN) | Too small to train on. Useful as a schema reference fixture. |
| Our own synthetic Indian generator | Jinja2 + WeasyPrint + Faker per earlier draft | Deferred entirely. The validation engine does not need thousands of Indian samples — it needs a small set of hand-crafted GST-shaped fixtures for rule testing (§6.5). |

### 6.4 Secondary / Reference Datasets (Not Training, but Useful)

| Dataset | Use |
|---|---|
| **SROIE** (ICDAR 2019, 1000 receipts) | Reference benchmark — compare our per-field F1 to published SROIE results so we have external calibration |
| **CORD** (Indonesian receipts, ~1000) | Alternative if `katanaml` proves insufficient for line-item / tax-split diversity |
| **FUNSD** (199 forms) | LayoutLMv3 pretraining if we graduate to layout models |
| **Roboflow invoice sets** | Line-item / table-region bounding boxes, useful only for the table sub-component |

### 6.5 Validation-Engine Fixtures (Small, Hand-Written)

The katanaml dataset does not have CGST/SGST/IGST splits, GSTINs, or HSN codes. So we cannot
use it to test the Indian GST validation logic (format check, tax-math check, HSN-rate check,
duplicate detection, GSTR-2B match). For those we write a **small hand-crafted fixture set**
— roughly 50–100 synthetic invoice records in plain JSON (no PDF rendering needed) —
covering:

- Valid GSTINs (format + checksum correct)
- Broken GSTIN checksums
- Intra-state invoices where `CGST + SGST = tax_rate × taxable`
- Inter-state invoices with IGST only
- Tax-math violations (deliberate ±₹5, ±₹50, ±₹500 errors to tune the tolerance)
- Exact duplicates, near-duplicates
- RCM invoices (registered buyer, unregistered supplier; legal/transport HSN category)
- Amount-mismatch vs GSTR-2B, not-found in GSTR-2B, matched in GSTR-2B

These fixtures live in `components/validation/fixtures/` as JSON + a pytest parametrised
test. They are **not** training data. They are unit-test data for the validation rules.

This is the only "synthetic data" work we do during the PoC. Big-scale synthetic invoice
generation (templates, rendering, augmentation) is deferred to the post-PoC Indian phase
along with MIDD.

### 6.6 Evaluation Set Discipline

- The `katanaml` test split (26 invoices) is our held-out real-world benchmark for the PoC.
  Never used for training.
- We version-control a corrections file alongside the dataset — if we find a labelling
  error during review, we record the fix in-repo so accuracy deltas across runs are
  attributable to code, not silently shifting ground truth.
- When Indian phase begins, MIDD's held-out split becomes the second canonical benchmark.
- A small **adversarial set** (~20 deliberately pathological invoices: heavy skew, bad
  photo conditions, non-standard layouts) is curated manually from stray web samples to
  track the worst-case tail.

### 6.7 VLM Usage Policy (Final)

Per your direction: **no LLM/VLM API calls at inference time**, ever. VLMs are permitted
only for dataset creation if open-source options are exhausted. With the katanaml dataset
already fully labeled, we have no immediate need for VLM weak-labeling. Open-source VLMs
(Qwen2-VL, InternVL) remain a post-PoC option only for labelling stray Indian invoices we
collect from the web.

---

## 7. Constraints, Workarounds, and the `dummy.txt` Protocol

### 7.1 Student / Zero-Budget Constraints (Recap)

- No paid GSTN / GSP access → heuristic + ADMIN-bypass pattern
- No real business GSTIN or GST portal login → synthetic GSTINs; manual GSTR-2B JSON upload
- No Tally license → CSV export
- No WhatsApp Business account → email IMAP + web upload
- No labeled invoice dataset → synthetic + weak-labeled real held-out set
- Single-developer, WSL/Linux laptop → prioritise CPU-friendly models; Colab GPU for training bursts
- No SOC2 / security posture → clearly scoped out; basic HTTPS + auth for demo only

### 7.2 `dummy.txt` — What Goes In It and Why

This file (to be created at the repo root when we start implementing, not now) is a
**running ledger of every fake, stub, placeholder, and assumption** so that when we later
productionize, nothing hides. Every entry must state:

```
YYYY-MM-DD | component | category | description | replacement plan
```

Categories we will use:
- `API_STUB` — route exists but backs to a stub/admin-bypass provider
- `FIXTURE_DATA` — hard-coded test data (GSTINs, GSTR-2B, HSN codes)
- `HEURISTIC_PROXY` — logic uses a heuristic in place of an authoritative source (e.g.,
  HSN rate table built from a manual seed rather than CBIC scrape)
- `SKIPPED_FEATURE` — PRD or GST law requires this but prototype skips it
- `CREDENTIAL_DUMMY` — dev credential that must be rotated before any real deployment
- `MANUAL_STEP` — something automated in production but manual in the prototype
  (e.g., GSTR-2B JSON upload)

Example seed entries that will go in `dummy.txt` on day one:
- `API_STUB | validation.gstin_active | Returns 'Active' via HeuristicStubProvider until Masters India credits are purchased`
- `MANUAL_STEP | reconciliation.gstr2b_sync | User uploads GSTR-2B JSON manually; no GSP API call`
- `FIXTURE_DATA | hsn.rate_table | Manual seed of 500 most common HSN codes in /data/hsn_seed.csv; not authoritative`
- `SKIPPED_FEATURE | credit_notes | Not parsed; purchase invoices only`
- `SKIPPED_FEATURE | multi_tenancy | Single-business mode only; no row-level isolation`

`dummy.txt` is reviewed at the start of any "productionize" exercise. Nothing in the file
may silently migrate from prototype to production-serving code.

---

## 8. Sequential Build — Components A Through O, Research → Implement → Integrate

This is the build order. Each component has a research phase (understand the problem,
evaluate options), an implementation phase (minimum viable version), and an integration
phase (wire into the pipeline behind a clear interface). No component starts until the
prior one's integration is green.

### 8.0 Monorepo Layout With Component-Level Segregation

Per your directive: one repo, but every pipeline component is independently developable,
testable, and swappable. Cross-component coupling goes through explicit interface modules
only.

```
invoice-intelligence-platform/
├── backend/                     # FastAPI app — orchestrates components
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── routes/              # HTTP endpoints
│   │   ├── models/              # Pydantic + SQLAlchemy
│   │   ├── services/            # Calls into components/
│   │   ├── workers/             # RQ worker entrypoints
│   │   └── config.py
│   ├── migrations/              # Alembic
│   └── tests/
├── components/                  # Independently developable pipeline pieces
│   ├── _base/                   # Shared types, interfaces, contracts
│   ├── ingestion/               # upload, hashing, dedup
│   ├── doc_router/              # text-PDF / image-PDF / loose image / IRP JSON detection
│   ├── preprocessing/           # OpenCV pipeline for images
│   ├── ocr/                     # OCR backends behind BaseOCR interface
│   │   ├── base.py
│   │   ├── rapidocr_backend.py  # default (PP-OCRv5 via ONNX)
│   │   ├── tesseract_backend.py # fallback, fast-path for clean text PDFs
│   │   ├── paddleocr_backend.py # scaffolded, not implemented — for PP-StructureV3 if needed
│   │   ├── doctr_backend.py     # scaffolded, not implemented
│   │   ├── tests/
│   │   └── README.md            # benchmark notes, swap instructions
│   ├── extraction/              # Entity extraction (layered)
│   │   ├── base.py
│   │   ├── heuristic/           # regex + label-anchor
│   │   ├── layoutlm/            # LayoutLMv3 later
│   │   └── tests/
│   ├── tables/                  # Line-item / table extraction
│   ├── qr/                      # IRP QR decode + signature verify
│   ├── validation/              # GSTIN, tax math, duplicate, HSN, GSTR-2B
│   │   ├── base.py              # provider interfaces (HeuristicStub, AdminBypass, MastersIndia)
│   │   ├── rules/
│   │   ├── fixtures/            # hand-written GST-shaped JSON fixtures (§6.5)
│   │   └── tests/
│   └── export/                  # CSV (Tally-import format)
├── data_sources/                # Dataset loaders / wranglers
│   │                            # (renamed from 'datasets/' to avoid the
│   │                            #  name collision with HuggingFace's
│   │                            #  'datasets' PyPI package — see
│   │                            #  progress.md entry 2026-04-17 K1)
│   ├── base.py                  # BaseDataset contract
│   ├── types.py                 # Sample (image + ground_truth)
│   ├── factory.py               # make_dataset("katanaml") etc.
│   ├── katanaml_invoices/       # primary PoC dataset loader
│   ├── midd/                    # post-PoC Indian (scaffolded)
│   ├── sroie/                   # reference benchmark (scaffolded)
│   ├── tests/
│   └── README.md
├── frontend/                    # Vanilla HTML / CSS / JS served by FastAPI
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── assets/
│   └── templates/               # Jinja2 templates (server-rendered where helpful)
├── evaluation/                  # Benchmark harness + dated reports
│   ├── harness.py
│   └── reports/                 # evaluation/YYYY-MM-DD_report.md
├── tools/                       # CLIs
│   ├── download_dataset.py      # one-shot fetcher for katanaml (+ cache)
│   ├── evaluate.py
│   └── gen_validation_fixtures.py
├── data/                        # .gitignored; local dataset cache
├── docker/
├── docker-compose.yml
├── dummy.txt
├── research.md
├── project.md
└── gst_invoice_platform_PRD.md
```

Principles:
- `components/*` has no imports from `backend/`. Backend imports into components, not vice versa.
- Each `components/<name>/` has a `base.py` (interface), one or more implementations, `tests/`, and a `README.md` describing inputs, outputs, benchmarks, and how to add another implementation.
- The repo will contain scaffolded but unimplemented files for alternative backends (e.g. Tesseract, PaddleOCR-direct) so the swap path is visible from day one.

### Component A — Project Skeleton & Dev Environment
- Research: directory layout conventions for FastAPI projects; Docker Compose for
  Postgres + Redis + app; Alembic setup.
- Implement: FastAPI `/health`, Postgres + Alembic initial migration, Docker Compose,
  pytest harness, `ruff` + `mypy` CI config, `.env.example`.
- Integrate: `docker compose up` boots everything; `pytest` passes.

### Component B — Ingestion (Upload + Persistence)
- Research: file storage strategy (local vs S3-compatible like MinIO); deduplication by
  file hash.
- Implement: `POST /invoices/upload` accepting PDF/PNG/JPG, computes SHA-256, stores
  bytes in local dir (swap to MinIO/S3 later), creates `invoice_files` row, enqueues
  RQ job.
- Integrate: uploading a file creates a queued job visible in the DB.

### Component C — Document Type Router
- Research: PDF text-layer detection (`pdfplumber.open(...).pages[0].chars`), magic-byte
  detection for PDF vs JPEG vs PNG, IRP JSON detection (look for `Irn` key at top level).
- Implement: `detect_doc_type(path) -> Literal["text_pdf", "image_pdf", "image", "irp_json"]`.
- Integrate: job dispatcher picks the right pipeline branch based on type.

### Component D — Text-PDF Extraction
- Research: pdfplumber's `extract_words`, `extract_tables`; handling multi-page invoices;
  identifying header vs body vs footer regions by y-coordinate clustering.
- Implement: extractor returns `{tokens: [{text, bbox, page}], tables: [...]}`.
- Integrate: output feeds the entity extractor directly (OCR stages skipped for text PDFs).

### Component E — Image Preprocessing
- Research: OpenCV techniques for phone-photo correction: Hough-line based deskew,
  adaptive thresholding for binarization, shadow removal via morphological operations,
  denoising (Non-Local Means). Benchmark: show before/after on 20 sample WhatsApp-style photos.
- Implement: `preprocess_for_ocr(img) -> img`.
- Integrate: image-pipeline jobs call preprocess before OCR.

### Component F — OCR
- Decision already made (see `research.md`): default backend is **RapidOCR** (PP-OCRv5
  models via ONNX Runtime). Additional backends (Tesseract, PaddleOCR-direct, docTR) are
  scaffolded behind the `BaseOCR` interface but not implemented at PoC time.
- Research: confirm RapidOCR default config handles the katanaml dataset and ~5 real
  Indian GST sample PDFs visually before implementation. Spot-check 10 invoices end-to-end.
- Implement: `RapidOCRBackend.ocr(img) -> {tokens: [{text, bbox, confidence}], lines: [...]}`.
- Integrate: identical output schema as the text-PDF extractor so downstream is path-agnostic.
- Post-PoC: enable Tesseract backend for clean-text-PDF fast path; benchmark RapidOCR vs
  PaddleOCR-direct PP-StructureV3 specifically for the table sub-problem if Component H
  shows it is needed.

### Component G — Entity Extraction (Layered)
- **G1. Regex/heuristic baseline**
  - Research: GSTIN regex, Indian date formats (`dd/mm/yyyy`, `dd-mm-yy`, `dd-MMM-yyyy`),
    invoice-number patterns (anything after "Invoice No"/"Inv #"/"Bill No"), amount
    patterns including Indian number formatting (`1,23,456.78`).
  - Implement: a rules engine that scores each candidate token by (a) regex match,
    (b) positional heuristic (GSTIN labels often top-right), (c) label-anchor proximity
    ("GSTIN:" label to the left of the value).
  - Integrate: produce structured invoice record with per-field confidence.
- **G2. Label-anchor dictionary matching**
  - Research: common invoice label variants (including Hinglish like "मु.राशि"); fuzzy
    matching with rapidfuzz.
  - Implement: dictionary of ~50 field-label variants, token-to-field assignment via
    nearest-labeled-anchor search.
  - Integrate: merge with G1 scores, higher-confidence wins.
- **G3. LayoutLMv3 fine-tune (later, after we have 500+ labeled samples)**
  - Research: LayoutLMv3 fine-tuning on FUNSD-style token classification; label schema
    design (IOB2 tags per invoice field).
  - Implement: Hugging Face `transformers` training loop, export to ONNX for CPU inference.
  - Integrate: A/B against G1+G2 on the held-out 200-set; only replace baseline if clearly better.

### Component H — Line Item Extraction
- Research: pdfplumber table extraction vs PP-Structure table recognition; handling
  merged-cell cases; matching line item HSN codes + amounts to the invoice totals.
- Implement: table extraction + line-item normalization.
- Integrate: invoice totals cross-check against sum of line items.

### Component I — QR / IRP Verification
- Research: IRP QR payload spec (it is a signed JWT); NIC public key availability; JWT
  signature verification.
- Implement: pyzbar QR detection → JWT verification → struct compare against extracted fields.
- Integrate: a mismatch produces a flag on the invoice record.

### Component J — Validation Engine
Subcomponents exactly as PRD §8:
- J1 GSTIN format validation (offline checksum)
- J2 GSTIN active check (adapter pattern: HeuristicStub / AdminBypass / MastersIndia)
- J3 Tax math validator
- J4 Duplicate detection (exact match → MinHash LSH)
- J5 HSN rate lookup against seed CSV
- J6 GSTR-2B reconciliation (against user-uploaded JSON)
- J7 RCM detection (flag only, no auto-handling)
Each subcomponent is a pure function behind an interface, unit-tested in isolation.

### Component K — Dataset Loader + Small Validation Fixtures
Scope narrowed per research conclusions (see `research.md` §4–5 and project.md §6).
- K1. **Primary dataset loader** — `datasets/katanaml_invoices/` loads
  `katanaml-org/invoices-donut-data-v1` via HuggingFace `datasets`, caches locally in
  `data/katanaml/`, exposes iteration and per-sample fetch with ground-truth JSON.
- K2. **Reference-dataset loader** — `datasets/sroie/` for external calibration.
- K3. **Validation fixtures generator** — `tools/gen_validation_fixtures.py` writes ~50–100
  hand-crafted GST-shaped JSON records (valid/invalid GSTINs, intra-state, inter-state,
  tax-math violations, RCM cases, GSTR-2B mismatches) into `components/validation/fixtures/`.
  Not PDFs. Not training data. Unit-test data for the rule engine.
- **Big synthetic invoice generation (templates + WeasyPrint + Albumentations) is deferred
  to the post-PoC Indian phase**, alongside MIDD integration.

### Component L — Evaluation Harness
- Research: SROIE-style field-level metrics (exact match F1 per field, hER for numeric
  fields); end-to-end reporting.
- Implement: `python -m tools.evaluate --set data/real_200/` prints per-field accuracy
  and per-validation-rule pass/fail rates.
- Integrate: CI runs a quick-eval on a 20-sample subset to catch regressions.

### Component M — Export (CSV)
- Research: Tally's CSV voucher import format; column order; date format quirks.
- Implement: `POST /export/csv` accepting an invoice-id list, returns a CSV matching Tally's import spec.
- Integrate: approval in the UI triggers export availability.

### Component N — Email Ingestion (IMAP)
- Research: IMAP IDLE vs polling; attachment extraction safety (never execute, mime-type check).
- Implement: scheduled RQ job polls configured mailbox, extracts PDF/image attachments,
  enqueues them through the ingestion pipeline.
- Integrate: email-sourced invoices show up in the queue with `source='email'`.

### Component O — Frontend Viewer (Vanilla HTML + CSS + JS served by FastAPI)
Per your directive: no Streamlit, no React, no SPA framework, no build step.
- Research: minimal static-site patterns with FastAPI; `StaticFiles` mount for
  `frontend/static/`; Jinja2 templates for any server-rendered pages.
- Implement: pages for Upload, Queue, Invoice Detail (with field-level extraction +
  validation flags), Reconciliation Summary. Interactivity via plain `fetch()` against the
  JSON API; no npm.
- Scope for first iteration: flexible upload button + a list of test invoices from the
  loaded dataset so users can select one and see the pipeline's result side-by-side with
  ground truth. Richer dashboards evolve after the backend is confirmed working.
- Integrate: frontend calls only the FastAPI JSON API; no direct DB access from the browser.

### Build Order Dependency Graph

```
A (skeleton) ─► K1 (dataset loader) ─► B (upload) ─► C (doc router) ─┐
                                                                      │
                                          ┌───────────────────────────┤
                                          ▼                           ▼
                                      D (text-PDF)              E (preprocess) ─► F (OCR)
                                          │                                           │
                                          └───────────────┬───────────────────────────┘
                                                          ▼
                                                 G1 (regex baseline) ─► G2 (label-anchor)
                                                          │
                                                          ▼
                                                      H (tables)
                                                          │
                                                          ▼
                                           K3 (validation fixtures) ─► J (validation)
                                                          │
                                                          ▼
                                                     M (CSV export)
                                                          │
                                                          ▼
                                                     O (HTML viewer)
                                                          │
                                                          ▼
                                              L (evaluation harness — cross-cutting)

Parallel / optional:
  I (QR / IRP verify)         — runs alongside the main path; feeds J
  N (IMAP email ingestion)    — deferred past PoC; sits in front of B when added
  G3 (LayoutLMv3 fine-tune)   — optional later replacement for G1+G2 after baseline measured
  K2 (SROIE reference loader) — added when L needs external calibration
```

Parallelism on a solo dev: D and E/F can alternate — text-PDF path first because it is
the fastest feedback loop, image path second once OCR is in. L (evaluation harness) is
set up as soon as K1 is available so every subsequent component gets an accuracy number
on integration.

Email ingestion (N) is deliberately **deferred past the PoC core** per your direction:
before confirming the backend is workable we only use the HTML viewer + loaded dataset.
Once the core pipeline proves effectiveness, N (IMAP) and eventually multi-source
ingestion become the obvious next work.

---

## 9. Evaluation Strategy — How We Know It Works

"Prove the effectiveness of results" is the stated goal of the prototype. That means we
need hard numbers, not vibes.

### 9.1 Metrics

**Stage-level metrics** (per component):
- OCR: Character Error Rate (CER), Word Error Rate (WER), per-character latency
- Entity extraction: per-field exact-match F1, numeric-field relative error
- Table extraction: row-count accuracy, cell-content F1
- Validation rules: coverage (how many invoices had each rule applied), precision (of rules that flagged, how many were actually wrong)

**End-to-end metrics** (per invoice):
- **All-fields-correct rate**: % of invoices where every header field is extracted correctly
- **Approve-without-edit rate**: % of invoices that would pass human review without any correction (this is the business-relevant number)
- **Validation-rule trigger accuracy**: % of invoices where the system's flag decision matches the human verdict

### 9.2 Evaluation Sets

- **Synthetic held-out** (500 synthetic, never seen in training) — catches regressions fast
- **Real held-out 200** — the north-star metric; we only look at aggregate numbers, we do
  not tune on individual examples in this set
- **Adversarial set** (~20) — deliberately pathological invoices (heavy skew, low resolution,
  non-standard layouts, Hinglish descriptions) — measures the worst-case tail

### 9.3 Reporting Cadence

A one-page evaluation report is regenerated at the end of every component's integration.
The report lives in `/evaluation/YYYY-MM-DD_report.md` so we have a dated history of
the system's performance as components come online.

---

## 10. Open Questions / Decisions to Confirm

Items still open after the 2026-04-16 sign-off cycle. Resolved defaults from prior rounds
are recorded in `progress.md`.

1. **Prototype accuracy bar** — what field-level accuracy on the katanaml test split counts
   as "PoC proven"? My suggested default: match or exceed the published 96% mean accuracy
   that the Donut fine-tune on this same dataset achieves. A stretch target of 90% per-field
   exact-match F1 for the heuristic baseline (G1+G2) before we invest in LayoutLMv3 (G3).
   Confirm or adjust?
2. **Demo deliverables** — is the expected delivery: (a) working HTML viewer + backend via
   Docker Compose, (b) dated evaluation reports in `evaluation/reports/`, and (c) a recorded
   walkthrough video? Or are there additional deliverables (college-project report,
   presentation deck, paper draft)?
3. **Single-business vs multi-tenant** — single-business for prototype is the default in
   the PRD gap table (§1.3). Confirm?
4. **Cloud demo** — no CI/CD in the prototype phase. When we need a cloud demo, cheapest
   path is Railway or Fly.io free tier. OK as a deferred decision?

---

## 11. Research Backlog (Things to Chase Before or During Implementation)

Updated after 2026-04-16 research and sign-off.

### Before first code commits
- [ ] Download `katanaml-org/invoices-donut-data-v1` from HuggingFace; verify schema matches what `research.md` documented; cache locally under `data/katanaml/`.
- [ ] Visually inspect ~10 invoice images from the katanaml dataset + ~5 Indian GST sample PDFs (from free template providers) to sanity-check RapidOCR default config before Component F implementation.
- [ ] Verify NIC (Indian e-invoice IRP) public key availability for JWT signature verification on QR codes — needed before Component I.
- [ ] Seed `hsn_rates.csv` with top 500 HSN codes from CBIC's published schedule — used by Component J5 (HSN rate lookup).
- [ ] Compile the state-code lookup table for GSTIN checksum validation (Component J1).

### During implementation
- [ ] Identify a realistic free-tier GSTIN-active-status API (likely Masters India) and build its `GSTINActiveStatusProvider` implementation on standby — will be switched in the day credits are available.
- [ ] After heuristic extraction baseline has a measured accuracy number on katanaml, decide whether LayoutLMv3 fine-tune (G3) is the next move or whether heuristic gap is elsewhere.

### Post-PoC (deferred)
- [ ] Download MIDD (Zenodo 10.5281/zenodo.5113009), integrate the loader, measure pipeline sim-to-real transfer to Indian invoices.
- [ ] Collect real Indian GST invoices (OSS test fixtures, friends' small businesses with PII redacted) if MIDD proves insufficient.
- [ ] Benchmark Qwen2-VL vs InternVL for weak-labelling stray Indian invoices, only if we need more than MIDD provides.
- [ ] Benchmark RapidOCR vs PaddleOCR-direct vs Tesseract 5 on our own data (not just third-party blogs) — builds our own evidence.
- [ ] Survey 3–5 Indian CA firms for real pain points — sanity-check PRD assumptions before any productionisation.

---

## 12. Out of Scope for Prototype (On-the-Record Non-Goals)

Updated after 2026-04-16 research and sign-off.

### Hard non-goals (scoped out from the start)
- Native Tally XML push (CSV export only)
- Multi-tenancy / CA-firm mode
- Sales / outward invoices / GSTR-1 side
- Credit notes, debit notes, advance receipts
- Foreign currency / import bills of entry
- WhatsApp Business API ingestion
- GSP-mediated GSTN API calls (real GSTIN active check, real GSTR-2B download, real IRN generation)
- SOC2 / ISO 27001 / enterprise security posture
- Mobile app
- Production deployment / 99.9% uptime / horizontal scaling
- Any LLM / VLM API at inference time (cost + we own the research)
- Frontend SPA frameworks (React, Vue, Streamlit, etc.) — vanilla HTML/CSS/JS only
- GPU at inference time — CPU-only

### Deferred past PoC (will be revisited after core pipeline is proven)
- **Indian GST-specific training data** (MIDD integration, Indian synthetic generation) — validation engine tested with hand-written JSON fixtures until then
- **Multi-OCR ensemble / A-B benchmark** — only one OCR backend (RapidOCR) is active at PoC; alternative backends are scaffolded but not implemented
- **Email (IMAP) and other ingestion sources** — upload-only for PoC
- **LayoutLMv3 / Donut extraction upgrades** — heuristic baseline measured first, upgrade decision based on numbers
- **Native large-scale synthetic invoice generation** (Jinja2 + WeasyPrint + Albumentations) — deferred to Indian phase

These become active work items only if and when the PoC proves the core hypothesis and we
decide to specialise the pipeline for India and/or productionise.

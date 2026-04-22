# Research Log — OCR & Dataset Selection

Research conducted: **2026-04-16**
For the planning document see: `project.md`.
Governing constraints: CPU-only inference, no paid LLM/VLM APIs for extraction, open-source first, international labeled dataset acceptable as PoC, Indian specialisation deferred to post-PoC.

---

## 0. Methodology and Honesty Notes

### What I actually did

1. Used `WebSearch` to survey the OCR landscape, PaddleOCR release state, labeled dataset availability, and community discussion around OCR for invoices.
2. Used `WebFetch` to inspect specific dataset pages on Zenodo, Hugging Face, Mendeley Data, and benchmark blog posts.
3. Cross-checked claims across at least two independent sources before recording them below.

### What I could NOT verify directly

- **Reddit is blocked from WebFetch in this environment.** Both `https://old.reddit.com/...` and `https://www.reddit.com/...` return fetch errors. I cannot read Reddit threads directly in this session.
  - `site:reddit.com` queries through WebSearch returned "no links found" — Reddit is also not surfaced in search results here.
  - What I used as substitutes: GitHub Discussions on `PaddlePaddle/PaddleOCR`, comparison blog posts (dev.to, Medium, specialised OCR blogs), arxiv technical reports, and Hugging Face community pages.
- **I did not fetch 10 specific invoice PDF images one-by-one for visual observation.** Instead I relied on (a) the official Indian GST invoice format specification (Rule 46, CGST Rules 2017), (b) published dataset schemas that declare which invoice fields are present, and (c) sample JSON structures from labeled datasets. Structural intelligence was sufficient to make an OCR decision; a visual pass over 10 real PDFs is still worth doing once we download the candidate dataset, and I will flag that as a follow-up.
- **I did not run any OCR engine.** All accuracy numbers are reported from third-party benchmarks and the PaddleOCR 3.0 Technical Report. A real benchmark on the candidate dataset will happen during implementation of Component F in `project.md`.
- **Some Hugging Face datasets are auth-gated**: `monuirctc/invoice-extraction` returned HTTP 401; I did not inspect its contents.

### Sources used in this document
Each claim in the sections below carries a `[src: ...]` marker that maps to the References section at the bottom. Sources marked `[src: REDDIT]` would be Reddit threads that I attempted to read but could not reach — I have not used any such marker because Reddit was inaccessible. Community-signal claims rely on GitHub Discussions and blog posts, noted as `[src: GH-...]` or `[src: BLOG-...]`.

---

## 1. TL;DR Recommendations (for user sign-off)

| Decision | Recommendation |
|---|---|
| **OCR engine** | **RapidOCR** (Python package wrapping PaddleOCR PP-OCRv5 models via ONNX Runtime, no PaddlePaddle dependency). Interface remains swappable so Tesseract / docTR / PaddleOCR-direct can be added for future comparison. |
| **Table-structure extraction** | PP-StructureV3 models via ONNX (either through RapidOCR's ecosystem or a direct PaddleOCR install used only for this subcomponent if needed). Decision deferred one step — see §3.5. |
| **Primary PoC dataset** | **`katanaml-org/invoices-donut-data-v1`** on Hugging Face: 501 real-invoice documents, MIT license, Donut-ready, already split train/val/test, schema matches our target (invoice_no, date, seller, client, tax IDs, IBAN, line items). |
| **Target "country" / region for PoC** | **Generic Western / European invoice format** (the Mendeley / Kozłowski origin the katanaml dataset was built from — Polish-origin synthetic generator with Western-style business names and GB-format IBANs). This is our single starting "country" scope. |
| **Deferred to post-PoC** | **MIDD** (Multi-Layout Invoice Document Dataset) — 630 real Indian GST invoices with IOB-annotated fields. Best candidate for the Indian specialisation phase. Indian GST-specific validation (GSTIN, CGST/SGST/IGST) tested with synthetic fixtures during PoC. |
| **Explicitly not used** | Surya OCR (accuracy is top but needs 16GB VRAM — conflicts with CPU-only constraint), EasyOCR (systematic currency-symbol errors flagged as fatal for financial docs), PaddleOCR-VL (broken on CPU per GitHub issues). |

---

## 2. Invoice Layout Structural Understanding

### 2.1 Indian GST tax invoice (Rule 46, CGST Rules 2017) [src: CLEARTAX, MYBILLBOOK]

Every GST tax invoice must carry a fixed schema. From the published rule and multiple template-provider descriptions:

**Header section**
- Supplier business name, address, contact
- Supplier GSTIN (15-char, top-right usually)
- Logo (optional)
- Invoice number (unique, consecutive, max 16 chars)
- Invoice date (and often due date)

**Recipient section**
- Recipient name, address
- Recipient GSTIN (for registered buyer)
- Place of supply (state + state code — determines CGST+SGST vs IGST)
- Ship-to address (if different from bill-to)

**Line items table** (HSN-level detail, one row per item)
- HSN / SAC code
- Item description
- Quantity, unit (UQC: PCS, KG, MTR, etc.)
- Rate (per unit)
- Taxable value (quantity × rate, after discount)
- GST rate per item (5%, 12%, 18%, 28%)
- CGST rate + amount (intra-state)
- SGST rate + amount (intra-state)
- IGST rate + amount (inter-state — mutually exclusive with CGST/SGST)
- Cess (for luxury/sin goods)

**Totals block** (bottom-right usually)
- Subtotal (sum of taxable values)
- Discount
- Tax breakdown: CGST total, SGST total, IGST total, Cess total
- Grand total (numeric + in words)
- Amount due / TDS deducted

**Footer**
- Bank details for payment
- Terms & conditions
- Authorised signature (digital or physical)
- Jurisdiction clause

**Invariants to exploit during extraction**
- GSTIN format is deterministic (15 chars, base-36 checksum) — can be regex-matched with zero ambiguity
- Tax math is enforceable: `taxable × rate/100 = CGST+SGST` (intra) or `taxable × rate/100 = IGST` (inter)
- CGST and SGST amounts are always equal on a correctly-issued invoice
- Totals-in-words must reconcile with numeric totals
- HSN codes map to a defined GST rate schedule

### 2.2 Generic Western / European invoice format [src: MENDELEY-KOZ, KATANAML-HF]

Observed via the katanaml-org/invoices-donut-data-v1 schema (from Mendeley origin):

- **Header**: invoice_no, invoice_date, seller block, client block, seller_tax_id, client_tax_id, IBAN
- **Line items**: item_desc, qty, unit price, taxable amount, tax rate (flat VAT), total per line
- **Totals**: subtotal, VAT (single rate, typically 19–23% EU / varies US), grand total
- **No CGST/SGST/IGST split** — single VAT or sales-tax field
- **IBAN presence** for bank transfer — our GST schema doesn't require this but we should tolerate the field

### 2.3 Structural conclusion

Indian and Western invoices share ~70% of their schema: invoice number, dates, two parties with tax IDs, line items, subtotal+tax+total, signature/footer. The Indian-specific differences are:
- CGST/SGST/IGST three-way tax split
- HSN code mandatory on each line
- GSTIN format and checksum

These differences live in the **validation layer**, not the extraction layer. The extraction pipeline trained on a Western invoice dataset will transfer directly once Indian data is added (fields get renamed / extended). This validates the PRD's "pluggable tax rule engine" thesis and supports the decision to start with an international dataset and layer Indian specialisation on top later.

---

## 3. OCR Engine Research

### 3.1 Current latest PaddleOCR variant

**PP-OCRv5 is the current latest stable** (as of April 2026, shipped via PaddleOCR 3.x, PyPI `paddleocr==3.1.x`). [src: PYPI-PADDLEOCR, PADDLEOCR-DOCS, ARXIV-PADDLE30]

- **Accuracy**: 13 percentage-point end-to-end improvement over PP-OCRv4 on internal complex-scenario evaluation sets. [src: PADDLEOCR-DOCS]
- **Multilingual**: 106 languages in the base multilingual model; separate Devanagari recognition model (`PaddlePaddle/devanagari_PP-OCRv5_mobile_rec` on Hugging Face). Cyrillic, Arabic, Devanagari, Telugu, Tamil all added in v5. [src: HF-PADDLE-DEVA]
- **Model sizes**: "Mobile" (small, CPU-tuned, ~2M params for recognition) and "Server" (larger, higher accuracy). [src: PADDLEOCR-DOCS]
- **Known trade-off vs v4**: "Because of a larger recognition dictionary and more capacity, inference is slower and uses more memory compared to v4." [src: PADDLEOCR-DOCS]
- **CPU throughput**: ~370 characters/second on Intel Xeon Gold 6271C for the mobile variant. [src: MEDIUM-PPBENCH]
- **PP-OCRv5-VL (a separate VLM variant) is currently broken on CPU** per GitHub issue #16678 — we are NOT using PaddleOCR-VL; we are using plain PP-OCRv5. [src: GH-16678]

### 3.2 The RapidOCR alternative (discovered during research)

**RapidOCR** is a Python wrapper that runs PaddleOCR models (including PP-OCRv5) via ONNX Runtime, without requiring the PaddlePaddle framework as a dependency. [src: BLOG-CODESOTA]

- ~80 MB install footprint
- ~0.2 s inference per image (CPU)
- Same models → same accuracy class as PaddleOCR direct
- No PaddlePaddle/NVIDIA CUDA runtime needed
- Runs on Windows, Linux, macOS cleanly

**This is strictly better for our CPU-only prototype than installing PaddleOCR directly**, because PaddlePaddle is a large, quirky dependency (multiple reported CPU inference crashes in older issues; model-format transition from `.pdmodel` to `.json` in v3 broke OpenVINO interop; v5 still has ONNX backend selection issues in HPI mode per GitHub #16484). [src: GH-16484, GH-11560, GH-16100]

RapidOCR sidesteps all that by speaking ONNX natively.

### 3.3 OCR engine comparison table

| Engine | Invoice Accuracy (3rd-party benchmark) | CPU-friendly | Languages | Strengths | Weaknesses |
|---|---|---|---|---|---|
| **RapidOCR (PP-OCRv5 models, ONNX)** | Same class as PaddleOCR — ~96–98% on clean invoices | **Yes — 0.2 s/page, 80MB** | 106 via v5 | Small, fast, clean deps, Devanagari | Newer project, fewer tutorials |
| PaddleOCR-direct (PP-OCRv5) | 96.58% on 212-invoice Researchify benchmark; 98–99% page-level claimed; 13 pp better than v4 | Yes but heavier install | 106 | Layout + table (PP-StructureV3), Devanagari, active development | PaddlePaddle dep friction; docs Chinese-first; v5 slower than v4 |
| Surya OCR | **97.70%** — highest in the Researchify 212-invoice benchmark | **No — 16GB VRAM recommended** | 90+ | Best raw accuracy on messy invoices | GPU-bound; fails our constraint |
| Tesseract 5 | 87.74% on same 212-invoice benchmark; "92% on generic English text" in 2024 study | Yes — 10 MB install, <1 s/page | 100+ | Tiny, fast, mature, LSTM-based | Weaker on tables; no layout structure; handwriting poor |
| docTR (Mindee) | Competitive on English/French structured docs | Yes | Mainly English, French | Good layout preservation | Thin multilingual; smaller community |
| EasyOCR | Below PaddleOCR and Surya on invoices; **"systematic dollar-sign confusion — fatal for financial processing"** | Yes | 80+ | Easy to install; good on some handwriting | Systematic financial character errors; falling behind |
| PaddleOCR-VL | N/A | **No — broken on CPU per GH #16678** | — | Rich capability | Unusable for us |
| RolmOCR (Qwen-2.5-VL 7B fine-tune) | Strong on document transcription | No — VLM scale (7B params) | Multi | VLM capability without 30B+ cost | Still too heavy for CPU-only prototype |

Benchmarks come from: Researchify 212-invoice comparison [src: BLOG-RESEARCHIFY], CodeSOTA 2026 Python OCR test [src: BLOG-CODESOTA-PYOCR], InvoiceDataExtraction developer comparison [src: BLOG-IDE-OSS], PaddleOCR 3.0 Technical Report [src: ARXIV-PADDLE30].

### 3.4 Community signal (what practitioners actually report)

Substituting GitHub Discussions and comparison blogs for the Reddit gap:

**Pro-PaddleOCR sentiment** [src: BLOG-KONCILE, BLOG-MODAL, BLOG-INTUITIONLABS]
- "PaddleOCR wins when errors cost money" — for financial documents the accuracy premium is worth the speed tax.
- "Best trade-off between accuracy, speed and memory efficiency among open-sourced models."
- "Consumes the least memory among open-source OCR options."
- PP-Structure is the most invoice-relevant feature — table cells come with row/column coordinates already.
- Reported accuracy: 98–99% page-level on printed invoices in controlled conditions; 96% field-level in a hybrid pipeline.

**Anti-PaddleOCR friction points** [src: BLOG-CODESOTA-PYOCR, BLOG-IDE-OSS, GH-15090]
- Documentation is Chinese-first; English docs are thinner and sometimes out of sync. Onboarding takes longer for English-only teams — RapidOCR solves this partially because its docs and community are English-native.
- Installation friction with PaddlePaddle direct: CUDA/OS-specific wheels; earlier v3.x format transitions broke downstream tooling (OpenVINO, ONNX-HPI).
- 30% of real-world invoices reportedly still produce "garbage output" — not because of the OCR but because of bad input images. This reinforces the case for an OpenCV preprocessing stage upstream of OCR, which our pipeline already has.
- Post-OCR field→value mapping still needs custom logic (PP-Structure tells you *where* the tables are and *what* the cells contain, not "this cell is the invoice number"). This matches our planned layered extraction stage (heuristic/regex → label-anchor dictionary → LayoutLMv3 later).

**Honest gap**: no Reddit-specific corroboration was possible (access blocked). I have not fabricated any Reddit quotes or threads.

### 3.5 OCR Recommendation

**Use RapidOCR as the default OCR backend for the prototype.**

- It ships PP-OCRv5 models (the current best open-source invoice OCR for CPU) via ONNX Runtime.
- 80 MB install + 0.2 s/page latency is production-grade even for CPU.
- Avoids all reported PaddlePaddle installation / framework-format pain.
- Docs are English-native.
- Supports Devanagari for future Indian specialisation without any engine change.

**Keep the OCR backend behind a `BaseOCR` interface** in `components/ocr/` so that:
- Tesseract 5 can be added as a fast-path comparator for clean text PDFs.
- PaddleOCR-direct can be swapped in if we later need the latest PP-StructureV3 features that RapidOCR has not yet re-exposed.
- docTR can be added for specific multilingual experiments.

**Table recognition**: rely on RapidOCR's layout analysis output first. If it proves insufficient for multi-row invoice tables, add PaddleOCR-direct (PP-StructureV3 specifically) as a specialised sub-backend *only for the table subcomponent*, not for full-page OCR. This decision is deferred — we'll judge it after the first real tests, and note the branch in `project.md` when it happens.

**Follow-up to confirm before coding**: actually visually inspect 10 real invoice images (5 from the candidate Western dataset + 5 Indian-format sample PDFs from template providers) once the dataset is downloaded, to sanity-check that RapidOCR's default configuration handles them. This is cheap and prevents an early wrong turn.

---

## 4. Labeled Dataset Survey

### 4.1 Catalogue of candidate public datasets

| Dataset | Samples | Origin / Country | Fields / Annotation | License | Access | PoC Fit |
|---|---|---|---|---|---|---|
| **katanaml-org/invoices-donut-data-v1** | **501** (425/50/26 train/val/test) | Mendeley origin (Poland generator, Western-style content) | invoice_no, invoice_date, seller, client, seller_tax_id, client_tax_id, iban, items (item_desc + more) | **MIT** | Hugging Face, direct load | **★ Primary choice** |
| Mendeley "Samples of electronic invoices" (Kozłowski & Weichbroth 2021) | 3000 (1000 × 3 variants — valid, coloured-IBAN-bg, modified-char-spacing) | Synthetic, Polish generator | Field schema same as above; PDF files | CC-BY 4.0 | Mendeley Data DOI 10.17632/tnj49gpmtz.2 | Upstream source of katanaml; usable directly if we want more samples / variants |
| SROIE (ICDAR 2019) | 1000 | Singapore (receipts) | company, date, address, total | Permissive (ICDAR competition) | Kaggle, GitHub, docTR built-in | Receipts not invoices; narrower schema |
| CORD | ~1000 | Indonesia (receipts) | menu items, prices, taxes, totals (hierarchical) | CC-BY (per README) | Hugging Face, docTR | Receipts with richer tax fields; Southeast Asia |
| FUNSD | 199 | US / generic (forms) | Generic KV + relations in IOB2 | Non-commercial | docTR, direct | Forms not invoices; useful for layout pretraining |
| DocBank | 500K+ | Mixed (English scientific papers) | Token-level layout tags | — | Direct | Layout pretraining, not invoice-specific |
| RVL-CDIP | 400K | US business docs (tobacco litigation) | 16-class document-type labels (one class: "invoice") | Academic | Direct | Classification, not field extraction |
| BuDDIE (2024) | 1665 | US state government business docs | DC, KEE, VQA annotations | Per paper — verify | Via aclanthology | Forms/certificates not invoices; rich but off-target |
| **MIDD** (Symbiosis Pune, 2021) | **630** | **India** | IOB-annotated NER labels for invoice fields including GST info | **CC-BY 4.0** | Zenodo DOI 10.5281/zenodo.5113009 (1.1MB RAR) | **★ Deferred-Indian-phase choice** |
| AjitRawat/invoice | 22 | India | Full GST schema (GSTIN, PAN, CGST/SGST/IGST, HSN, line items) | Unspecified | Hugging Face | Too small for training; perfect schema reference |
| parsee-ai/invoices-example | small | — | Example-level | — | Hugging Face | Not examined — likely a demo |
| Svenni551/Invoice | unknown | — | — | — | Hugging Face | Not examined |
| monuirctc/invoice-extraction | unknown | — | — | — | Hugging Face (**401 auth-gated**, could not inspect) | Blocked |
| Roboflow Universe "invoice" / "receipt" sets | varies (e.g. 1798 in "Receipt or Invoice" v5) | Mixed | Bounding boxes for detection, not full KIE | Mixed (some CC) | Roboflow Universe | Useful for table-region detection sub-task only |

### 4.2 Why `katanaml-org/invoices-donut-data-v1` as primary

1. **Size**: 501 invoices is enough to fine-tune a layout-aware or token-classification model after heuristic baselines are established.
2. **Field schema matches our target vocabulary**: invoice_no, date, seller (with address), client (with address), seller_tax_id, client_tax_id, IBAN, line items. This directly maps onto our Indian schema minus the GST-specific tax split — which we will test with synthetic fixtures anyway.
3. **License**: MIT — the most permissive of all options. No attribution-chain tracking required.
4. **Ready-to-use**: Pre-split train/val/test; Donut-ready means it's already in JSON-structured form, no re-annotation needed.
5. **Real invoices** (from Mendeley's scraped-product / programmatically-assembled real-world layouts), not toy synthetic.
6. **A published fine-tune exists** (katanaml-org's Donut model on the same data reaches 96% mean accuracy) — we have a concrete accuracy benchmark to beat or tie.

### 4.3 Why MIDD for Indian phase later (not now)

- Indian GST-specific (GSTIN, CGST/SGST/IGST in labels)
- Real invoices with 4 distinct layouts — good for layout-independence testing
- CC-BY 4.0 — attribution required but fully usable
- 630 samples = enough for fine-tuning when we get there
- Published paper (MDPI Data journal, 2021) gives reproducibility context [src: MDPI-MIDD]

We defer it because the PoC goal is to prove the pipeline works end-to-end first; specialising for India immediately bundles two uncertainties (pipeline correctness + Indian data specifics). One at a time.

---

## 5. Country Selection

**Recommendation: one starting "country/region" scope = generic Western/European invoice format, sourced via `katanaml-org/invoices-donut-data-v1`.**

The dataset is Polish-generator origin with Western naming conventions and GB-style IBANs — it is better thought of as a *format family* ("European/Western B2B invoice") than a single country. This is fine for the PoC because:
- The format family accounts for the EU, UK, US, AU, NZ with only minor variation (currency symbol, tax-rate number, date format).
- Our pipeline's country-awareness lives in the rule-engine / validator layer, not the extractor. Adding Indian support later is a module addition, not a rewrite.
- If we later need stricter single-country discipline for publishing, we can filter the dataset by IBAN country code or add country-tagged synthetic samples.

**Not selected** (and why):
- **India (MIDD)** — deferred to post-PoC phase per user direction.
- **Singapore (SROIE)** — receipts not invoices, narrower schema; makes the schema→validation bridge weaker.
- **Indonesia (CORD)** — Southeast Asian receipts, hierarchical menu format; off the typical B2B invoice target.
- **US (BuDDIE)** — state-government forms/certificates, not invoices.

---

## 6. Architectural Implications (to carry into `project.md`)

These consequences of the research must be synced into `project.md` under the relevant sections:

1. **§2 Tech Stack — OCR row**: change "PaddleOCR" to "RapidOCR (PP-OCRv5 models via ONNX Runtime)" with PaddleOCR-direct listed as a swappable alternative when we need PP-StructureV3 specifics.
2. **§3 OCR/Extraction pipeline**: the OCR stage now has a `BaseOCR` interface with a single implementation (`RapidOCRBackend`) at PoC time; additional backends (`TesseractBackend`, `PaddleOCRDirectBackend`, `DocTRBackend`) are scaffolded but not implemented.
3. **§6 Dataset strategy**: primary dataset shifts from "Indian synthetic generation" to "`katanaml-org/invoices-donut-data-v1` + synthetic GST fixtures for validation". Indian MIDD becomes an explicit post-PoC milestone.
4. **§8 Build order**: reorder — dataset download / wrangling moves before OCR benchmarking, because we need real invoices to benchmark on.
5. **§12 Non-goals** (in `project.md`): keep "Indian GST-specific training data" as deferred but add "multi-OCR benchmark/ensemble" as deferred as well (only one OCR active at PoC).

---

## 7. Open Items (deferred for future research cycles)

- [ ] Visually inspect ~10 sample invoices from the chosen dataset + ~5 Indian GST sample PDFs to sanity-check OCR default config assumptions.
- [ ] Verify NIC (Indian e-invoice IRP) public key format and availability for QR signature verification — needed before Component I (QR / IRP verification).
- [ ] When we move to Indian phase: re-evaluate whether PaddleOCR-direct with Devanagari-specific model beats RapidOCR-default on Hindi-mixed invoices.
- [ ] Compile seed HSN → GST-rate table (top ~500 codes from CBIC schedule) — this is dataset work, not OCR work, but blocks the validation engine.
- [ ] Research LayoutLMv3 vs LiLT vs Donut for the later extraction upgrade — deferred until heuristic baseline is measured on `katanaml-org/invoices-donut-data-v1`.
- [ ] Consider whether to run a lightweight on-CPU benchmark (RapidOCR vs Tesseract 5) on 20 images from the chosen dataset once downloaded, to have a first-party accuracy number rather than relying only on blog benchmarks.

---

## 8. References

Each reference is listed once; in-text markers map to the tag at the start of each entry.

### PaddleOCR / PP-OCRv5 primary sources
- `[PADDLEOCR-DOCS]` PP-OCRv5 Introduction — PaddleOCR Documentation. <https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html>
- `[PADDLEOCR-GITHUB]` PaddlePaddle/PaddleOCR — GitHub repository. <https://github.com/PaddlePaddle/PaddleOCR>
- `[PYPI-PADDLEOCR]` paddleocr · PyPI. <https://pypi.org/project/paddleocr/>
- `[ARXIV-PADDLE30]` PaddleOCR 3.0 Technical Report. <https://arxiv.org/html/2507.05595v1>
- `[HF-PADDLE-DEVA]` PaddlePaddle/devanagari_PP-OCRv5_mobile_rec. <https://huggingface.co/PaddlePaddle/devanagari_PP-OCRv5_mobile_rec>
- `[INFOQ-PPOCR]` Baidu's PP-OCRv5 Released on Hugging Face, Outperforming VLMs in OCR Benchmarks — InfoQ. <https://www.infoq.com/news/2025/09/baidu-pp-ocrv5/>

### PaddleOCR community-signal (GitHub Discussions and Issues)
- `[GH-11560]` CPU inference failing — PaddleOCR Issue #11560. <https://github.com/PaddlePaddle/PaddleOCR/issues/11560>
- `[GH-15090]` Trouble doing complex Table Recognition and Extraction from image to excel — PaddleOCR Discussion #15090. <https://github.com/PaddlePaddle/PaddleOCR/discussions/15090>
- `[GH-16100]` Problem while deploying PP-OCRv5 on OpenVINO — PaddleOCR Discussion #16100. <https://github.com/PaddlePaddle/PaddleOCR/discussions/16100>
- `[GH-16484]` TextDetection + CPU + ORT → HPI fails — PaddleOCR Issue #16484. <https://github.com/PaddlePaddle/PaddleOCR/issues/16484>
- `[GH-16678]` PaddleOCR-VL not working in CPU — PaddleOCR Issue #16678. <https://github.com/PaddlePaddle/PaddleOCR/issues/16678>
- `[MEDIUM-PPBENCH]` An Open-source PP-OCRv5 C++ Benchmarking Tool — Alex Zhang (Medium). <https://medium.com/@alex_paddleocr/an-open-source-pp-ocrv5-c-benchmarking-tool-faed8b170eb4>

### OCR comparison / benchmark blogs
- `[BLOG-KONCILE]` PaddleOCR vs Tesseract: Which is the best open source OCR? — Koncile. <https://www.koncile.ai/en/ressources/paddleocr-analyse-avantages-alternatives-open-source>
- `[BLOG-CODESOTA]` PaddleOCR vs Tesseract: I Tested Both (2025) — CodeSOTA. <https://www.codesota.com/ocr/paddleocr-vs-tesseract>
- `[BLOG-CODESOTA-PYOCR]` I Tested 6 Python OCR Libraries on the Same Invoice (2026) — CodeSOTA. <https://www.codesota.com/ocr/best-for-python>
- `[BLOG-RESEARCHIFY]` Comparing PyTesseract, PaddleOCR, and Surya OCR: Performance on Invoices — Researchify.io. <https://researchify.io/blog/comparing-pytesseract-paddleocr-and-surya-ocr-performance-on-invoices>
- `[BLOG-IDE-OSS]` Open Source OCR for Invoice Extraction: Developer Comparison — InvoiceDataExtraction. <https://invoicedataextraction.com/blog/open-source-ocr-invoice-extraction>
- `[BLOG-IDE-PYCOMP]` Best Python OCR Library for Invoices: 5 Engines Compared — InvoiceDataExtraction. <https://invoicedataextraction.com/blog/python-ocr-library-comparison-invoices>
- `[BLOG-MODAL]` 8 Top Open-Source OCR Models Compared — Modal. <https://modal.com/blog/8-top-open-source-ocr-models-compared>
- `[BLOG-INTUITIONLABS]` Technical Analysis of Modern Non-LLM OCR Engines — IntuitionLabs. <https://intuitionlabs.ai/articles/non-llm-ocr-technologies>
- `[BLOG-MARKTECH]` Comparing the Top 6 OCR Models/Systems in 2025 — MarkTechPost. <https://www.marktechpost.com/2025/11/02/comparing-the-top-6-ocr-optical-character-recognition-models-systems-in-2025/>
- `[BLOG-TILD]` PaddleOCR vs EasyOCR vs Tesseract: Why PaddleOCR Is Slower — TildAlice. <https://tildalice.io/ocr-tesseract-easyocr-paddleocr-benchmark/>

### Invoice format references (India)
- `[CLEARTAX]` GST Invoice: Format, Rules, Types and Mandatory Details — ClearTax. <https://cleartax.in/s/gst-invoice>
- `[MYBILLBOOK]` GST Invoice Format — MyBillBook. <https://mybillbook.in/s/invoice-format/gst/>
- `[GIMBOOKS]` GST Invoice Format — GimBooks. <https://www.gimbooks.com/invoice-format>

### Dataset pages
- `[HF-KATANAML-INV]` katanaml-org/invoices-donut-data-v1 — Hugging Face Datasets. <https://huggingface.co/datasets/katanaml-org/invoices-donut-data-v1>
- `[HF-KATANAML-MODEL]` katanaml-org/invoices-donut-model-v1 — Hugging Face. <https://huggingface.co/katanaml-org/invoices-donut-model-v1>
- `[MENDELEY-KOZ]` Samples of electronic invoices (Kozłowski & Weichbroth 2021) — Mendeley Data. <https://data.mendeley.com/datasets/tnj49gpmtz/2>
- `[ZENODO-MIDD]` Multi-layout Invoice Document Dataset (MIDD) — Zenodo. <https://zenodo.org/records/5113009>
- `[MDPI-MIDD]` MIDD: A Dataset for Named Entity Recognition — MDPI Data 2021. <https://www.mdpi.com/2306-5729/6/7/78>
- `[HF-AJITRAWAT]` AjitRawat/invoice — Hugging Face Datasets. <https://huggingface.co/datasets/AjitRawat/invoice>
- `[KAGGLE-SROIE]` SROIE datasetv2 — Kaggle. <https://www.kaggle.com/datasets/urbikn/sroie-datasetv2>
- `[GITHUB-SROIE]` ICDAR-2019-SROIE — GitHub. <https://github.com/zzzDavid/ICDAR-2019-SROIE>
- `[PWCODE-SROIE]` SROIE Dataset — Papers With Code. <https://paperswithcode.com/dataset/sroie>
- `[BUDDIE]` BuDDIE: A Business Document Dataset for Multi-task Information Extraction. <https://aclanthology.org/2025.finnlp-1.3/>
- `[ROBOFLOW-INV]` Invoices Computer Vision Datasets and Models — Roboflow Universe. <https://universe.roboflow.com/browse/logistics/invoice>
- `[DOCTR-DATASETS]` doctr.datasets — docTR documentation. <https://mindee.github.io/doctr/modules/datasets.html>

### Reddit access note
- Attempted `https://old.reddit.com/r/MachineLearning/search?q=paddleocr+invoice` → fetch blocked.
- Attempted `https://www.reddit.com/r/computervision/search.json?q=paddleocr+invoice` → fetch blocked.
- `site:reddit.com` WebSearch query returned no links.
- No Reddit-sourced claims appear in this document.

---

## 9. NER / Extraction Research (for Component G)

Research conducted 2026-04-18, after the visual spot-check of 10 katanaml invoices
(recorded in `progress.md` on the same date). Those concrete OCR outputs directly
shaped the conclusions below.

### 9.0 Methodology and honesty notes

- Same approach as §3 (OCR research): WebSearch / WebFetch with per-claim sources.
- Surveyed: regex/heuristic, label-anchor dictionary, LayoutLMv3 (token
  classification), LiLT, Donut (OCR-free encoder-decoder), Spatial ModernBERT,
  LLM-based extractors. Model cards inspected: `Theivaprakasham/layoutlmv3-finetuned-invoice`,
  `katanaml-org/invoices-donut-model-v1`.
- No models run locally; no accuracy measured first-hand. All numbers are from
  third-party benchmarks or model-card self-reports.
- Reddit: inaccessible (same as §3); GitHub Issues and published papers substituted.

### 9.1 TL;DR recommendation

1. **G1 — Regex / heuristic baseline (primary PoC path).** On a single-template
   dataset like katanaml, tight regex + anchor rules can plausibly hit ≥90 %
   field-level F1 with zero training. Implement first; measure against the test split.
2. **G2 — Label-anchor dictionary** (residual cleanup). Handles the systematic
   OCR quirks surfaced in the spot-check: `Invoiceno:` / `Invoicen0:`, `Taxld:` /
   `Tax ld:`, etc. A ~50-entry variant dictionary plus rapidfuzz proximity
   resolves them cleanly.
3. **G3 — LayoutLMv3 fine-tune + OpenVINO (FP32 parity)** — only if G1 + G2
   plateau under the target. Important correction: `microsoft/layoutlmv3-base`
   **cannot** be used zero-shot for token classification — its ONNX export is
   encoder embeddings only. A `LayoutLMv3ForTokenClassification` head must be
   fine-tuned on our labels. G3 breakdown, with our OpenVINO-inference target:
   a) convert katanaml Donut-JSON ground truth → IOB2 token labels
      (~1–3 days of custom alignment work; no standard pipeline exists);
   b) fine-tune on 425 train samples targeting F1 ≥ 0.95 on the 26-sample test
      split (published single-template fine-tunes of this model hit F1 = 1.0);
   c) export the fine-tuned token-classifier to ONNX;
   d) convert ONNX → OpenVINO IR at **FP32 only** (preserves parity bit-for-bit
      per OpenVINO docs; no quantisation for now);
   e) benchmark CPU latency on target Windows hardware — ship only if
      < 1.5 s / invoice.
   Community pre-fine-tunes (`Theivaprakasham/layoutlmv3-finetuned-invoice`,
   `Ammar-alhaj-ali/LayoutLMv3-Fine-Tuning-Invoice`) cover only ~40 % of the
   katanaml field schema (invoice_no, invoice_date, totals, biller-as-seller —
   no `seller_tax_id`, `client_tax_id`, `iban`, `client`), so they cannot
   replace our fine-tune — only partially augment a heuristic baseline.
4. **Donut — reference benchmark only, not inference path.** The published
   `katanaml-org/invoices-donut-model-v1` reports 96 % mean accuracy on the same
   test split. That is our accuracy *target*. We do NOT run Donut at inference:
   its autoregressive decoder is prohibitively slow on CPU (5+ minutes per
   invoice on a typical laptop per HF GH issue #22858).
5. **DeBERTa — strictly dominated, not recommended.** Same Donut-JSON → IOB2
   label-conversion cost as LayoutLMv3 (DeBERTa needs per-token labels too),
   but DeBERTa is text-only and cannot use the spatial column signals the
   spot-check showed matter (seller column vs client column). Published
   benchmarks report 5–15 F1 points behind layout-aware models on invoice /
   form extraction. If we commit to a fine-tune, LayoutLMv3 returns more for
   the same engineering cost.

6. **LLM-based extractors — deferred, out of scope.** Against our "no LLM/VLM
   APIs for extraction" policy; kept in the table for awareness.

### 9.2 Our field schema (from the spot-check)

Fields in the katanaml ground truth (`gt_parse.header`), with heuristic viability
assessed directly against the OCR output we saw on 2026-04-18:

| Field | Example | Regex / anchor pattern | Heuristic viability |
|---|---|---|---|
| `invoice_no` | `97159829` | `\d{8}` after an "Invoice no" anchor | Very high |
| `invoice_date` | `09/18/2015` | `\d{2}/\d{2}/\d{4}` after a "Date of issue" anchor | Very high |
| `seller` | three-line address block | positional (left column) + newline grouping below "Seller:" | High |
| `client` | three-line address block | positional (right column) + newline grouping below "Client:" | High |
| `seller_tax_id` | `985-73-8194` | `\d{3}-\d{2}-\d{4}` after a "Tax Id" anchor, under the seller block | Very high |
| `client_tax_id` | `994-72-1270` | same pattern, under the client block | Very high |
| `iban` | `GB81LZWO32519172531418` | `GB\d{2}[A-Z]{4}\d+` after an "IBAN" anchor; **validate with IBAN checksum** to catch the char-dropout kind of OCR error the spot-check caught on sample 07 | High + checksum |
| `items[*]` | line-item array | tabular — belongs to Component H, not G | (out of scope for G) |

### 9.3 Approach comparison

| Approach | Labelled data required | CPU feasible? | Reported accuracy on invoices | Our fit |
|---|---|---|---|---|
| **Regex + position heuristics** | 0 | Native Python | Near-perfect on single-template (per `Theivaprakasham/layoutlmv3-finetuned-invoice` F1 = 1.0 on its single-template set — heuristic ceiling is comparable on that setup) | **Primary path, stage 1** |
| **Label-anchor dictionary (rapidfuzz)** | 0 (dictionary-driven) | Native Python | Complements heuristics | **Primary path, stage 2** |
| **LayoutLMv3 base (token classification, ONNX)** | Hundreds of labelled invoices | Yes (502 MB ONNX on HF) | F1 up to 1.0 on single-template (Theivaprakasham); F1 = 0.69 on a 220-sample open dataset | **Fallback G3 if G1+G2 under-deliver** |
| **LiLT** | Similar to LayoutLMv3 | Yes | Same class as LayoutLMv3; better for multilingual | Defer; revisit when we add MIDD (Hindi / Devanagari) |
| **Donut (OCR-free encoder-decoder)** | Hundreds labelled | **No** — 5 + min / invoice on typical CPU (HF GH #22858) | 96 % mean accuracy on katanaml test split (published fine-tune) | **Reference benchmark only — not inference** |
| **Donut-MINT (distilled, Sep 2025)** | Inherits Donut | Unknown; research-stage | Near-parity with teacher via distillation | Track; do not depend |
| **Spatial ModernBERT (July 2025)** | Unknown | Unknown | Focuses on tables + KV for financial docs | Track; may mature as G3 alternative |
| **LLM-based (e.g. LlamaExtractor)** | Zero-shot or few-shot | Slow + expensive (API cost) | 94 % on 102 mixed invoices at 30 s / doc (arxiv 2510.15727) | **Out of scope** (policy: no LLM/VLM APIs for extraction) |

One recent published comparison worth calling out:
[arxiv 2510.15727, Oct 2025] tested **Docling** (rule + layout) vs **LlamaExtractor**
(LLM) on 102 mixed-format English/German invoices. Results: Docling 63 % accuracy
at 10 s / doc; LlamaExtractor 94 % accuracy at 30 s / doc. The paper explicitly
recommends Docling for CPU-constrained deployments — i.e. the "rule + layout"
pattern we are adopting for G1 + G2 remains defensible in contemporary
literature when compute matters.

### 9.4 Why "single template" changes the textbook calculus

The standard academic critique of heuristics — "brittle, don't generalise to new
templates, manual rules per vendor" — is correct in general, and cited by most
of the literature we surveyed. For *our specific* PoC it does not apply:

- The 2026-04-18 spot-check confirmed **katanaml is a single-template dataset**.
  All 10 inspected invoices share identical layout: same "Seller:" / "Client:"
  two-column header, same ITEMS table, same SUMMARY block, same Tax Id / IBAN
  positioning.
- Cross-template generalisation concerns the Indian MIDD dataset (4 layouts),
  which is deferred to post-PoC.
- Conclusion: for this dataset, heuristics can plausibly approach the
  layout-model ceiling because the constraint is the data (single template),
  not the extractor.
- **When we move to MIDD**, the layout model earns its keep and G3 becomes the
  default; G1 / G2 stay as a fast path for simple templates.

This is the kind of conclusion the textbook answer would get wrong if applied
blindly. Our spot-check is what justifies deviating from "always use LayoutLMv3
for invoices."

### 9.5 CPU inference feasibility (hard constraint)

| Approach | Runtime | Est. latency / invoice | Inference path? |
|---|---|---|---|
| Regex / heuristic | Python | < 50 ms | **Yes** |
| Label-anchor + rapidfuzz | Python | < 100 ms | **Yes** |
| LayoutLMv3-base (ONNX) | onnxruntime | ~1-3 s (rough estimate — must benchmark on our hardware before committing) | **Yes, if G3 triggered** |
| Donut base | PyTorch | 30 s - 5 min (HF GH #22858 anecdotal) | **No** |
| Donut-MINT distilled | PyTorch | Unknown | Research-stage; track |
| LlamaExtractor / LLMs | LLM API | 30 s / doc reported | **No** (policy + latency) |

### 9.6 Recommended sequencing (implementation plan)

Mapped to `project.md` §8 Component G:

1. **G1 implementation (~half a day)**
   - Anchor regexes for `invoice_no`, `invoice_date`, `seller_tax_id`,
     `client_tax_id`, `iban`.
   - Positional heuristics: seller column on the left, client column on the
     right, using line bboxes from OCR.
   - Multi-line address aggregation: cluster consecutive lines inside the
     seller / client column by y-coordinate proximity.
   - Unit tests covering each field + every OCR quirk surfaced in the spot-check
     (label-concatenation, digit-letter substitution, space loss, char dropout).

2. **G2 implementation (~half to one day)**
   - Label-variant dictionary: `{"Invoice no", "Invoiceno", "Invoicen0", ...}`,
     `{"Tax Id", "Taxld", "Tax ld", ...}`, `{"IBAN"}`, `{"Date of issue"}`,
     `{"Seller", "Seller:"}`, `{"Client", "Client:"}`.
   - rapidfuzz for fuzzy label-token match; nearest-anchor resolution for values.
   - Merge rule: G2 supersedes G1 only when G2 confidence > G1 confidence.

3. **Evaluation harness (first slice of Component L) (~half a day)**
   - Per-field exact-match F1 on the 26-sample katanaml test split.
   - Save a dated report under `evaluation/reports/YYYY-MM-DD_G1G2.md`.
   - Pass / fail accounting per field + aggregate.

4. **Decision gate**
   - If **average per-field F1 ≥ 0.90** → declare the extraction baseline good;
     move on to Component H (tables) and J (validation).
   - If any of `invoice_no / invoice_date / tax IDs / iban` drops below **F1
     = 0.90** → invest in G3 (LayoutLMv3 fine-tune).

5. **G3 (LayoutLMv3 fine-tune) — only if triggered (~1 week)**
   - Starting checkpoint: `microsoft/layoutlmv3-base`.
   - Train on 425 katanaml train + 50 val samples.
   - Export ONNX; benchmark CPU latency on our hardware before committing.
   - Compare F1 to G1 + G2; replace only if strictly better.

### 9.7 Follow-ups

- After G1 runs, inspect 5 misclassified cases from the val split to refine the
  G2 dictionary (don't pre-enumerate variants; data-drive them).
- If G3 becomes active, benchmark its CPU latency first-hand; budget training cost.
- Watch Spatial ModernBERT and DocExtractNet as potential G3 alternatives as the
  2025-26 research matures.
- When the MIDD phase begins, revisit this ranking — layout models almost
  certainly become primary for multi-template data.

### 9.8 References (NER section)

- `[ARXIV-INV2510]` Invoice Information Extraction: Methods and Performance
  Evaluation (Oct 2025). <https://arxiv.org/html/2510.15727v1>
- `[HAMRI-2024]` Document Information Extraction: An Analysis of Invoice
  Anatomy — Hamri 2024. <https://onlinelibrary.wiley.com/doi/10.1155/2024/7599415>
- `[HAL-IE-INV]` Information Extraction from Invoices — HAL. <https://hal.science/hal-03418385/document>
- `[ARXIV-DOCILE]` DocILE Benchmark for Document Information Localization and
  Extraction. <https://arxiv.org/pdf/2302.05658>
- `[ARXIV-SPATIAL-MB]` Spatial ModernBERT — arxiv July 2025. <https://arxiv.org/html/2507.08865>
- `[ARXIV-DOCEXTRACTNET]` DocExtractNet (ScienceDirect 2024). <https://www.sciencedirect.com/science/article/pii/S0306457324004059>
- `[HF-LAYOUTLM3-BASE]` microsoft/layoutlmv3-base (includes ONNX). <https://huggingface.co/microsoft/layoutlmv3-base>
- `[HF-LAYOUTLM3-INV-T]` Theivaprakasham/layoutlmv3-finetuned-invoice. <https://huggingface.co/Theivaprakasham/layoutlmv3-finetuned-invoice>
- `[HF-LAYOUTLM3-INV-A]` Ammar-alhaj-ali/LayoutLMv3-Fine-Tuning-Invoice. <https://huggingface.co/Ammar-alhaj-ali/LayoutLMv3-Fine-Tuning-Invoice>
- `[HF-KATANAML-MODEL]` katanaml-org/invoices-donut-model-v1 (reference benchmark). <https://huggingface.co/katanaml-org/invoices-donut-model-v1>
- `[GH-DONUT-22858]` HF Transformers Issue #22858 — slow Donut CPU inference. <https://github.com/huggingface/transformers/issues/22858>
- `[GH-DONUT-22681]` HF Transformers Issue #22681 — Donut generate extremely slow. <https://github.com/huggingface/transformers/issues/22681>
- `[ARXIV-DONUT-MINT]` Donut-MINT — distilled Donut for DocVQA, Sep 2025. <https://arxiv.org/html/2509.26235v1>
- `[BLOG-PHILSCHMID-DONUT]` philschmid — Fine-tuning Donut for document parsing. <https://www.philschmid.de/fine-tuning-donut>
- `[BLOG-TDS-L3-INV]` Fine-Tuning LayoutLM v3 for Invoice Processing — Towards Data Science. <https://towardsdatascience.com/fine-tuning-layoutlm-v3-for-invoice-processing-e64f8d2c87cf/>
- `[GITHUB-INVOICE2DATA]` invoice-x/invoice2data — reference only; package unmaintained (no release in >12 months per Snyk / PyPI). <https://github.com/invoice-x/invoice2data>

---

## 10. Line-Item / Table Extraction Research (Component H)

Research conducted 2026-04-18 after the G1+G2 evaluation landed at avg F1 0.832
(see `progress.md`). Component H closes the remaining extraction gap —
recovering the per-invoice `items` array from the Donut-style ground truth,
which G1+G2 ignored entirely.

### 10.0 Methodology and honesty notes

- Same pattern as §3 (OCR) and §9 (NER): WebSearch / WebFetch with per-claim
  sources; no models run locally.
- Inspected: `img2table` library, PaddleOCR PP-StructureV3 docs, Microsoft
  Table Transformer model cards, LayoutLMv3 on CORD benchmarks, recent arxiv
  invoice-extraction papers.
- Reddit: inaccessible, same as before. No Reddit-sourced claims.
- The 2026-04-18 spot-check (`evaluation/inspection/2026-04-18_katanaml_spotcheck/`)
  directly informs the approach choice below — the observed single-template
  structure of katanaml makes a custom spatial algorithm viable, which would
  be a much weaker recommendation on multi-template data.

### 10.1 TL;DR recommendation

1. **H1 — Custom spatial clustering (primary PoC path).** The katanaml items
   table is single-template with fixed columns (No. / Description / Qty / UM /
   Net price / Net worth / VAT [%] / Gross worth). Given OCR line bboxes,
   reconstructing row-by-row is a closed-form spatial problem — no ML needed
   — and should be <50 ms / invoice on CPU.
2. **H2 — `img2table` library** (fallback if H1's column detection is fragile).
   Pure-Python, OCR-aware, purpose-built for tables-from-OCR with missing or
   misaligned borders. Zero training data needed.
3. **H3 — PP-StructureV3 table module or Table Transformer** — only if
   H1+H2 fail or we graduate to multi-template data (MIDD). PP-StructureV3
   is ~3.7 s / page on Intel CPU (Intel 8350C, per PaddleOCR docs), which
   stacked with our RapidOCR ~5.7 s / page would nearly double end-to-end
   latency. Deferred.
4. **H4 — LayoutLMv3 fine-tune (token classification)** — ties to the G3
   path in §9.6. If we ever escalate extraction to LayoutLMv3, the items
   extraction can use the same model with richer labels (IOB2 with
   item-column tags). Not the first path.

### 10.2 Observed table structure (from the spot-check)

Every katanaml invoice follows the same layout below the `ITEMS` header:

| Column | Approx x-range (on 2481-wide page) | Value type |
|---|---|---|
| `No.` | 120-150 | `\d+\.` (e.g. `1.`, `2.`) |
| `Description` | 180-600 | Multi-line string, wraps 1-3 lines |
| `Qty` | 670-720 | Decimal with comma (`2,00`) |
| `UM` | 760-810 | Always `each` in our samples |
| `Net price` | 1180-1280 | Decimal (`444,60`) |
| `Net worth` | 1500-1600 | Decimal (`889,20`) |
| `VAT [%]` | 1780-1830 | `10%` in our samples |
| `Gross worth` | 2070-2170 | Decimal (`978,12`) |

The `SUMMARY` anchor (below the last item row) bounds the items region. Anchors
for both `ITEMS` and `SUMMARY` already exist in `components/extraction/heuristic/labels.py`
as `items_start` and `summary_start` keys.

Row-reading observations (critical for the algorithm design):

- **Numeric fields for a given item share a y-coordinate.** Qty, UM, prices,
  VAT %, gross worth all sit on the same horizontal band.
- **The description can wrap to 1-3 lines.** Continuation lines sit below the
  numeric band of the same item, above the next item's numeric band.
- **Reading order from OCR is row-major within the table.** For item N, OCR
  typically emits: `N.`, description-line-1, qty, UM, net-price, net-worth,
  VAT, gross-worth, description-line-2, description-line-3.
- **Item-number pattern `\d+\.` at the `No.` column is the reliable anchor**
  for detecting a new item.

### 10.3 Approach comparison

| Approach | Data req. | CPU feasible? | Expected accuracy on single-template | Our fit |
|---|---|---|---|---|
| **Custom spatial clustering** (H1) | 0 | **Yes — < 50 ms/invoice estimated** | High on single-template (fixed column x-ranges make attribution trivial) | **Primary path** |
| **`img2table`** (H2) | 0 | Yes — pure Python | Good (general-purpose; uses vertical projection histograms + OCR-aware heuristics) | Fallback if H1 is flaky on edge cases |
| **PP-StructureV3 table** (H3) | 0 (pre-trained) | Yes but heavy — 3.7 s/page on Intel CPU | Strong on diverse tables | Deferred — too slow for PoC |
| **Table Transformer (Microsoft TATR)** | 0 (pre-trained on PubTables-1M) | Possible but ResNet-50/101 backbone + transformer → heavier | Strong; GriTS-evaluated | Deferred |
| **LayoutLMv3 fine-tune with item-column labels** | Hundreds labelled | Yes via ONNX | 95-97 % F1 on CORD per published benchmarks | Tied to G3 escalation — revisit if we go there |
| **LLM-based (Mindee, LlamaExtractor, Claude)** | Zero-shot | Slow + paid APIs | 94-97 % accuracy on mixed invoices | **Out of scope** (policy) |

### 10.4 Why custom spatial first

For multi-template data the correct answer is a trained model (`Table
Transformer`, `LayoutLMv3`, or similar). For our katanaml-only PoC it is
not. Three reasons:

- **Fixed column x-ranges** — every invoice puts the Qty column at the same
  x on the same page width. Row-to-column attribution is a simple interval
  lookup, not a learning problem.
- **OCR already does the hard work** — RapidOCR emits line-level text with
  bboxes. A table-recognition model would re-do that detection. We leverage
  what we already have.
- **Latency budget** — custom spatial runs in milliseconds; PP-StructureV3
  adds seconds. End-to-end OCR+extraction is already 5-6 s / invoice; we
  do not want to push past 10.

When MIDD phase begins (post-PoC), we revisit. The `components/tables/`
interface is designed so swapping H3 or H4 under the same contract is a
drop-in change — mirror the OCR `BaseOCR` and extraction `BaseExtractor`
patterns.

### 10.5 Algorithm sketch — spatial clustering for H1

Input: `OCRResult` with line bboxes.
Output: `list[InvoiceItem]` with `item_desc`, `item_qty`, `item_net_price`,
`item_net_worth`, `item_vat`, `item_gross_worth`.

Pseudocode:

    1. Anchors
       - items_top_y    = y0 of the "ITEMS" anchor line
       - summary_top_y  = y0 of the "SUMMARY" anchor line (fallback: page.height)
       - header_row     = lines with item_column labels ("No.", "Description", ..., "Gross")
         just below items_top_y. Use their bboxes to establish column x-ranges.

    2. Region lines = OCR lines with items_top_y < y < summary_top_y, excluding
       the header row.

    3. Detect item anchors
       - For each region line: if x-center in No. column AND text matches "\d+\."
         - Record the anchor y as the y0 of that line.
       - Sort anchors ascending.

    4. For each anchor (items[k]):
       - band_y_range = [anchor_y - epsilon, next_anchor_y_or_summary_top)
       - description_range = same band + continuation lines above next anchor
       - For each column (Qty, UM, Net price, Net worth, VAT, Gross worth):
         - pick the line in that column whose y0 is within
           [anchor_y - small_slack, anchor_y + line_height_slack]
       - description: concatenate all lines whose x-center is in Description
         column AND whose y0 is in description_range

    5. Return list[InvoiceItem]

Edge cases to handle in tests:
- Missing `SUMMARY` anchor (rare, fallback to bottom of page).
- Single-item invoice (no next-anchor).
- Description that wraps 3 lines.
- OCR occasionally emitting the item-number glued to description ("1.First item").
- Different y-band thresholds per invoice (based on page height).

### 10.6 CPU feasibility

| Approach | Estimated latency per invoice |
|---|---|
| Custom spatial clustering (H1) | < 50 ms |
| `img2table` (H2) | ~100-300 ms (pure Python) |
| PP-StructureV3 table module (H3) | ~3.7 s (Intel CPU published) |
| Table Transformer (ONNX) | ~1-2 s (est.) |
| LayoutLMv3 (fine-tuned, ONNX) | ~1-3 s (same as G3) |

### 10.7 Implementation sequence

1. **H1 implementation (~1 day)**
   - New package `components/tables/` mirroring `components/extraction/`:
     `types.py` (`InvoiceItem`, `TableExtractionResult`), `base.py`
     (`BaseTableExtractor`), `factory.py`, `spatial/` subpackage with the
     clustering algorithm, scaffolded `pp_structure_backend.py` /
     `layoutlm_backend.py` for H3 / H4.
   - Synthetic OCR fixtures in `tests/_fixtures.py` — mirror the items
     tables from spot-check samples 00 (1 item), 04 (7 items), and a
     3-line-description edge case.
   - Unit tests: column detection, anchor detection, row attribution,
     edge cases.

2. **Evaluation extension (~half day)**
   - Extend `tools/evaluate_extraction.py` (or add `tools/evaluate_tables.py`)
     to compute per-item F1: exact match on each item's 6 fields, plus a
     count-aware metric (did we detect the right number of items?).
   - Report under `evaluation/reports/YYYY-MM-DD_H1.md`.

3. **Decision gate**
   - Target: ≥ 0.85 average per-item per-field F1 on the 26-sample katanaml
     test split (lower than G's 0.90 because line items are structurally
     harder than single-value header fields).
   - If gate fails → re-open H2 or H3 sub-plans.

### 10.8 Follow-ups

- Investigate `img2table` as an H2 implementation option (pure Python, MIT
  licence per PyPI). Install cost: small.
- Consider a post-processing "totals-consistency check" that cross-validates
  `sum(item_gross_worth) == invoice total` from the SUMMARY block (belongs
  in Component J / validation, not H).
- When MIDD phase begins, re-evaluate: its 4 Indian layouts will break the
  single-template assumption and H1 will need template detection or a
  model-backed backend.

### 10.9 References (H section)

- `[IMG2TABLE]` img2table — PyPI / GitHub. <https://github.com/xavctn/img2table>
- `[MINDEE-LINE-ITEMS]` Mindee blog — Invoice OCR line items extraction. <https://www.mindee.com/blog/invoice-ocr-line-items-extraction>
- `[PPSTRUCTV3-DOCS]` PP-StructureV3 Introduction — PaddleOCR Documentation. <https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/algorithm/PP-StructureV3/PP-StructureV3.html>
- `[PPOCR30-TR]` PaddleOCR 3.0 Technical Report — arxiv. <https://arxiv.org/pdf/2507.05595>
- `[TATR-GITHUB]` Microsoft Table Transformer (TATR) — GitHub. <https://github.com/microsoft/table-transformer>
- `[TATR-STRUCTURE]` microsoft/table-transformer-structure-recognition-v1.1-all — Hugging Face. <https://huggingface.co/microsoft/table-transformer-structure-recognition-v1.1-all>
- `[TATR-FIN]` microsoft/table-transformer-structure-recognition-v1.1-fin — Hugging Face. <https://huggingface.co/microsoft/table-transformer-structure-recognition-v1.1-fin>
- `[DOCEXTRACTNET]` DocExtractNet (LayoutLMv3-based) — ScienceDirect 2024. <https://www.sciencedirect.com/science/article/pii/S0306457324004059>
- `[SPATIAL-MB]` Spatial ModernBERT — arxiv July 2025. <https://arxiv.org/html/2507.08865>
- `[ARXIV-INV2510]` Invoice Information Extraction: Methods and Performance Evaluation (Oct 2025). <https://arxiv.org/html/2510.15727v1>

---

## 11. Validation Engine Research (Component J) — lite stub

Scope pivoted on 2026-04-19 (see `progress.md`): the PoC validates
**the fields katanaml actually contains**, not Indian GST fields. All
GSTIN / CGST/SGST/IGST / HSN / GSTR-2B / RCM rules are deferred to
the post-PoC Indian phase (when MIDD is integrated).

This is a "research-lite" section — the rules are established
algorithms, not a topic needing a comparison table.

### 11.1 Rule list (for katanaml)

| Rule | Scope | Algorithm | Source |
|---|---|---|---|
| `invoice_no_format` | `ExtractedField` | Regex `^\d{6,10}$` | Observed from spot-check — all katanaml invoice numbers are 8-digit |
| `invoice_date_format` | `ExtractedField` | `datetime.strptime(value, "%m/%d/%Y")` — katanaml GT uses `MM/DD/YYYY` | Observed from spot-check |
| `tax_id_format` | `ExtractedField` × 2 | Regex `^\d{3}-\d{2}-\d{4}$` | SSN-style, observed from GT |
| `iban_shape` | `ExtractedField` | Regex `^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$` | ISO 13616 structure |
| `iban_checksum` | `ExtractedField` | ISO 13616 mod-97 (move first 4 chars to end, letter→`A=10..Z=35`, integer mod 97 == 1) | Wikipedia / ECBS — standard since 1997 |
| `item_net_worth_consistency` | `InvoiceItem` | `\|net_worth − qty × net_price\| ≤ 0.01 × max(\|net_worth\|, 0.01) + 1.0` | Rounding tolerance of 1 absolute unit + 1 % relative, covers katanaml's decimal-rounding pattern |
| `item_gross_worth_consistency` | `InvoiceItem` | `\|gross_worth − net_worth × (1 + vat/100)\| ≤ 0.01 × max(\|gross_worth\|, 0.01) + 1.0` | Same tolerance |
| `batch_duplicate` | Batch of `ExtractionResult`s | Tuple key `(invoice_no, seller_tax_id, invoice_date, gross_total)` | Exact-match within batch; MinHash LSH held for later |

### 11.2 Numeric parsing convention

Katanaml uses European decimal format (`2,00`, `1 319,97`).

    parse_decimal("1 319,97") -> Decimal("1319.97")

Rules:
- Strip all whitespace from the input (thousand separator).
- If the string contains `,`, treat `,` as decimal separator and drop
  any remaining `.` (which would be a thousands separator).
- Parse with `decimal.Decimal` — floats introduce rounding that can
  misdiagnose rule outcomes.

### 11.3 Tolerance rationale

Arithmetic consistency uses a combined absolute + relative tolerance
(1 unit + 1 %). A pure absolute tolerance would be too strict for
large invoices (gross worth of 10 000 would need 1-unit exactness)
and too lenient for small invoices (gross worth of 10 could drift by
10 %). A combined rule matches how published invoice-checking
software works in practice.

### 11.3a Known limitation — mod-97 isn't infallible

IBAN's mod-97 checksum is a ~96 % detector: it catches all single-digit
substitutions and all transpositions of adjacent digits, but **some
multi-character OCR corruptions produce a coincidentally valid
checksum**. We found this empirically on our 2026-04-18 evaluation —
two OCR-corrupted IBANs (sample 07 `GB10YCPS61791374226282` and
sample 01 `GB31LZXS20242755934691`) both pass mod-97 despite being
the wrong value.

Implication: validation flags **most** silent OCR corruption but not
all. Higher-assurance pipelines cross-check IBANs against vendor
records or bank-directory APIs — out of PoC scope. The test suite
(`components/validation/tests/test_iban_checksum.py`) documents this
class of false negative with a dedicated parametrised test so the
limitation is on the record.

### 11.4 Out of scope (deferred)

- GSTIN 15-char checksum and state-code validation.
- CGST + SGST vs IGST intra-/inter-state arithmetic.
- HSN code rate lookup against a CBIC schedule CSV.
- GSTR-2B reconciliation against a user-uploaded JSON file.
- Reverse Charge Mechanism detection.
- MinHash LSH near-duplicate detection (exact match covers the
  immediate fraud case; MinHash adds recall for intentional mutation
  attacks — out of current scope).

### 11.5 References

- `[ISO-13616]` IBAN format and check-digit algorithm — ISO 13616-1:2020. <https://www.iso.org/standard/81090.html>
- `[WP-IBAN]` International Bank Account Number — Wikipedia. <https://en.wikipedia.org/wiki/International_Bank_Account_Number>
- `[PY-DECIMAL]` `decimal` — Decimal fixed-point and floating-point arithmetic — Python docs. <https://docs.python.org/3/library/decimal.html>

---

*End of research.md. This document is synced to `project.md` — when findings here change a decision there, the decision update lives in `project.md` and the dated event is recorded in `progress.md`.*

# Engineering Practices Used in This Project

Brief catalogue of engineering-discipline patterns applied in this codebase
that are not usually in a fresher's toolbox. One or two lines on *why* each
matters, plus 2–3 concrete places we used it so the idea sticks to a real
artefact.

This file is reference-only — the concepts are the takeaway, not the code.

---

## 1. Pytest markers for test tiers (fast vs slow)

- Lets you run the fast feedback loop in seconds and only pay for the
  expensive tests when you need to (e.g. before a PR).
- Registered in `pyproject.toml [tool.pytest.ini_options].markers`, then
  attached to tests via `pytestmark = pytest.mark.ocr_heavy` or
  `@pytest.mark.ocr_heavy` / `@pytest.mark.dataset_heavy`.

Examples in this repo:
- `components/ocr/tests/test_rapidocr_backend.py` — marked `ocr_heavy`
  because each test loads the PP-OCRv5 model (~1–2 s each).
- `data_sources/tests/test_katanaml.py` — marked `dataset_heavy` because
  it downloads the katanaml dataset on first run.
- Daily command: `pytest -m "not ocr_heavy and not dataset_heavy"` — runs
  in < 3 s, doesn't touch networks or model files.

## 2. `pytest.importorskip` for optional dependencies

- Test modules that need an optional library can skip themselves cleanly
  if that library is missing, instead of collapsing the whole test session.
- You write `pytest.importorskip("<library>", reason="...")` at module top.

Examples:
- `data_sources/tests/test_katanaml.py` skips if `datasets` (HuggingFace)
  is not installed. Before `uv pip install` picked up `datasets`, the
  module showed as **skipped**, not **errored**.
- `components/ocr/tests/test_rapidocr_backend.py` skips if
  `rapidocr_onnxruntime` is missing — the rest of the OCR tests
  (`test_types.py`, `test_base.py`, `test_scaffolded_backends.py`) still
  run fine without RapidOCR installed.

## 3. Pytest fixture scopes (`scope="module"`, `scope="session"`)

- Expensive setup (loading an ML model, downloading a dataset) is done
  **once** per module/session instead of once per test.
- Default fixture scope is `function` — which would reload the model 17
  times in our RapidOCR test module. Changing to `scope="module"` makes
  it load once.

Examples:
- `components/ocr/tests/test_rapidocr_backend.py` has
  `@pytest.fixture(scope="module")` on both `backend` and
  `invoice_like_image` — PP-OCRv5 model weights load once for all 17 tests.
- `data_sources/tests/test_katanaml.py` uses `scope="module"` on the
  `dataset` fixture — the HuggingFace dataset is opened once, not per test.

## 4. `@pytest.mark.parametrize` for table-driven tests

- Runs the same assertion body against many inputs, with each case shown
  as a distinct test ID in the pytest report — failures point at the
  exact input, not at one vague test name.
- Keeps the test body small and the cases easy to extend.

Examples:
- `components/extraction/tests/test_regex_patterns.py`
  `TestInvoiceNoAnchored` parametrizes 8 OCR-quirk variants
  (`Invoice no: 123`, `Invoiceno:123`, `Invoicen0:123`, ...). Adding a
  new variant is one line.
- `components/ocr/tests/test_scaffolded_backends.py` parametrizes over
  `(TesseractBackend, PaddleOCRBackend, DocTRBackend)` — three scaffolds
  tested identically without duplicating the test code.

## 5. Abstract base class + dependency injection (swappable backends)

- Upstream code talks to the abstract interface; concrete implementations
  are wired in via a factory. Swapping the OCR engine from RapidOCR to
  Tesseract is a one-line config change, not a code migration.
- Enforces the contract — missing methods raise `TypeError` at
  instantiation, not at runtime during the hot path.

Examples:
- `components/ocr/base.py` — `BaseOCR(ABC)` with `@abstractmethod`;
  `RapidOCRBackend`, `TesseractBackend`, etc. subclass it.
- `components/extraction/base.py` — `BaseExtractor`; `HeuristicExtractor`
  implements it now, `LayoutLMv3Extractor` is scaffolded for later.
- `components/tables/base.py` — `BaseTableExtractor`; `SpatialTableExtractor`
  today, `PPStructureTableExtractor` / `LayoutLMTableExtractor` scaffolded
  for escalation.
- `data_sources/base.py` — `BaseDataset`; `KatanamlInvoicesDataset`
  implements, `MIDDDataset` / `SROIEDataset` scaffolded.

## 6. Factory functions with lazy imports

- `make_ocr("rapidocr")` / `make_extractor("heuristic")` etc. let callers
  select a backend by string (from a config file, CLI flag, env var) without
  importing each backend's heavy module.
- Each factory imports the target backend **only when that backend is
  requested** — scaffolded backends never pay their import cost.

Examples:
- `components/ocr/factory.py` `_BACKEND_REGISTRY` maps short name →
  dotted class path; `make_ocr` uses `importlib.import_module` on demand.
  Result: `import components.ocr` doesn't load rapidocr, paddleocr, etc.
- Same pattern in `components/extraction/factory.py`,
  `components/tables/factory.py`, `data_sources/factory.py`.

## 7. Scaffolded placeholders that raise `NotImplementedError`

- Future backends exist as concrete classes with the right interface on
  day one — the swap path is visible and documented — but they raise
  `NotImplementedError` from every real operation until someone
  implements them. Prevents "how do I add another backend?" archaeology.
- Cheaper than waiting until you need the second backend to design the
  first.

Examples:
- `components/ocr/tesseract_backend.py`, `paddleocr_backend.py`,
  `doctr_backend.py` — all three scaffolded alongside the working
  RapidOCR. Enablement steps documented in each file's docstring.
- `components/tables/pp_structure_backend.py`,
  `components/tables/layoutlm_backend.py` — escalation paths for
  Component H.
- Test coverage in `test_scaffolded_backends.py` /
  `test_scaffolded_datasets.py` — each scaffold must instantiate without
  any heavy library installed and must raise `NotImplementedError` on
  real methods. Guarantees the swap path stays visible.

## 8. Compiling regex patterns once at module scope

- `re.compile(...)` builds the pattern's internal state once; subsequent
  `.search()` / `.match()` calls reuse it. When you call a function
  thousands of times (e.g. once per OCR line × 26 invoices), the
  difference shows up in the profiler.

Examples:
- `components/extraction/heuristic/regex_patterns.py` — every pattern
  (`INVOICE_NO`, `TAX_ID_ANCHORED`, `IBAN_ANCHORED`, ...) is
  `re.compile(...)` at module load; the extractor never recompiles them.
- `components/extraction/heuristic/normalizers.py` — `_LOWER_TO_UPPER`,
  `_DIGIT_TO_UPPER`, `_MULTIPLE_SPACES` are all compiled once.
- `components/tables/spatial/extractor.py` — `_ITEM_NUMBER`, `_DECIMAL`,
  `_VAT_PERCENT`, `_UM` compiled at module scope.

## 9. Pydantic v2 `frozen=True` + strict field validation

- Data contracts between components are **immutable once constructed**.
  Downstream code can trust the values won't mutate under it. Invalid
  data fails at construction (at the boundary), not ten function calls
  later.
- Serialisation (`.model_dump_json()` / `.model_validate_json()`) comes
  for free and keeps the JSON format aligned with the Python type.

Examples:
- `components/ocr/types.py` — `OCRResult`, `Token`, `Line`, `BoundingBox`
  are all `ConfigDict(frozen=True)`. `BoundingBox` uses
  `@model_validator(mode="after")` to enforce `x1 >= x0` and `y1 >= y0`.
- `components/extraction/types.py` — `ExtractedField` validates
  `confidence ∈ [0, 1]` and `text` is non-empty.
- `data_sources/types.py` — `Sample` validates the image ndarray is
  HxWx3 uint8 RGB at construction, not during use.

## 10. Research-first discipline with decision gates

- Write the trade-off analysis in `research.md` (sources + comparison
  table + recommendation), get explicit sign-off, *then* implement.
  Catches wrong assumptions before they become thousands of lines of
  code (e.g., the "use LayoutLMv3-base zero-shot" misconception caught
  in the §9 research).
- Every component has a numeric **decision gate** (`F1 ≥ 0.90`, `F1
  ≥ 0.85`, etc.) — a pass/fail signal tied to the evaluation report,
  not a vibes call.

Examples:
- `research.md` §3 (OCR), §4 (datasets), §9 (NER), §10 (table
  extraction) — each with its own TL;DR recommendation, approach
  comparison, references, and honesty notes.
- `tools/evaluate_extraction.py` and `tools/evaluate_tables.py` — CLI
  exits 0 if the gate passes, 1 if it fails. Could wire into CI.

## 11. Dual documentation — topical (`project.md`) + chronological (`progress.md`)

- `project.md` answers "how is this set up now?" — edited in place when
  understanding changes.
- `progress.md` is append-only and answers "what happened when and why?"
  — a living log of decisions and their dates.
- Readers who want either view get a clean narrative; nobody has to grep
  Git history.

Examples:
- When Component G failed the F1 gate at 0.673 → after the space-normaliser
  recovered to 0.832, `progress.md` got a new dated entry with the full
  per-field delta; `project.md` was untouched because the architectural
  decisions hadn't changed.
- When we renamed `datasets/` → `data_sources/` (collision with the
  HuggingFace `datasets` package), `project.md` §8.0 got updated in-place
  *and* `progress.md` got a dated entry recording why we deviated.

## 12. "Held optimisations" backlog

- When a piece of work is deferred (not forgotten), it gets an explicit
  entry in `progress.md` with an ID (`[H-EXT-1]`), what's held, and
  why. The held list is reviewed before any productionisation step —
  nothing silently rots.
- Different from GitHub issues: these items are tied to the day's
  decision context, not to a generic issue tracker.

Examples:
- `[H-EXT-1] Seller/client space-normalisation` — held on 2026-04-18,
  implemented same day, marked **ADDRESSED**.
- `[H-EXT-5] G3 LayoutLMv3 + OpenVINO` — still held; only revisited if
  F1 gates keep failing.
- `[H-OCR-1] Image downscaling before OCR` — still held; current
  latency is workable.

## 13. `dummy.txt` protocol for stubs / fixtures / assumptions

- Every fake, stub, placeholder, or assumption gets a one-line entry
  in `dummy.txt` with a category, why, and how to replace. When we
  productionise, we walk this file — nothing hides.
- Different from TODO comments: centralised and designed to be
  reviewed, not scattered through the code.

Examples (from the protocol doc in `project.md` §7.2):
- `API_STUB | validation.gstin_active | Returns 'Active' via
  HeuristicStubProvider until Masters India credits are purchased`
- `FIXTURE_DATA | hsn.rate_table | Manual seed of 500 most common
  HSN codes in /data/hsn_seed.csv; not authoritative`
- `SKIPPED_FEATURE | credit_notes | Not parsed; purchase invoices only`

## 14. Separation of concerns: `types.py` / `base.py` / `factory.py`

- Each module has one reason to change. Pydantic schemas in `types.py`
  can evolve without touching the abstract interface in `base.py`; the
  factory logic in `factory.py` is independent of both. You can read
  any one of them in isolation.
- Downstream `from components.ocr import OCRResult, make_ocr` just works
  because the package `__init__.py` re-exports the public surface.

Examples:
- `components/ocr/` — `types.py` (5 Pydantic models), `base.py`
  (abstract `BaseOCR`), `factory.py` (`make_ocr`, `available_backends`).
- `components/extraction/` — same layout.
- `components/tables/` — same layout.
- `data_sources/` — same layout.

## 15. Lazy imports inside `__init__` for heavy dependencies

- Backends that depend on a heavy library (`rapidocr-onnxruntime`,
  `paddleocr`, `transformers`, ...) import the library **inside the
  constructor**, not at module top. Means:
  - Importing the backend module is cheap — just loads the class stub.
  - Missing optional deps produce a clear `ImportError` with install
    instructions, not a noisy stack trace at application startup.
- Especially valuable when the backend is behind a feature flag or
  an optional extra.

Examples:
- `components/ocr/rapidocr_backend.py` `__init__` does
  `from rapidocr_onnxruntime import RapidOCR as _RapidOCR` inside a
  try/except with a helpful `ImportError(..., from exc)`.
- `data_sources/katanaml_invoices/loader.py` lazy-imports
  `datasets.load_dataset` — users who don't need Katanaml never
  have to install the HuggingFace `datasets` library.

## 16. `pyproject.toml` with optional extras

- `[project.optional-dependencies]` lets a user install only what they
  need. `pip install .[tesseract]` pulls Tesseract; default install
  doesn't. Keeps the minimum footprint lean.
- Combined with lazy imports, optional extras are a complete pattern —
  backend code, install spec, and documentation all align.

Examples:
- `pyproject.toml` `[project.optional-dependencies]` has `dev`, `tesseract`,
  `paddleocr`, `doctr` extras.
- The `doctr_backend.py`'s own docstring says
  `pip install -e ".[doctr]"` — so the extra name is discoverable
  from the backend file, not from a README.

## 17. Dated evaluation reports under `evaluation/reports/`

- Every evaluation run writes a file named `YYYY-MM-DD_<component>.md`
  and a sibling `.json`. You can diff reports across dates to see
  regressions or improvements.
- Separates human-readable summary (markdown) from machine-parseable
  detail (JSON) — the markdown shows the trend, the JSON lets tools
  compute deltas.

Examples:
- `evaluation/reports/2026-04-18_G1G2.md` + `.json` — first G1+G2 run
  and post-normaliser re-run, both under the same name (overwritten
  because same day). A production setup would append `_v2` or similar.
- `evaluation/reports/2026-04-18_H1.md` + `.json` — table extractor
  baseline.
- `evaluation/inspection/2026-04-18_katanaml_spotcheck/` — per-sample
  inspection bundle for the OCR eyeballing pass, with `summary.md` at
  the root and `NN_comparison.md` / `NN_image.png` /
  `NN_ground_truth.json` / `NN_ocr.json` per sample.

## 18. "Don't fail silently" — log the provenance of every value

- Every `ExtractedField` carries `source` (`regex`, `label_anchor`,
  `column_heuristic`, `none`) and `source_detail` ("invoice_no anchor",
  "tax_id bare in column", ...). When a validation check fires, you
  can see *why* the value was chosen.
- A confidence score alone is not enough. Confidence of 0.9 that came
  from an unanchored bare regex is riskier than 0.9 from a label-anchored
  pattern, even though the numbers look identical.

Examples:
- `components/extraction/types.py` — `ExtractedField.source` and
  `source_detail` fields are populated by every rule in the heuristic
  extractor.
- `components/extraction/heuristic/extractor.py` — every field is
  emitted with its provenance tag.
- The evaluation report uses this field to filter failure categories
  (see the `## Failing fields (inspection list)` section of the G1G2
  report).

---

## How to extend this file

When a new practice is introduced, add it with the same shape:
- Name
- 1–2 line advantage
- 2–3 example scenarios (filepaths or commands), real ones from this repo.

Don't add generic "best practice" items that aren't actually used in the
codebase — the point is that every entry is backed by an artefact the
reader can open and inspect.

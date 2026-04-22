# Plan — Onboarding Platform: Two Independent Personas, Ingestion-Sourced Inbox, Persona-Tuned Dashboards

> **Scope:** Design only. No code, no SQL DDL, no Pydantic schemas, no API
> handler shapes. The deliverable is the aligned product + UX + dashboard
> + data-model design for the `business` branch. Implementation planning
> is a later turn.

---

## Context — why this, why now, what you clarified

`main` has the PoC components at baseline (OCR, extraction, tables,
validation — gated, frozen-contract, independently deployable). We're on
the `business` branch. `project.md` §1.3 explicitly deferred
multi-tenancy out of the prototype; that deferral ends now.

You clarified three load-bearing constraints that reshape the design:

1. **Two fully independent personas.** CA-firm and Business-enterprise
   each get their own accounts, onboarding UIs, dashboards, and data.
   They are **interconnected only at the ingestion-source layer** —
   Gmail / Outlook / WhatsApp connectors serve both — but never share
   workspaces, invoices, or linking relationships. A CA does not
   "invite clients"; the CA's notion of "clients" is **derived from the
   billed-to GSTIN in their own ingested invoices**, not from an
   explicit invitation/link table.
2. **Onboarding collects ingestion-source credentials day 1.** Gmail,
   phone number, Outlook (where available). UI scaffolds the connection
   flow as a demonstratable artefact even if the real connector
   implementations live on `ingestion/*`. Mock endpoints return stub
   success until that branch wires them up.
3. **Independent folder.** All business-layer code lives in a new
   `platform/` folder at repo root, separate from `components/` and
   `backend/`. `platform/` depends on `components/*` (it needs
   extraction) but `components/*` never imports from `platform/`.
   Folder-level independence preserves the branch governance model we
   agreed in the earlier conversation.

The user's third-question clarification reframes the language question
as a **UI-quality / engagement question**: English-only for now, but
research the best UI patterns per persona to make them "stay and get
connected actively." That is now §4 of this plan.

---

## 1. Persona research — who these users actually are

### 1.1 Business-enterprise (SMB owner)

| Dimension | Reality |
|---|---|
| Digital literacy | Low–medium. WhatsApp-native. PDF = "what my CA sends me." |
| Time economics | Irregular; opens app when vendor sends invoice or CA pings |
| Primary JTBD | *"Track my purchases automatically; don't let me pay the same invoice twice; know how much I spent."* |
| GST literacy | Often near zero; has heard "ITC" vaguely |
| Device | Phone-first (Android, mid-range); occasional desktop |
| Monthly cadence | 5–50 invoices/month |
| Biggest fear | GST notice (panic trigger) |
| Delights them | "All clear ✓"; "You saved ₹X"; "Here's your April summary" |
| What makes them stay | Positive reinforcement, outcome visibility, minimal friction, no tax jargon |

### 1.2 CA-firm

| Dimension | Reality |
|---|---|
| Digital literacy | High for work tools; low tolerance for novelty |
| Time economics | Billable; every extra click is money |
| Primary JTBD | *"Receive all my client invoices from multiple sources; extract reliably; reconcile against GSTR-2B; export to Tally fast."* |
| GST literacy | Fluent (GSTR-1/2B/3B, ITC, HSN, RCM) |
| Device | Desktop, often dual-monitor, Chrome |
| Monthly cadence | Deadline-driven — 10th (GSTR-1), 20th (GSTR-3B); 5-day crunch |
| Biggest fear | Missing GSTR-2B mismatch → client ITC blocked → CA blamed |
| Delights them | Dense portfolio view; zero ambiguity; keyboard speed; reliable export |
| What makes them stay | Hours saved / month; no flakiness during deadline week; Tally parity |

### 1.3 Interconnection — only at the source layer

```
  ┌──────────────────────────────┐
  │ Ingestion source adapters     │  (Gmail / Outlook / WhatsApp / folder)
  │ (shared infra — lives on      │
  │  ingestion/* branch)          │
  └────────┬─────────────────────┘
           │ pushes InvoiceInput
           ▼
  ┌──────────────┬────────────────┐
  │ Business     │  CA            │   (two fully independent account
  │ account      │  account       │    trees; no cross-account reads)
  │ - own inbox  │  - own inbox   │
  │ - own dash   │  - own dash    │
  └──────────────┴────────────────┘
```

---

## 2. Information needs / dashboard content — per persona

This is the "what exactly do they see" section you asked for.

### 2.1 Business dashboard — content spec

**Top strip (KPI tiles, left to right):**
| Tile | Value | Why |
|---|---|---|
| Invoices this month | count + delta vs last month | "Am I keeping up?" |
| Total spend | ₹ amount + delta | Cash-out visibility |
| ITC savable this month | ₹ amount | Outcome metric (even if they don't fully understand ITC, seeing rupees saved sticks) |
| Needs your review | count | Attention-routing — drives return visits |

**Visual panel (main body):**
- **Spend by vendor** (horizontal bar, top 5 + "others") — who am I paying
- **Spend trend** (line, last 6 months) — are my costs going up
- **Invoices by source** (small stacked bar: Gmail / Outlook / WhatsApp / Upload) — shows platform working ("2 came from WhatsApp without me lifting a finger")

**Lists (below the fold):**
- **Recent invoices** — 10 most recent, each row: source icon, vendor name (plain), date, amount, status icon (✓ / ⚠ / duplicate)
- **Needs your attention** — filtered list of flagged items, explanation in plain language

**Hidden from business dashboard:**
- Per-field extraction confidence
- CGST/SGST/IGST split detail (collapsed behind "tax details" link on invoice page)
- Rule-level validation breakdown (IBAN checksum proof, tax-math expected/observed)
- OCR metadata, processing times, pipeline version
- HSN codes

**Primary CTAs on business dashboard:**
- "+ Add Invoice" (camera / file upload)
- "Connect another source" (if < 2 sources connected)
- "Download this month as CSV" (for their own records)

### 2.2 CA dashboard — content spec

**Top strip (KPI tiles, left to right):**
| Tile | Value | Why |
|---|---|---|
| Clients (this month active) | count | Portfolio size awareness |
| Invoices this month | count + delta | Throughput check |
| Needs review | count | Work remaining |
| GSTR-2B mismatches | count | Risk surface |
| ITC-at-risk | ₹ amount | Financial stake across portfolio |
| Days to next GSTR deadline | integer + filing type | Urgency banner |

**Visual panel:**
- **Invoice volume by client** (horizontal bar, top 10 clients, sortable by volume or by flag count)
- **Validation issues by client** (stacked bar: pass / fail / n-a per client)
- **Processing pipeline funnel**: Ingested → Extracted → Reviewed → Approved (numbers per stage, drop-offs visible)

**Lists:**
- **Client list** — dense grid, row per derived client (grouped by billed-to GSTIN):
  - Columns: client name (GSTIN-derived or manually labelled), monthly invoice count, unreviewed count, flag count, GSTR-2B mismatch count, filing-ready status, last activity
  - Sortable, filterable, colour-coded (green / amber / red)
  - Click row → drill into client-scoped invoice list
- **Activity feed** — recent approvals, extractions, edits with actor + timestamp
- **Upcoming deadlines** — per client, per return type

**Shown on CA dashboard (and nowhere else):**
- Full validation rule breakdown per invoice (IBAN, tax math, duplicate, format, GSTR-2B match) with `expected` and `observed`
- Per-field extraction confidence
- Audit trail / event log
- OCR backend metadata (backend name, duration, pipeline version)
- Tally CSV export configuration

**Primary CTAs on CA dashboard:**
- "Review queue" (unreviewed, sorted by urgency)
- "Month-end mode" (one click → filters everything to filing-blockers)
- "Upload GSTR-2B" (drag-drop JSON for reconciliation)
- "Export to Tally" (range + client selector)

### 2.3 The derived-client insight — key to CA simplicity

> A CA's *client list* is not a separate entity table. It's the
> `GROUP BY client_gstin` over the CA's own invoices.

Implications:
- No invite flow, no pending rows, no link table — massive scope saving
- Client display name is initialised from the "billed-to" entity name
  extracted from the first invoice; CA can rename/merge later
- Two invoices with the same client_gstin but different spellings of
  the client name auto-collapse in the dashboard; CA sees one client
- When CA onboards, the client list starts empty and fills as invoices
  arrive — zero manual data entry

---

## 3. Unified ingestion inbox — first-class viewer

You specifically asked for this: a viewer that lists all invoices and
messages extracted from connected sources, with dates and metadata
(from whom / email / contact).

### 3.1 Shape — Gmail-inbox-for-invoices

The inbox is a **single-list view across all connected sources**, not
per-source tabs. Rows are chronological; filters do the per-source
scoping.

**Columns (business view):**
| Column | Content |
|---|---|
| Source | small icon: Gmail / Outlook / WhatsApp / Upload / Forwarded |
| From | sender email / contact name (WhatsApp sender name) / uploader |
| Received | date+time, relative ("2h ago") in recent, absolute older |
| Subject / File | email subject or attachment filename |
| Status | chip: `queued` / `extracting` / `extracted` / `failed` / `ignored` |
| Vendor | extracted vendor name (dim if not yet extracted) |
| Amount | extracted total (dim if not yet extracted) |
| Actions | "View" / "Extract now" / "Ignore" |

**Extra columns (CA view, same inbox table):**
- **Client** (derived from billed-to GSTIN; editable)
- **Validation flags** (icon count)
- **GSTR-2B match** (badge)

### 3.2 Filters

- Source (multi-select)
- Status (queued / extracting / extracted / failed / ignored)
- Date range
- Sender
- Search (full-text over subject, sender, vendor, filename)
- Business: toggle "needs my attention" (flagged only)
- CA: toggle "needs review" + client filter

### 3.3 Immediate vs scheduled extraction

Two levers, per your ask:

1. **Per-source default** — when connecting a source, user picks:
   - `Instant` — extract immediately on arrival (default for upload)
   - `Scheduled (nightly batch)` — extract at 2 AM local
   - `Manual only` — extract only when user clicks "Extract now"
2. **Per-invoice override** — inbox row action "Extract now" bumps any
   queued item to immediate.

**Why both:** CAs at month-end crunch need immediate extraction for
incoming urgents; for normal flow, nightly batch is cheaper and calmer.
SMBs usually want instant (single upload) so they see the result while
they're still looking.

Status transitions shown as a progress chip: `queued → ocr → extract →
validate → done`. Click the chip to see per-stage timing and errors.

### 3.4 "Ignore" / "not an invoice" signal

Not every email attachment is an invoice. Users need a quick "ignore"
action. Ignored rows don't count against flagged totals and don't
trigger extraction. Later this becomes training data for an "is-invoice"
classifier on the ingestion side.

---

## 4. UI patterns per persona — research-grounded

Your real ask on Q3: what patterns make each category stay and connect
actively. Below is the pattern research applied per persona.

### 4.1 Business — patterns known to drive SMB retention

| Pattern | Where seen | Why it works for SMB |
|---|---|---|
| One giant primary CTA | Shopify dashboard, Instagram "+" | Reduces decision load; one thing to do per visit |
| Outcome-first KPI tiles | Monzo / CRED spending summaries | "You saved ₹X" beats "92% accuracy" for non-technical users |
| Empty-state as onboarding | Dropbox, Notion | First-run has a guided single-step instead of blank |
| Progressive disclosure | Apple Settings | Hide complexity behind explicit "more" taps |
| Confirmation microcopy | WhatsApp "Forwarded"/"Read" | Reassurance via tiny reinforcements |
| Status as colour + icon, not text | iMessage delivery ticks | Readable at a glance regardless of literacy |
| Bottom-sheet for secondary actions | Instagram, WhatsApp | Thumb-reachable; low intimidation |
| Streaks / monthly summaries | Duolingo, Spotify Wrapped | Periodic re-engagement triggers |
| Push notification on state change | WhatsApp, Gmail | Brings users back without them remembering |
| Icon-led navigation | Indian super-apps (Paytm, PhonePe) | Reduces text dependence |

**Applied to our business dashboard:**
- Dashboard leads with a single "+ Add Invoice" CTA, not a menu
- KPI tiles say "You saved ₹X in ITC" not "X invoices processed"
- Month-end push: "Your April summary is ready — ₹12,400 in ITC"
- Status on each invoice is colour + icon (green ✓ / amber ⚠), no words
- Empty state on first login: "Connect your Gmail to start" full-screen
- Confirmation after upload: "We've saved this invoice ✓" tiny bottom toast, auto-dismiss
- Recent invoices as cards with thumbnail, not table rows

### 4.2 CA — patterns known to drive pro retention

| Pattern | Where seen | Why it works for CAs |
|---|---|---|
| Command palette (⌘K) | Linear, Raycast, Notion, GitHub | Power users navigate via keyboard, not clicks |
| Dense sortable grids | Airtable, Salesforce, Jira | More info per screen = less navigation overhead |
| Saved views / filters | GitHub issues, Linear | "Month-end readiness" view saved once, reused forever |
| Bulk select with shift-click | Gmail, Finder | N invoices actioned in one click, not N clicks |
| Keyboard-first shortcuts (j/k/a/r) | Superhuman, Gmail keyboard mode | Billable time saved; hands stay on keyboard |
| Toast > modal | Linear | Non-blocking; flow stays uninterrupted |
| Split-pane list/detail | Superhuman, Mail.app | List stays visible while reading one item |
| Audit log + export | Notion, Figma | Regulatory requirement for CAs |
| Status-at-a-glance colour strip | Datadog, AWS Health | Immediate triage signal |
| In-app search everywhere | Linear, GitHub | CA doesn't remember where something is; searches |
| Deadline banners | Stripe billing, GitHub Actions | Time-critical actions surfaced above the fold |

**Applied to our CA dashboard:**
- `⌘K` opens a command palette (client jump, action run, search across invoices)
- Client list is a dense sortable grid (12+ columns acceptable)
- "Month-end mode" = saved view with one-click toggle
- Shift-click multi-select on invoice queue → bulk approve / export / flag
- Keyboard shortcuts: `j/k` navigate, `a` approve, `r` reject, `f` flag, `e` edit, `/` search
- Approve confirmation is a bottom-right toast with undo, not a modal
- Invoice detail opens in right pane; list stays on left
- Audit log is a full-page export-ready table (no hiding it behind 3 clicks)
- Client colour strip on left of each row: green/amber/red
- Universal search bar in header, searches across all clients and invoices
- Red banner at top of dashboard: "3 days to GSTR-3B — 14 clients not filing-ready"

### 4.3 Shared — patterns for both

- **Instant feedback on every action** — no "please wait" without a progress indicator
- **Errors in plain language, not status codes**
- **Undo within N seconds** for any destructive action
- **Dark mode opt-in** (CA multi-monitor setups + evening SMB use both benefit)
- **Session continuity across devices** — refresh preserves filter / scroll state

---

## 5. Onboarding flow — with ingestion-source capture

### 5.1 Persona fork at registration

```
  ┌─────────────────────────────────┐
  │  Welcome                         │
  │  "I'm signing up as a..."        │
  │  [ Chartered Accountant / Firm ] │
  │  [ Business Owner ]              │
  │  Admin accounts out-of-band.     │
  └─────────┬───────────────────────┘
            │
       ┌────┴────┐
       ▼         ▼
    BUSINESS   CA
```

Role is written on the user row; cannot change without admin action.

### 5.2 Business path — 5 screens, mobile-first, < 2 minutes

1. **Phone + OTP**
2. **"What's your business called?"** (display name + optional GSTIN)
3. **"Connect a source — we'll import invoices automatically"**
   - [Connect Gmail] (OAuth button — stub OK)
   - [Connect Outlook] (OAuth button — stub OK)
   - [Connect WhatsApp] (phone number + dedicated forwarding number)
   - [Skip — I'll upload manually]
4. **"How do you want extraction to run?"** (default Instant, radio for Scheduled)
5. **Home dashboard** — empty state: "Waiting for your first invoice — we'll let you know when one arrives"

### 5.3 CA path — 6 screens, desktop-first

1. **Email + password**
2. **Firm info**: firm name, ICAI membership (optional, no validation),
   phone
3. **"How many clients do you serve?"** (rough — sets tier expectation)
4. **"Connect sources your firm receives invoices on"** — same source
   menu as business, possibly multiple Gmail accounts / multiple phone
   numbers
5. **"Default extraction mode"**: Scheduled (nightly) recommended for
   portfolio volume; Instant available on per-invoice basis
6. **Home dashboard** — empty state: "Your client list fills in as
   invoices arrive. Forward a test invoice to try."

### 5.4 Ingestion-source handshake — UI vs implementation split

- **UI layer (this branch, `platform/ingestion_handshakes/`)** —
  renders OAuth buttons, collects callback codes, stores connection
  state, shows "connected ✓ / disconnected ✗" per source on a settings
  page. Mock endpoints return stub success until the real connector
  arrives.
- **Implementation layer (`ingestion/*` branch)** — actual Gmail API /
  Graph API / WhatsApp Business polling. Wires into the same handshake
  UI when ready.

This matches your "demonstrable UI, independent folder" directive and
preserves the 3-branch governance we agreed on.

---

## 6. View architecture — two shells, one data layer, shared ingestion

```
            ┌─────────────────────┐
            │  Auth & session      │
            │  role = business|ca  │
            └──────────┬──────────┘
                       │
             ┌─────────┴──────────┐
             ▼                    ▼
      ┌───────────────┐    ┌──────────────────┐
      │ BUSINESS SHELL│    │ CA SHELL         │
      │ - dashboard    │    │ - portfolio dash │
      │ - inbox        │    │ - inbox          │
      │ - invoice pg   │    │ - clients grid   │
      │ - sources      │    │ - reconciliation │
      │ - settings     │    │ - export / Tally │
      │                │    │ - audit log      │
      │                │    │ - settings       │
      └───────┬───────┘    └────────┬─────────┘
              │                     │
              └─────────┬───────────┘
                        ▼
            ┌──────────────────────┐
            │ SHARED DATA LAYER     │
            │ (platform/db/)        │
            │ - users                │
            │ - workspaces           │
            │ - invoices             │
            │ - inbox_messages       │
            │ - sources              │
            │ - jobs                 │
            │ - events               │
            └───────────┬──────────┘
                        │ consumes
                        ▼
            ┌──────────────────────┐
            │ components/ pipeline  │
            │ (OCR → extract →     │
            │  tables → validate)  │
            │ UNCHANGED             │
            └──────────────────────┘
```

- Business shell and CA shell are **different routes, different
  templates, different JS bundles**. Not a conditional render.
- The **inbox viewer is shared in structure** but column set differs
  per persona (§3.1).
- The **data layer is one** — both personas query the same tables,
  filtered by `workspace_id`.
- The **components pipeline is untouched** — `platform/` imports from
  `components/*`, never the reverse.

---

## 7. Data model — conceptual (simplified, no CA↔SMB link)

### 7.1 Entities

```
  users                (role: business | ca | admin; independent accounts)
    │
    ├── owns ────►   workspaces            (one per user today; future: multi)
                           │
                           ├── has ─────►  sources          (gmail / outlook / wa / upload)
                           │                  │
                           │                  └── produces ► inbox_messages
                           │                                    │
                           │                                    └── may produce ► invoices
                           │                                                        │
                           │                                                        ├── jobs
                           │                                                        ├── extractions
                           │                                                        ├── table_rows
                           │                                                        └── validation_findings
                           └── has ─────►  events            (audit log, per-workspace)

  platform-level (admin, future)
    platform_metrics   (materialised)
    events             (cross-workspace, read-only for admin — no invoice content)
```

### 7.2 Key simplifications vs the earlier design

| Removed | Reason |
|---|---|
| `ca_client_links` table | CA "clients" now derived from invoice.client_gstin |
| Pending workspaces | No CA-invites-client flow |
| `workspace_members` (many-to-many user↔workspace) | One user, one workspace for v1 |
| Invite / claim lifecycle | Not needed |
| "on_behalf_of" audit field | Not needed; CA operates their own account only |

### 7.3 Inbox messages vs invoices — two tables, one relationship

`inbox_messages` captures *what arrived from a source* (an email, a
WhatsApp media item, an uploaded file). It carries source-layer
metadata: sender, subject, received-at, source type, source-specific
ids. It may or may not become an invoice.

`invoices` captures *what extraction produced* for messages that turned
out to be real invoices. Linked back to the originating
`inbox_message_id`.

This split matches the user's ask ("listify all invoices and messages
extracted from these respective sources with dates and metadata") and
lets the inbox viewer show items that are *queued but not yet extracted*
or *ignored as non-invoice*, which pure `invoices` rows can't represent.

### 7.4 Derived-client table (or view)

A CA's client dashboard is backed by:

```
  derived_clients_view := 
    SELECT client_gstin, 
           MIN(client_name)          AS display_name,
           COUNT(*)                   AS monthly_invoices,
           SUM(needs_review)          AS unreviewed,
           SUM(has_flag)              AS flag_count,
           SUM(gstr2b_mismatch)       AS mismatch_count,
           MAX(created_at)            AS last_activity
    FROM invoices
    WHERE workspace_id = :ca_workspace
    GROUP BY client_gstin
```

No new table required at v1. When CA wants to rename or merge clients,
we add `client_label_overrides (workspace_id, client_gstin,
display_name)` — ~5 columns, trivial migration.

### 7.5 Admin readiness (unchanged from prior plan)

- Events table is first-class; every meaningful action writes one row
- Workspace metadata rich at creation (`created_via`, `region`, `tier`)
- Admin DB role grants read only on `events` / `workspaces` / `users`,
  never on `invoices` — PII boundary enforced by RDBMS permissions

### 7.6 Storage tier

- **SQLite** for Slice 1 (single binary, zero infra)
- **Postgres** trigger: > 10 concurrent CA sessions OR > 100 workspaces
- Conceptual model is engine-agnostic

### 7.7 Pipeline cache migration

Today: `data/cache/pipeline_cache.jsonl` keyed by `invoice.id`.
Future: SQLite `pipeline_runs` keyed by `(workspace_id, invoice_id,
pipeline_version)`. Mechanical migration.

---

## 8. Pain-point → feature map

| Pain | Persona | Feature | Where |
|---|---|---|---|
| Invoices arrive everywhere (Gmail, WA, Outlook) | Both | Connected-sources with unified inbox | Onboarding + Inbox |
| Miss an invoice in chaos | Business | Status chip; push when new arrival | Dashboard + push |
| Receipts pile up | Business | "+Add Invoice" one-tap on home | Dashboard |
| Pay duplicate | Business | Validation duplicate-rule flag as amber card | Invoice detail |
| GST notice panic | Business | "All clear ✓"; plain language | Dashboard |
| Blocked ITC | Both | ITC-at-risk KPI tile; GSTR-2B reconciliation | Both dashboards |
| Context-switch across clients | CA | Client grid; ⌘K jump; client-scoped inbox filter | CA dashboard + inbox |
| Filing deadline | CA | Deadline banner; month-end mode; per-client filing-ready | CA dashboard |
| Audit trail | CA | Events table, exportable | CA audit log |
| Tally export | CA | CSV in Tally import format (exists) | CA export tab |
| Low literacy | Business | Icons > text; outcome-first copy; bottom sheets | Whole business shell |
| Time-poor | CA | Shortcuts, bulk ops, dense default, saved views | Whole CA shell |
| Wait for extraction | Both | Per-source + per-invoice mode toggle (instant / scheduled) | Inbox |
| Non-invoice attachments | Both | "Ignore" action + filter | Inbox |
| Admin visibility without PII | Admin | Events-only aggregate dashboard | Admin shell |

---

## 9. Journey maps

### 9.1 Business — Ramesh, hardware shop

- Onboarding (day 0): signs up on phone, connects Gmail, picks "Instant extraction." 90 seconds.
- Day 1, 10:42 AM: vendor emails invoice. Platform ingests via Gmail push, extracts in < 3 s.
- 10:43: Ramesh gets notification "1 new invoice processed." Opens app. Invoice card. Vendor + amount. [Yes, this is mine].
- Day 12: vendor resends (accidentally). Platform extracts, flags as potential duplicate. Push: "Duplicate check." Ramesh opens, sees side-by-side. "Different — keep both."
- Month-end: opens app. Dashboard: "April — ₹84,000 spent, ₹12,400 ITC saved, 34 invoices (all clear ✓)." Taps "Download April as CSV." Forwards to CA.

**Total: ~20 min/month, zero jargon.**

### 9.2 CA — Priya, solo, 32 clients-worth of invoices

- Onboarding (day 0): signs up desktop, connects 2 Gmail accounts (firm + personal) and 1 Outlook, picks "Scheduled" default.
- Day 1: client list empty. Forwards a test invoice — appears in inbox, extracts, dashboard shows 1 client, 1 invoice.
- Normal day: opens desktop. `⌘K` jump to "Acme Traders." Sees client page with unreviewed queue. `j/k` through, `a` to approve 8 invoices.
- GSTR-3B week: month-end mode banner up. Client grid sorts by needs-action. Works top-down. Uploads GSTR-2B JSON for reconciliation. Mismatches surface on the reconciliation tab. Fixes, flags, chases via WhatsApp link.
- Export: `⌘E` → Tally CSV for last month, all clients, grouped by voucher type.

**Total: ~4 hr/month for 32 clients' invoice volume.**

### 9.3 Admin — Vasu (platform owner)

- Weekly: opens admin dashboard. MAU / DAU split by role, signup funnel, top CAs by volume, extraction error rate, p50/p95 latency. No invoice contents.

---

## 10. Delivery shape — thin slices

### Slice 1 — "business only, manual upload, full dashboard stub"

Build:
- Auth + business signup (phone+OTP)
- Source-onboarding UI scaffolds (buttons + stubs; no real OAuth yet)
- Manual upload path end-to-end (reuse existing pipeline)
- Business dashboard (KPI tiles driven by real data, even if only upload source is live)
- Inbox viewer (upload source only; columns per §3.1)
- Invoice detail page (business variant)
- Settings (profile, sources page showing stubs)

Skip: CA shell, CA-specific dashboard, chat, real source connectors,
admin, scheduled extraction (all invoices extract instantly in Slice 1).

**Deliverable:** A business owner signs up on phone, uploads an
invoice, sees it extracted and validated, returns next day, it's still
there; connects a (stub) Gmail via onboarding; dashboard shows real KPI
numbers from their own uploads.

### Slice 2 — "CA shell + derived client list"

Build:
- CA signup path (desktop, email/password)
- CA dashboard (portfolio KPIs, derived client grid, no ⌘K yet)
- CA inbox variant (adds Client + Validation-flags columns)
- Invoice detail page (CA variant with full validation + audit trail)
- Events table wired through

Skip: bulk ops, ⌘K palette, month-end mode, GSTR-2B reconciliation UI,
chat.

**Deliverable:** A CA signs up, uploads a few invoices, sees portfolio
grouped by billed-to GSTIN, reviews each with full validation breakdown.

### Slice 3 — "CA power features"

Shortcuts (`j/k/a/r/f/e`), `⌘K` palette, bulk select, saved views,
month-end mode, audit log UI, Tally export selector.

### Slice 4 — "Real ingestion sources"

Integration turn: pull in the `ingestion/*` branch's Gmail / Outlook /
WhatsApp connectors; wire into the handshake UI stubs from Slice 1.
Scheduled vs instant extraction gets real when there's a non-manual
source.

### Slice 5 — "Reconciliation + Tally export polish"

GSTR-2B JSON upload + match view, ITC-at-risk calculations, Tally CSV
with full column coverage.

### Slice 6 — "Admin dashboard (read-only, metadata-only)"

Cheap because `events` has been accumulating since Slice 1.

### Slice 7 — "Chat (both personas)"

Business assistant (fixed-intent classifier) + CA copilot (NL-over-data
palette). Rule-based parser first; LLM-backed is a later cost decision.

---

## 11. Open questions — decisions still needed

1. **Workspace vs account cardinality** — for v1, 1 user = 1 workspace
   (confirmed by your "independent" framing). Future CA multi-workspace
   is a Slice 8+ concern. Confirm.
2. **Source credential storage** — encrypted-at-rest OAuth tokens in
   SQLite (cheap, fine for v1 single-box) vs a secrets manager (infra
   dependency, premature). Recommendation: SQLite + column-level
   encryption using a master key from env var.
3. **"Default extraction mode" — global setting or per-source?** —
   Recommendation: per-source (user may want Gmail scheduled but
   Uploads instant). Confirm.
4. **Client-display-name canonicalisation** — for CA derived clients
   from `client_gstin`, pick first-seen name vs most-frequent name vs
   latest name. Recommendation: most-frequent with CA override. Confirm.
5. **Month boundary** — calendar month (1st to end) vs GST month (file-
   specific). Recommendation: calendar month on dashboards; GST-month
   in reconciliation view.
6. **Inbox retention** — keep ignored / non-invoice rows forever or
   auto-purge after N days? Recommendation: keep 90 days, then soft-
   delete; training data stays.
7. **Admin account creation** — CLI / env var only, no self-service.
   Confirm.
8. **Frontend tech stack** — extend current vanilla HTML/JS `frontend/`
   OR introduce a lightweight framework (Alpine, HTMX, or plain Lit)
   for the denser CA grid? `project.md` §2.2 says no SPA frameworks.
   Recommendation: stick with vanilla + HTMX (server-rendered HTML
   fragments) — gives us dense interactivity without a build step.
9. **Mobile strategy for business** — responsive web (Slice 1–6), PWA
   install prompt (Slice 7), native app (out of scope). Confirm.
10. **Chat (Slice 7) parser** — rule-based-only vs LLM-backed vs both
    (rule-based for business, LLM for CA). Recommendation: both.

---

## 12. Critical files / locations (for the later implementation turn)

### New: `platform/` at repo root

```
platform/
├── README.md                  # this branch's deliverable overview
├── auth/                      # phone-OTP + email-password flows
├── onboarding/                # persona-fork, source-handshake stubs
├── ingestion_handshakes/      # OAuth UI scaffolds (stubs until ingestion branch lands)
├── inbox/                     # unified inbox viewer backend + routes
├── dashboard/
│   ├── business/              # business KPI / chart data providers
│   └── ca/                    # CA portfolio / derived-client data providers
├── workers/                   # scheduled-vs-instant extraction runner
├── db/                        # SQLite schema + migrations
└── tests/
```

`platform/` depends on `components/*`; never the reverse. Enforced by
CONTRACTS.md governance + an import-graph test.

### Existing to reuse (not modify)

- `components/*/types.py` — wire-format types; imported as-is
- `components/ocr`, `components/extraction`, `components/tables`,
  `components/validation` — pipeline, unchanged
- `backend/app/pipeline.py` — workspace-agnostic; reused by
  `platform/workers/`

### Existing to migrate (careful)

- `backend/app/cache.py` (JSONL) → `platform/db/pipeline_runs.py`
  (SQLite, keyed by `(workspace_id, invoice_id, pipeline_version)`)
- `backend/app/csv_export.py` → moves under `platform/dashboard/ca/`
  (CA-only feature)
- `frontend/static/index.html` + `app.js` + `style.css` — viewer
  primitives stay as a component library; re-consumed by both shells

### Existing to deprecate eventually (not this branch)

- Current `frontend/static/index.html` single-invoice viewer — becomes
  a special-case rendering inside the new Invoice Detail page, not a
  standalone app

---

## 13. Verification — how we know the design is right

This is design, not code. Verification is evaluative.

1. **Persona walkthrough** — step through Ramesh's (§9.1) and Priya's
   (§9.2) journey maps on paper/whiteboard. Target: business < 2 min
   to first invoice; CA < 4 hr/month for 32 clients' volume.
2. **Jargon audit** — count tax-specific words (GSTIN, ITC, CGST, HSN)
   on the business shell. If > 3 unique terms visible, simplify.
3. **Information-density audit** — count columns on CA client grid. If
   < 8, under-delivering to CA expectation.
4. **PII-boundary audit** — trace every admin dashboard query. If any
   touches `invoices.*`, data model has failed.
5. **Inbox coverage check** — can the inbox represent: (a) a queued
   upload, (b) an ignored PDF, (c) a failed-extract email, (d) an
   extracted WhatsApp photo? If any can't, `inbox_messages` table
   shape is wrong.
6. **Derived-client check** — can we render the CA client grid as a
   single SQL `GROUP BY client_gstin` over `invoices`? If yes, v1 data
   model correct. If any required column needs a join not in our
   schema, we missed a field.
7. **Source-independence check** — can a user disconnect a source
   without deleting their invoices? If yes, `sources` ← `inbox_messages`
   relationship is nullable. Required.
8. **Retention targets — paper** — can we write today the push / email
   cadence that would bring Ramesh back twice a month and Priya twice
   a week? If no, §4 UI patterns aren't yet wired into product
   mechanics.
9. **Future-admin readiness** — can we write today the SQL for Year-1
   admin dashboard (MAU, DAU by role, signup funnel, top-CAs-by-volume,
   error rate by stage)? If yes, ready.

---

## 14. Explicit non-goals for this branch

- Production auth (TOTP, SSO, SAML) — phone-OTP + email-password only
- CA↔SMB invite / link relationship — both independent, interconnected
  only via shared ingestion infra
- Billing / subscriptions — separate workstream, not in this branch
- Multi-language i18n for Slice 1 — English only; UI-pattern quality
  is the retention lever, not translation
- Chat system — deferred to Slice 7
- Real Gmail / Outlook / WhatsApp connectors — stubs here; implementation
  on `ingestion/*`
- LayoutLMv3 or extraction-quality work — lives on `main`
- Changes to the 5 frozen wire-format types — governed by CONTRACTS.md
- Native mobile apps — responsive web + later PWA prompt only
- Real WhatsApp Business API — deferred past Slice 7

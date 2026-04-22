/* ═══════════════════════════════════════════════════════════════════
 * Invoice Intelligence — frontend app
 *
 * One module-scope state object; the middle pane is a three-way state
 * machine (empty / loading / preview). Per-invoice KPIs, confidence
 * bars, grouped validation, and hover-to-bbox highlighting all read
 * from the same /api/invoices/{id} payload.
 * ═══════════════════════════════════════════════════════════════════ */

const state = {
    invoices: [],
    selectedId: null,
    payload: null,
    imageNatural: { width: 0, height: 0 },
};

/* Zoom + pan state for the invoice preview. Wheel zooms around the cursor;
 * drag pans. `scale` is multiplicative; `x` / `y` are pixel offsets applied
 * to the `#preview-container` via CSS transform (transform-origin 0 0). */
const zoomState = { scale: 1, x: 0, y: 0 };
const panState = { dragging: false, lastX: 0, lastY: 0 };

function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

const FIELD_ORDER = [
    "invoice_no",
    "invoice_date",
    "seller",
    "client",
    "seller_tax_id",
    "client_tax_id",
    "iban",
];

/* ─────────── DOM helpers ─────────── */

function $(sel, root = document) { return root.querySelector(sel); }
function $$(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === "className")      node.className = v;
        else if (k === "text")      node.textContent = v;
        else if (k === "html")      node.innerHTML = v;
        else if (k === "dataset")   Object.assign(node.dataset, v);
        else if (k === "on") {
            for (const [event, handler] of Object.entries(v)) node.addEventListener(event, handler);
        } else {
            node.setAttribute(k, v);
        }
    }
    for (const child of children.flat()) {
        if (child == null || child === false) continue;
        node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
}

function canon(s) {
    return (s ?? "").replace(/\s+/g, "").toLowerCase();
}

/* ─────────── API ─────────── */

async function apiListInvoices(split, limit) {
    const resp = await fetch(`/api/invoices?split=${encodeURIComponent(split)}&limit=${encodeURIComponent(limit)}`);
    if (!resp.ok) throw new Error(`List failed: ${resp.status}`);
    return resp.json();
}
async function apiGetInvoice(id) {
    const resp = await fetch(`/api/invoices/${encodeURIComponent(id)}`);
    if (!resp.ok) throw new Error(`Load failed: ${resp.status}`);
    return resp.json();
}

/* ─────────── middle-pane state machine ─────────── */

function showEmptyState() {
    $("#empty-state").hidden       = false;
    $("#loading-state").hidden     = true;
    $("#preview-container").hidden = true;
    $("#zoom-controls").hidden     = true;
    $("#right-empty").hidden       = false;
    $("#right-panels").hidden      = true;
}
function showLoadingState() {
    $("#empty-state").hidden       = true;
    $("#loading-state").hidden     = false;
    $("#preview-container").hidden = true;
    $("#zoom-controls").hidden     = true;
    $("#right-empty").hidden       = false;
    $("#right-panels").hidden      = true;
}
function showPreviewState() {
    $("#empty-state").hidden       = true;
    $("#loading-state").hidden     = true;
    $("#preview-container").hidden = false;
    $("#zoom-controls").hidden     = false;
    $("#right-empty").hidden       = true;
    $("#right-panels").hidden      = false;
}

/* ─────────── top-bar cache indicator ─────────── */

function updateCacheCount() {
    const total = state.invoices.length;
    const cached = state.invoices.filter((inv) => inv.cached).length;
    $("#cache-count-text").textContent = `${cached} / ${total} cached`;
    const dot = $("#cache-indicator");
    if (total === 0)           dot.style.background = "var(--slate-500)";
    else if (cached === 0)     dot.style.background = "var(--slate-500)";
    else if (cached < total)   dot.style.background = "var(--amber-500)";
    else                       dot.style.background = "var(--green-500)";
}

/* ─────────── invoice list ─────────── */

function renderInvoiceList(invoices) {
    const list = $("#invoice-list");
    list.innerHTML = "";
    if (!invoices.length) {
        list.append(el("li", { className: "invoice-placeholder", text: "No invoices." }));
        updateCacheCount();
        return;
    }
    // Cached invoices first (subtle green tint), then by index.
    const sorted = [...invoices].sort((a, b) => {
        if (a.cached !== b.cached) return a.cached ? -1 : 1;
        return (a.index ?? 0) - (b.index ?? 0);
    });
    for (const inv of sorted) {
        const idRow = el("span", { className: "invoice-id" }, inv.id);
        const metaRow = el(
            "span",
            { className: "invoice-meta" },
            `#${inv.invoice_no ?? "—"} · ${inv.invoice_date ?? "—"}`,
        );
        const li = el(
            "li",
            { dataset: { id: inv.id }, on: { click: () => selectInvoice(inv.id) } },
            idRow,
            metaRow,
        );
        if (inv.cached) li.classList.add("cached");
        if (state.selectedId === inv.id) li.classList.add("selected");
        list.append(li);
    }
    updateCacheCount();
}

async function loadInvoiceList() {
    const split = $("#split-select").value;
    const limit = Math.max(1, parseInt($("#limit-input").value, 10) || 10);
    try {
        const items = await apiListInvoices(split, limit);
        state.invoices = items;
        renderInvoiceList(items);
    } catch (err) {
        console.error(err);
        $("#invoice-list").innerHTML = "";
        $("#invoice-list").append(el("li", { className: "invoice-placeholder", text: `Error: ${err.message}` }));
    }
}

/* ─────────── invoice detail ─────────── */

async function selectInvoice(id) {
    state.selectedId = id;
    for (const li of $$(".invoice-list li")) {
        li.classList.toggle("selected", li.dataset.id === id);
    }

    showLoadingState();

    $("#download-csv").href  = `/api/invoices/${encodeURIComponent(id)}/export.csv`;
    $("#download-json").href = `/api/invoices/${encodeURIComponent(id)}`;

    try {
        const payload = await apiGetInvoice(id);
        // If the user clicked a different invoice while this one was still
        // loading, abandon this render — don't paint stale state.
        if (state.selectedId !== id) return;

        state.payload = payload;
        state.imageNatural = payload.page || { width: 0, height: 0 };

        // Wait for the image to actually finish downloading before swapping
        // out the loading state — otherwise the loader hides while the preview
        // pane briefly shows empty, then the image pops in.
        const img = $("#invoice-image");
        await new Promise((resolve) => {
            img.onload = () => resolve();
            img.onerror = () => resolve();
            img.src = `/api/invoices/${encodeURIComponent(id)}/image.png`;
        });
        if (state.selectedId !== id) return;

        // Reset zoom for the new invoice, then show the preview, THEN sync
        // the overlay — must be done in this order because clientWidth/Height
        // are 0 while the container is still `hidden` (display: none), and
        // a zero-sized SVG can never draw hover rectangles.
        zoomReset();
        showPreviewState();
        requestAnimationFrame(syncOverlaySize);

        renderKpis(payload);
        renderExtraction(payload.extraction);
        renderItems(payload.tables);
        renderValidation(payload.validation, payload);
        renderOcr(payload.ocr);

        // Refresh list so the green-tinted cached row appears after the first run.
        loadInvoiceList();
    } catch (err) {
        console.error(err);
        showEmptyState();
        state.payload = null;
        const placeholder = el("li", { className: "invoice-placeholder", text: `Error: ${err.message}` });
        $("#invoice-list").innerHTML = "";
        $("#invoice-list").append(placeholder);
    }
}

/* ─────────── KPI computation + rendering ─────────── */

function computeKpis(payload) {
    const fields = payload?.extraction?.fields ?? {};
    const gtHeader = payload?.ground_truth?.header ?? {};

    let extracted = 0;
    let accurate = 0;
    for (const name of FIELD_ORDER) {
        const pred = fields[name]?.value;
        const gt = gtHeader[name];
        if (pred != null && pred !== "") extracted += 1;
        if (pred != null && gt != null && canon(pred) === canon(gt)) accurate += 1;
    }

    const findings = payload?.validation?.findings ?? [];
    let pass = 0, fail = 0, na = 0;
    for (const f of findings) {
        if (f.outcome === "pass") pass += 1;
        else if (f.outcome === "fail") fail += 1;
        else na += 1;
    }

    const ocrMs = payload?.ocr?.duration_ms ?? 0;
    const extMs = payload?.extraction?.duration_ms ?? 0;
    const tblMs = payload?.tables?.duration_ms ?? 0;
    const totalMs = ocrMs + extMs + tblMs;

    return {
        extracted, totalFields: FIELD_ORDER.length,
        accurate,
        pass, fail, na,
        ocrMs, extMs, tblMs, totalMs,
    };
}

function renderKpis(payload) {
    const k = computeKpis(payload);

    $("#kpi-fields   .kpi-num").textContent = k.extracted;
    $("#kpi-accuracy .kpi-num").textContent = k.accurate;
    $("#kpi-pass").textContent = k.pass;
    $("#kpi-fail").textContent = k.fail;
    $("#kpi-na").textContent   = k.na;
    $("#kpi-latency  .kpi-num").textContent = Math.round(k.totalMs);

    // Multi-line tooltip: real newlines render as line breaks thanks to
    // CSS `white-space: pre` on the pseudo element.
    $("#kpi-latency").dataset.tooltip =
        `OCR:     ${Math.round(k.ocrMs)} ms\n` +
        `Extract: ${k.extMs.toFixed(1)} ms\n` +
        `Tables:  ${k.tblMs.toFixed(1)} ms`;
}

/* ─────────── overlay / hover-to-highlight ─────────── */

function clearOverlay() {
    const svg = $("#overlay");
    while (svg.firstChild) svg.removeChild(svg.firstChild);
}

function syncOverlaySize() {
    const img = $("#invoice-image");
    const svg = $("#overlay");
    if (!state.imageNatural.width || !state.imageNatural.height) return;
    svg.setAttribute("viewBox", `0 0 ${state.imageNatural.width} ${state.imageNatural.height}`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.style.width = img.clientWidth + "px";
    svg.style.height = img.clientHeight + "px";
}
window.addEventListener("resize", syncOverlaySize);

function drawBboxes(bboxes) {
    clearOverlay();
    if (!bboxes || !bboxes.length) return;
    const svg = $("#overlay");
    for (const b of bboxes) {
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", b.x0);
        rect.setAttribute("y", b.y0);
        rect.setAttribute("width", Math.max(0, b.x1 - b.x0));
        rect.setAttribute("height", Math.max(0, b.y1 - b.y0));
        svg.appendChild(rect);
    }
}

function findBboxesForValue(value) {
    if (value == null || !state.payload) return [];
    const target = canon(value);
    if (!target) return [];
    const found = [];
    for (const line of state.payload.ocr.lines) {
        const lineText = canon(line.text);
        if (!lineText) continue;
        if (lineText.includes(target) || target.includes(lineText)) {
            found.push(line.bbox);
        }
    }
    return found;
}

function attachHover(node, bboxSupplier) {
    node.addEventListener("mouseenter", () => drawBboxes(bboxSupplier()));
    node.addEventListener("mouseleave", clearOverlay);
    node.classList.add("hoverable");
}

/* ─────────── zoom + pan ─────────── */

function applyZoom() {
    const c = $("#preview-container");
    c.style.transform = `translate(${zoomState.x}px, ${zoomState.y}px) scale(${zoomState.scale})`;
    const lbl = $("#zoom-label");
    if (lbl) lbl.textContent = `${Math.round(zoomState.scale * 100)}%`;
}

function zoomReset() {
    zoomState.scale = 1;
    zoomState.x = 0;
    zoomState.y = 0;
    applyZoom();
}

/* Zoom around a point (mx, my) where the cursor sits relative to the
 * `#preview-container`'s visible top-left. Using the standard
 * "point-under-cursor stays put" formula:
 *     new_tx = old_tx + mx * (1 - new_scale / old_scale) */
function zoomAround(mx, my, newScale) {
    newScale = clamp(newScale, 0.3, 8);
    const oldScale = zoomState.scale;
    if (newScale === oldScale) return;
    const r = newScale / oldScale;
    zoomState.x += mx * (1 - r);
    zoomState.y += my * (1 - r);
    zoomState.scale = newScale;
    applyZoom();
}

function onPreviewWheel(e) {
    if ($("#preview-container").hidden) return;
    e.preventDefault();
    const rect = $("#preview-container").getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    // Exponential zoom curve — feels smoother than a fixed step per notch.
    const factor = Math.exp(-e.deltaY * 0.0015);
    zoomAround(mx, my, zoomState.scale * factor);
}

function onPanStart(e) {
    if (e.button !== 0) return;                        // left button only
    if ($("#preview-container").hidden) return;
    panState.dragging = true;
    panState.lastX = e.clientX;
    panState.lastY = e.clientY;
    $("#preview-container").classList.add("panning");
    e.preventDefault();
}
function onPanMove(e) {
    if (!panState.dragging) return;
    const dx = e.clientX - panState.lastX;
    const dy = e.clientY - panState.lastY;
    panState.lastX = e.clientX;
    panState.lastY = e.clientY;
    zoomState.x += dx;
    zoomState.y += dy;
    applyZoom();
}
function onPanEnd() {
    if (!panState.dragging) return;
    panState.dragging = false;
    $("#preview-container").classList.remove("panning");
}

/* Zoom-in / zoom-out buttons — zoom around the preview's centre. */
function zoomByButton(factor) {
    const rect = $("#preview-container").getBoundingClientRect();
    zoomAround(rect.width / 2, rect.height / 2, zoomState.scale * factor);
}

/* ─────────── extraction panel ─────────── */

function confTier(conf) {
    if (conf == null || conf === 0) return "conf-none";
    if (conf >= 0.85) return "conf-high";
    if (conf >= 0.60) return "conf-mid";
    return "conf-low";
}

function renderExtraction(extraction) {
    const tbody = $("#extraction-table tbody");
    tbody.innerHTML = "";
    if (!extraction || !extraction.fields) return;

    for (const name of FIELD_ORDER) {
        const field = extraction.fields[name];
        if (!field) continue;
        const value = field.value;

        const nameCell = el("td", { text: name });
        const valueCell = el("td", { text: value ?? "—" });

        const row = el("tr", {}, nameCell, valueCell);
        if (value) attachHover(row, () => findBboxesForValue(value));
        tbody.append(row);
    }
}

/* ─────────── items panel ─────────── */

function renderItems(tables) {
    const tbody = $("#items-table tbody");
    tbody.innerHTML = "";
    const items = tables?.items ?? [];
    $("#items-count").textContent = items.length;

    const cols = ["item_desc", "item_qty", "item_net_price", "item_net_worth", "item_vat", "item_gross_worth"];
    items.forEach((item, idx) => {
        const tds = [el("td", { text: String(idx + 1) })];
        for (const col of cols) {
            const value = item[col];
            const td = el("td", { text: value ?? "—" });
            if (value) attachHover(td, () => findBboxesForValue(value));
            tds.push(td);
        }
        tbody.append(el("tr", {}, ...tds));
    });
}

/* ─────────── validation panel (grouped) ─────────── */

/* Client-side "is the extracted value the same as the katanaml ground
 * truth?" check. Emits one finding per header field shaped like the
 * server-side `RuleFinding`s so they drop into the same grouped UI.
 *
 * Why here, not in the backend: the server's ValidationEngine checks
 * format / checksum / arithmetic — those stay true in production, where
 * there is no ground truth. Accuracy-vs-GT is only meaningful on labelled
 * data and therefore lives in the viewer. */
function computeAccuracyFindings(payload) {
    const fields = payload?.extraction?.fields ?? {};
    const gt = payload?.ground_truth?.header ?? {};
    const out = [];
    for (const name of FIELD_ORDER) {
        const predVal = fields[name]?.value ?? null;
        const gtVal   = gt[name] ?? null;

        if (gtVal == null && predVal == null) {
            out.push({
                rule_name: "accuracy_vs_gt",
                target: name,
                outcome: "not_applicable",
                reason: "no ground truth and no extraction",
                expected: null, observed: null,
            });
        } else if (gtVal == null) {
            out.push({
                rule_name: "accuracy_vs_gt",
                target: name,
                outcome: "not_applicable",
                reason: "ground truth missing",
                expected: null, observed: predVal,
            });
        } else if (predVal == null) {
            out.push({
                rule_name: "accuracy_vs_gt",
                target: name,
                outcome: "fail",
                reason: "field not extracted",
                expected: gtVal, observed: null,
            });
        } else if (canon(predVal) === canon(gtVal)) {
            out.push({
                rule_name: "accuracy_vs_gt",
                target: name,
                outcome: "pass",
                reason: null,
                expected: gtVal, observed: predVal,
            });
        } else {
            out.push({
                rule_name: "accuracy_vs_gt",
                target: name,
                outcome: "fail",
                reason: "value differs from ground truth",
                expected: gtVal, observed: predVal,
            });
        }
    }
    return out;
}

function renderValidation(validation, payload) {
    const container = $("#validation-groups");
    container.innerHTML = "";

    // Server-side (intrinsic) findings first, client-side accuracy findings second.
    const serverFindings = validation?.findings ?? [];
    const accuracyFindings = computeAccuracyFindings(payload);
    const findings = [...serverFindings, ...accuracyFindings];

    const groups = { fail: [], pass: [], not_applicable: [] };
    for (const f of findings) {
        (groups[f.outcome] ?? groups.not_applicable).push(f);
    }

    container.append(buildValidationGroup("Fail",           groups.fail,           "validation-group-fail", true));
    container.append(buildValidationGroup("Pass",           groups.pass,           "validation-group-pass", false));
    if (groups.not_applicable.length) {
        container.append(buildValidationGroup("Not applicable", groups.not_applicable, "validation-group-na", false));
    }
}

function buildValidationGroup(label, findings, groupClass, open) {
    const summary = el(
        "summary",
        {},
        el("span", { text: label }),
        el("span", { className: "vg-count", text: String(findings.length) }),
    );
    const ul = el("ul", { className: "validation-list" });
    if (findings.length === 0) {
        ul.append(el("li", { className: "rule-empty", text: `No ${label.toLowerCase()} findings.` }));
    } else {
        for (const f of findings) {
            const ruleLine = el(
                "div",
                {},
                el("span", { className: "rule-name", text: f.rule_name }),
                el("span", { className: "rule-target", text: f.target }),
            );
            const li = el("li", {}, ruleLine);
            if (f.reason) {
                li.append(el("span", { className: "rule-reason", text: f.reason }));
            }
            // Accuracy + arithmetic failures carry `expected` / `observed` —
            // surface them so the viewer sees exactly what differs.
            const parts = [];
            if (f.expected != null && String(f.expected).length)
                parts.push(`expected: ${f.expected}`);
            if (f.observed != null && String(f.observed).length)
                parts.push(`got: ${f.observed}`);
            if (parts.length) {
                li.append(el("span", { className: "rule-values", text: parts.join("   ·   ") }));
            }
            ul.append(li);
        }
    }
    const details = el("details", { className: `validation-group ${groupClass}` }, summary, ul);
    if (open) details.setAttribute("open", "");
    return details;
}

/* ─────────── OCR panel ─────────── */

function renderOcr(ocr) {
    const list = $("#ocr-list");
    list.innerHTML = "";
    const lines = ocr?.lines ?? [];
    $("#ocr-count").textContent = lines.length;

    lines.forEach((line) => {
        const confSpan = el("span", { className: "conf", text: `${Math.round(line.confidence * 100)}%` });
        const li = el("li", {}, confSpan, line.text);
        attachHover(li, () => [line.bbox]);
        list.append(li);
    });
}

/* ─────────── init ─────────── */

function wireUp() {
    $("#reload-btn").addEventListener("click", loadInvoiceList);
    $("#split-select").addEventListener("change", loadInvoiceList);
    $("#limit-input").addEventListener("change", loadInvoiceList);

    // Zoom + pan. Wheel is attached to the whole preview pane so it fires
    // whether the cursor is over the image, empty margin, or zoom controls.
    // Mousedown starts a pan only when it hits the preview-container itself
    // (clicks on zoom-controls buttons don't pan because they have their own
    // handlers and are outside preview-container).
    $("#preview").addEventListener("wheel", onPreviewWheel, { passive: false });
    $("#preview-container").addEventListener("mousedown", onPanStart);
    window.addEventListener("mousemove", onPanMove);
    window.addEventListener("mouseup", onPanEnd);
    window.addEventListener("mouseleave", onPanEnd);

    $("#zoom-in-btn").addEventListener("click",  () => zoomByButton(1.25));
    $("#zoom-out-btn").addEventListener("click", () => zoomByButton(1 / 1.25));
    $("#zoom-reset-btn").addEventListener("click", zoomReset);
}

document.addEventListener("DOMContentLoaded", () => {
    showEmptyState();
    wireUp();
    loadInvoiceList();
});

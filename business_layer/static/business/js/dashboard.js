// Dashboard — live KPI tiles + top vendors + needs-review + upload card.

(function (global) {
    'use strict';

    const MONTH_NAMES = [
        'January','February','March','April','May','June',
        'July','August','September','October','November','December',
    ];

    function fmtAmount(minor, currency) {
        if (minor == null) return '—';
        const whole = (minor / 100).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return (currency === 'INR' ? '₹' : (currency + ' ')) + whole;
    }

    function fmtCount(n) {
        return n == null ? '—' : String(n);
    }

    function showError(root, msg) {
        const el = root.querySelector('[data-role="error"]');
        if (!el) return;
        if (msg) { el.textContent = msg; el.hidden = false; }
        else { el.textContent = ''; el.hidden = true; }
    }

    function showStatus(root, msg) {
        const el = root.querySelector('[data-role="upload-status"]');
        if (!el) return;
        if (msg) { el.textContent = msg; el.hidden = false; }
        else { el.textContent = ''; el.hidden = true; }
    }

    async function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        const rows = document.cookie.split('; ');
        let csrf = '';
        for (const r of rows) {
            const [k, ...v] = r.split('=');
            if (k === 'bl_csrf') { csrf = decodeURIComponent(v.join('=')); break; }
        }
        const res = await fetch('/api/upload', {
            method: 'POST',
            credentials: 'include',
            headers: csrf ? { 'X-CSRF-Token': csrf } : {},
            body: formData,
        });
        const text = await res.text();
        let payload = null;
        try { payload = JSON.parse(text); } catch (_) { /* ignore */ }
        if (!res.ok) {
            const err = new Error((payload && payload.detail) || res.statusText);
            err.status = res.status;
            err.code = payload && payload.code;
            err.detail = payload && payload.detail;
            throw err;
        }
        return payload;
    }

    function renderTiles(root, payload) {
        const t = payload.tiles;
        const cur = payload.currency;
        root.querySelector('[data-role="kpi-count"]').textContent = fmtCount(t.invoices_this_month);
        root.querySelector('[data-role="kpi-spend"]').textContent = fmtAmount(t.total_spend_minor, cur);
        root.querySelector('[data-role="kpi-itc"]').textContent = fmtAmount(t.itc_estimate_minor, cur);
        root.querySelector('[data-role="kpi-review"]').textContent = fmtCount(t.needs_review_count);

        const period = root.querySelector('[data-role="period"]');
        if (period) {
            period.textContent = MONTH_NAMES[payload.period_month - 1] + ' ' + payload.period_year;
        }
    }

    function renderTopVendors(root, vendors, currency) {
        const wrap = root.querySelector('[data-role="top-vendors-wrap"]');
        const list = root.querySelector('[data-role="top-vendors-list"]');
        if (!vendors || vendors.length === 0) { wrap.hidden = true; return; }
        wrap.hidden = false;
        list.replaceChildren();
        for (const v of vendors) {
            const li = document.createElement('li');
            const name = document.createElement('span');
            name.className = 'vendor-name';
            name.textContent = v.vendor_name;
            const amount = document.createElement('span');
            amount.className = 'vendor-amount';
            amount.textContent = fmtAmount(v.total_minor, currency);
            const meta = document.createElement('span');
            meta.className = 'vendor-meta';
            meta.textContent = v.invoice_count + (v.invoice_count === 1 ? ' invoice' : ' invoices');
            li.appendChild(name); li.appendChild(amount); li.appendChild(meta);
            list.appendChild(li);
        }
    }

    function renderNeedsReview(root, items, currency) {
        const wrap = root.querySelector('[data-role="needs-review-wrap"]');
        const list = root.querySelector('[data-role="needs-review-list"]');
        if (!items || items.length === 0) { wrap.hidden = true; return; }
        wrap.hidden = false;
        list.replaceChildren();
        for (const it of items) {
            const li = document.createElement('li');
            li.addEventListener('click', () => {
                window.location.hash = '#/invoice/' + encodeURIComponent(it.invoice_id);
            });

            const vendor = document.createElement('span');
            vendor.className = 'review-vendor';
            vendor.textContent = it.vendor_name || '(vendor pending)';

            const amount = document.createElement('span');
            amount.className = 'review-amount';
            amount.textContent = fmtAmount(it.total_minor, currency);

            const meta = document.createElement('span');
            meta.className = 'review-meta';
            const bits = [];
            if (it.invoice_no) bits.push(it.invoice_no);
            if (it.invoice_date) bits.push(it.invoice_date);
            const fails = document.createElement('span');
            fails.className = 'review-fail-count';
            fails.textContent = it.failing_rules + (it.failing_rules === 1 ? ' issue' : ' issues');
            meta.textContent = bits.join(' · ') + (bits.length ? ' · ' : '');
            meta.appendChild(fails);

            li.appendChild(vendor); li.appendChild(amount); li.appendChild(meta);
            list.appendChild(li);
        }
    }

    async function loadKpis(root) {
        let payload;
        try {
            payload = await window.api.get('/api/business/dashboard');
        } catch (_) {
            // Dashboard still renders without KPIs — silently degrade.
            return;
        }
        renderTiles(root, payload);
        renderTopVendors(root, payload.top_vendors, payload.currency);
        renderNeedsReview(root, payload.needs_review, payload.currency);
    }

    function renderCaLinkState(root, session) {
        const unlinkedBox = root.querySelector('[data-role="ca-link-unlinked"]');
        const linkedBox = root.querySelector('[data-role="ca-link-linked"]');
        const errEl = root.querySelector('[data-role="ca-link-error"]');
        const form = root.querySelector('#form-ca-link');
        const unlinkBtn = root.querySelector('[data-role="ca-unlink-btn"]');
        const nameEl = root.querySelector('[data-role="ca-link-name"]');
        const gstinEl = root.querySelector('[data-role="ca-link-gstin"]');

        function showLinked(caGstin, caName) {
            linkedBox.hidden = false;
            unlinkedBox.hidden = true;
            gstinEl.textContent = caGstin || '';
            nameEl.textContent = caName || 'your CA firm';
            errEl.hidden = true;
        }
        function showUnlinked() {
            linkedBox.hidden = true;
            unlinkedBox.hidden = false;
            errEl.hidden = true;
        }

        // /api/auth/me already includes the workspace; we stored ca_gstin there? No —
        // the session response currently doesn't carry it. Fetch fresh here.
        // Lightweight: piggy-back on the dashboard response which has the workspace.
        // For v1 we just read ca_gstin via a quick /api/auth/me call.
        (async () => {
            try {
                const me = await window.api.get('/api/auth/me');
                const gst = me && me.workspace && me.workspace.ca_gstin;
                if (gst) showLinked(gst, null);
                else showUnlinked();
            } catch (_) {
                showUnlinked();
            }
        })();

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            errEl.hidden = true;
            const val = form.elements['ca_gstin'].value.trim().toUpperCase();
            try {
                const r = await window.api.post('/api/business/ca-link', { ca_gstin: val });
                showLinked(r.ca_gstin, r.ca_name);
            } catch (err) {
                let msg = err.detail || 'Could not link.';
                if (err.status === 404) msg = 'No CA is registered with that GSTIN yet.';
                if (err.code === 'business_rule_violated') msg = err.detail;
                errEl.textContent = msg;
                errEl.hidden = false;
            }
        });

        unlinkBtn.addEventListener('click', async () => {
            try { await window.api.del('/api/business/ca-link'); } catch (_) {}
            showUnlinked();
        });
    }

    function render(root, session) {
        const tpl = document.getElementById('view-dashboard');
        const clone = tpl.content.cloneNode(true);
        const h1 = clone.querySelector('[data-role="greeting"]');
        if (session && session.workspace && session.workspace.name) {
            h1.textContent = 'Hi, ' + session.workspace.name;
        }
        root.replaceChildren(clone);

        // Wire upload form.
        const form = root.querySelector('#form-upload');
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            showError(root, null);
            showStatus(root, null);
            const file = form.elements['file'].files[0];
            if (!file) return;
            const btn = form.querySelector('button.primary');
            btn.disabled = true;
            showStatus(root, 'Uploading…');
            try {
                const result = await uploadFile(file);
                window.location.hash = '#/invoice/' + encodeURIComponent(result.invoice_id);
            } catch (err) {
                let msg = err.detail || 'Upload failed. Try again.';
                if (err.status === 413 || err.code === 'validation_failed') {
                    msg = err.detail || 'This file is too large or not supported.';
                }
                showError(root, msg);
                showStatus(root, null);
            } finally {
                btn.disabled = false;
                form.reset();
            }
        });

        // Fire-and-forget KPI load so the dashboard appears immediately
        // and tiles populate as soon as the API returns.
        loadKpis(root);
        renderCaLinkState(root, session);
        renderSourcesState(root);
        maybeShowGmailCallbackToast();
    }

    function maybeShowGmailCallbackToast() {
        // When the OAuth callback redirects back to us it appends
        // ?gmail=connected or ?gmail=denied as a query-like token after
        // the hash. Surface that as an inline hint on the sources card.
        const marker = (window.location.search || '').match(/gmail=(connected|denied)/);
        if (!marker) return;
        // Clean up the URL so a refresh doesn't re-show the toast.
        history.replaceState(null, '', window.location.pathname + window.location.hash);
    }

    async function renderSourcesState(root) {
        const btn = root.querySelector('#btn-connect-email');
        const hint = root.querySelector('[data-role="gmail-connected-hint"]');
        const disconnectBtn = root.querySelector('[data-role="gmail-disconnect"]');
        if (!btn) return;

        let sources = [];
        try {
            const resp = await window.api.get('/api/sources');
            sources = resp.items || [];
        } catch (_) { /* show default state */ }
        const gmail = sources.find((s) => s.kind === 'gmail');

        if (gmail && gmail.status === 'connected') {
            btn.hidden = true;
            hint.hidden = false;
        } else {
            btn.hidden = false;
            hint.hidden = true;
        }

        disconnectBtn.addEventListener('click', async () => {
            try { await window.api.post('/api/oauth/google/disconnect', {}); }
            catch (_) { /* idempotent */ }
            btn.hidden = false;
            hint.hidden = true;
        });
    }

    global.dashboard = { render };
})(window);

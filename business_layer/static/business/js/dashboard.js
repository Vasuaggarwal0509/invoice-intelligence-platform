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
        return await window.api.postFormData('/api/upload', formData);
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

        const strip = root.querySelector('[data-role="status-strip"]');
        if (strip) {
            const ex = t.extracted_count || 0;
            const pe = t.pending_count || 0;
            const rv = t.needs_review_count || 0;
            root.querySelector('[data-role="status-extracted"]').textContent = ex;
            root.querySelector('[data-role="status-pending"]').textContent = pe;
            root.querySelector('[data-role="status-review"]').textContent = rv;
            // Hide entirely when there's nothing to break down — no point
            // showing three zeros under empty tiles.
            strip.hidden = (ex + pe + rv) === 0;
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

    async function loadKpis(root, period) {
        const qs = period && period !== 'this_month' ? '?period=' + encodeURIComponent(period) : '';
        let payload;
        try {
            payload = await window.api.get('/api/business/dashboard' + qs);
        } catch (_) {
            // Dashboard still renders without KPIs — silently degrade.
            return;
        }
        renderTiles(root, payload);
        renderTopVendors(root, payload.top_vendors, payload.currency);
        renderNeedsReview(root, payload.needs_review, payload.currency);
    }

    function wirePeriodSwitch(root) {
        const btnThis = root.querySelector('[data-role="period-this"]');
        const btnLast = root.querySelector('[data-role="period-last"]');
        if (!btnThis || !btnLast) return;
        function activate(which) {
            btnThis.classList.toggle('is-active', which === 'this');
            btnLast.classList.toggle('is-active', which === 'last');
            loadKpis(root, which === 'last' ? 'last_month' : 'this_month');
        }
        btnThis.addEventListener('click', () => activate('this'));
        btnLast.addEventListener('click', () => activate('last'));
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
                if (gst) {
                    showLinked(gst, null);
                    // Already linked — clear any pending invite so a
                    // refresh doesn't re-prompt.
                    try { window.localStorage.removeItem('pending_ca_invite'); }
                    catch (_) {}
                } else {
                    showUnlinked();
                    // Pre-fill the form from the invite link, if any.
                    let pending = null;
                    try { pending = window.localStorage.getItem('pending_ca_invite'); }
                    catch (_) {}
                    if (pending) {
                        form.elements['ca_gstin'].value = pending;
                        // Soft hint above the form so the user knows
                        // why the field is pre-populated.
                        let hint = unlinkedBox.querySelector('.invite-hint');
                        if (!hint) {
                            hint = document.createElement('p');
                            hint.className = 'muted small invite-hint';
                            hint.textContent = 'Your CA invited you to link with them. Confirm the GSTIN below and click Link CA.';
                            unlinkedBox.insertBefore(hint, form);
                        }
                        // Scroll the card into view.
                        unlinkedBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }
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
                try { window.localStorage.removeItem('pending_ca_invite'); }
                catch (_) {}
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
        loadKpis(root, 'this_month');
        wirePeriodSwitch(root);
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
        const fetchNowBtn = root.querySelector('[data-role="gmail-fetch-now"]');
        const fetchStatusEl = root.querySelector('[data-role="gmail-fetch-status"]');
        const accountLabelEl = root.querySelector('[data-role="gmail-account-label"]');
        const fetchSpinner = root.querySelector('[data-role="gmail-fetch-spinner"]');
        const fetchLabel = root.querySelector('[data-role="gmail-fetch-label"]');
        const connectSpinner = root.querySelector('[data-role="connect-spinner"]');
        const connectLabel = root.querySelector('[data-role="connect-label"]');
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
            // Render the connected account label (e.g., "Gmail · vasu@gmail.com").
            if (accountLabelEl) {
                accountLabelEl.textContent = gmail.label || 'Gmail';
            }
        } else {
            btn.hidden = false;
            hint.hidden = true;
        }

        // Connect-Email click: show spinner + flip label to "Redirecting…"
        // for visual feedback while the browser navigates to Google.
        // Browser navigation will replace this UI within a second; the
        // change is just to avoid a "did my click work?" moment.
        btn.addEventListener('click', () => {
            if (connectSpinner) connectSpinner.hidden = false;
            if (connectLabel) connectLabel.textContent = 'Redirecting to Google…';
        });

        disconnectBtn.addEventListener('click', async () => {
            try { await window.api.post('/api/oauth/google/disconnect', {}); }
            catch (_) { /* idempotent */ }
            btn.hidden = false;
            hint.hidden = true;
        });

        function setFetchStatus(text, klass) {
            fetchStatusEl.textContent = text;
            fetchStatusEl.className = 'fetch-status ' + klass;
            fetchStatusEl.hidden = !text;
        }
        function setFetchBusy(busy) {
            if (fetchSpinner) fetchSpinner.hidden = !busy;
            if (fetchLabel) fetchLabel.textContent = busy ? 'Fetching…' : 'Fetch now';
            fetchNowBtn.disabled = busy;
        }

        fetchNowBtn.addEventListener('click', async () => {
            // Diagnostic logs — visible in browser DevTools → Console.
            // If the user reports "Fetch now does nothing", the first
            // line tells us whether the handler even fired.
            console.log('[fetch-now] click handler entered');
            setFetchBusy(true);
            setFetchStatus('Reaching out to Gmail — this can take a few seconds…', 'empty');
            try {
                console.log('[fetch-now] POST /api/oauth/google/fetch-now …');
                const stats = await window.api.post('/api/oauth/google/fetch-now', {});
                console.log('[fetch-now] response:', stats);
                const ing = stats.attachments_ingested || 0;
                const sk = stats.attachments_skipped || 0;
                const sc = stats.messages_scanned || 0;
                if (stats.marked_disconnected) {
                    setFetchStatus(
                        'Gmail says the connection was revoked. Reconnect to continue.',
                        'error'
                    );
                    btn.hidden = false;
                    hint.hidden = true;
                } else if (ing > 0) {
                    setFetchStatus(
                        `Fetched ${ing} new invoice${ing === 1 ? '' : 's'} (${sc} message${sc === 1 ? '' : 's'} scanned). Refreshing the dashboard…`,
                        'success'
                    );
                    // Reload after a moment so the new invoices show up
                    // in tiles + Inbox + needs-review.
                    setTimeout(() => window.location.reload(), 1800);
                } else if (sc === 0) {
                    // Genuine empty result: Gmail had nothing matching the
                    // subject keyword filter at all.
                    setFetchStatus(
                        'No matching emails in your Gmail right now. (We auto-check every 15 min in the background too.)',
                        'empty'
                    );
                } else {
                    // sc > 0 but ing === 0 — every match was already in
                    // the inbox, almost always because the background
                    // poller picked them up first. This is success, not
                    // failure: the user IS already up to date.
                    setFetchStatus(
                        `Your inbox is already up to date — ${sc} matching message${sc === 1 ? '' : 's'} checked, all already imported. Open the Inbox tab to see them.`,
                        'success'
                    );
                }
            } catch (err) {
                // Surface to the console so silent failures don't
                // disappear, even if the user-facing status text is
                // also set below.
                console.error('[fetch-now] error:', err);
                // Server-side already produces helpful messages for the
                // common Gmail-API-not-enabled / 403 / 429 cases — just
                // surface what came back. Fall back to a generic.
                let msg = err.detail || 'Fetch failed. Check the server logs.';
                if (err.status === 404) msg = 'No connected Gmail account on this workspace.';
                if (err.status === 401) msg = 'Your session expired — please sign in again.';
                setFetchStatus(msg, 'error');
            } finally {
                setFetchBusy(false);
                console.log('[fetch-now] click handler done');
            }
        });
    }

    global.dashboard = { render };
})(window);

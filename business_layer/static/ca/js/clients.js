// CA clients list + per-client invoice list.

(function (global) {
    'use strict';

    function fmtAmount(minor, currency) {
        if (minor == null) return '—';
        const whole = (minor / 100).toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        });
        const symbol = currency === 'INR' ? '₹' : (currency ? currency + ' ' : '');
        return symbol + whole;
    }

    /** Populate the no-clients-yet block with the CA's GSTIN + a
     *  shareable invite link, plus copy-to-clipboard buttons.
     *
     *  The invite link points at /business?ca=<GSTIN> — the business
     *  shell reads that query param on boot and pre-fills the "Link
     *  your CA" form on the dashboard.
     */
    async function renderEmptyInvite(root, inviteBlock) {
        let me;
        try { me = await window.api.get('/api/auth/me'); }
        catch (_) { /* no session — let the router handle it */ return; }
        const gstin = (me && me.workspace && me.workspace.gstin) || '';
        const origin = window.location.origin;
        const inviteUrl = origin + '/static/business/index.html?ca=' + encodeURIComponent(gstin);

        const gstinEl = inviteBlock.querySelector('[data-role="invite-gstin"]');
        const linkEl = inviteBlock.querySelector('[data-role="invite-link"]');
        const toast = inviteBlock.querySelector('[data-role="copy-toast"]');
        const copyGstinBtn = inviteBlock.querySelector('[data-role="copy-gstin"]');
        const copyLinkBtn = inviteBlock.querySelector('[data-role="copy-link"]');

        gstinEl.textContent = gstin || '(no GSTIN on your workspace)';
        linkEl.textContent = inviteUrl;
        inviteBlock.hidden = false;

        function flashCopied() {
            toast.hidden = false;
            setTimeout(() => { toast.hidden = true; }, 1800);
        }
        async function copyText(text) {
            try { await navigator.clipboard.writeText(text); flashCopied(); }
            catch (_) {
                // Clipboard API requires a secure context (HTTPS or
                // localhost). Fall back to a select-and-execCommand
                // for older browsers / mixed contexts.
                const ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                try { document.execCommand('copy'); flashCopied(); }
                catch (_e) { /* give up silently */ }
                document.body.removeChild(ta);
            }
        }
        copyGstinBtn.addEventListener('click', () => copyText(gstin));
        copyLinkBtn.addEventListener('click', () => copyText(inviteUrl));
    }

    function renderRollup(root, items) {
        const wrap = root.querySelector('[data-role="ca-rollup"]');
        if (!wrap) return;
        if (!items || items.length === 0) { wrap.hidden = true; return; }
        const totals = items.reduce((acc, c) => {
            acc.invoices += (c.invoice_count || 0);
            acc.spend += (c.total_spend_minor || 0);
            acc.flags += (c.open_flags || 0);
            return acc;
        }, { invoices: 0, spend: 0, flags: 0 });
        root.querySelector('[data-role="rollup-clients"]').textContent = String(items.length);
        root.querySelector('[data-role="rollup-invoices"]').textContent = String(totals.invoices);
        root.querySelector('[data-role="rollup-spend"]').textContent = fmtAmount(totals.spend, 'INR');
        root.querySelector('[data-role="rollup-flags"]').textContent = String(totals.flags);
        wrap.hidden = false;
    }

    async function renderClients(root) {
        const tpl = document.getElementById('view-clients');
        root.replaceChildren(tpl.content.cloneNode(true));
        const list = root.querySelector('[data-role="client-list"]');
        const inviteBlock = root.querySelector('[data-role="empty-invite"]');

        let payload;
        try { payload = await window.api.get('/api/ca/clients'); }
        catch (err) {
            inviteBlock.hidden = false;
            inviteBlock.querySelector('p').textContent =
                err.detail || 'Could not load clients.';
            return;
        }
        if (!payload.items || payload.items.length === 0) {
            await renderEmptyInvite(root, inviteBlock);
            return;
        }
        inviteBlock.hidden = true;
        renderRollup(root, payload.items);
        for (const c of payload.items) {
            const li = document.createElement('li');
            li.addEventListener('click', () => {
                window.location.hash = '#/clients/' + encodeURIComponent(c.workspace_id);
            });

            const name = document.createElement('span');
            name.className = 'client-name';
            name.textContent = c.name;

            const amount = document.createElement('span');
            amount.className = 'client-amount';
            amount.textContent = fmtAmount(c.total_spend_minor, 'INR');

            const gstin = document.createElement('span');
            gstin.className = 'client-gstin';
            gstin.textContent = c.gstin || '(no GSTIN)';

            const meta = document.createElement('span');
            meta.className = 'client-meta';
            const ct = document.createElement('span');
            ct.textContent = c.invoice_count + (c.invoice_count === 1 ? ' invoice' : ' invoices');
            meta.appendChild(ct);
            if (c.open_flags > 0) {
                const fl = document.createElement('span');
                fl.className = 'badge-flags';
                fl.textContent = c.open_flags + (c.open_flags === 1 ? ' open flag' : ' open flags');
                meta.appendChild(fl);
            }

            li.appendChild(name);
            li.appendChild(amount);
            li.appendChild(gstin);
            li.appendChild(meta);
            list.appendChild(li);
        }
    }

    async function renderClientInvoices(root, businessWorkspaceId) {
        const tpl = document.getElementById('view-client-invoices');
        root.replaceChildren(tpl.content.cloneNode(true));
        const tbody = root.querySelector('[data-role="invoice-body"]');
        const empty = root.querySelector('[data-role="empty-hint"]');

        // Reach into clients list for name + gstin; cheaper than a dedicated
        // endpoint. Cached for this session via state; falls back to a fresh
        // fetch if absent.
        let client = (global._caClientCache || {})[businessWorkspaceId];
        if (!client) {
            try {
                const all = await window.api.get('/api/ca/clients');
                global._caClientCache = {};
                for (const c of (all.items || [])) global._caClientCache[c.workspace_id] = c;
                client = global._caClientCache[businessWorkspaceId];
            } catch (_) { /* ignore — we'll just show the id */ }
        }
        root.querySelector('[data-role="client-name"]').textContent = (client && client.name) || 'Client';
        root.querySelector('[data-role="client-gstin"]').textContent = (client && client.gstin) || '';

        let payload;
        try {
            payload = await window.api.get(
                '/api/ca/clients/' + encodeURIComponent(businessWorkspaceId) + '/invoices'
            );
        } catch (err) {
            empty.textContent = err.detail || 'Could not load invoices.';
            empty.hidden = false;
            return;
        }
        if (!payload.items || payload.items.length === 0) {
            empty.hidden = false;
            return;
        }
        empty.hidden = true;
        for (const it of payload.items) {
            const tr = document.createElement('tr');
            tr.className = 'row-link';
            tr.addEventListener('click', () => {
                window.location.hash = '#/clients/'
                    + encodeURIComponent(businessWorkspaceId)
                    + '/invoices/' + encodeURIComponent(it.invoice_id);
            });

            const cells = [
                it.vendor_name || '…',
                it.invoice_no || '—',
                fmtAmount(it.total_amount_minor, it.currency),
                it.invoice_date || '—',
            ];
            for (const text of cells) {
                const td = document.createElement('td');
                td.textContent = text;
                if (text === '…' || text === '—') td.classList.add('dim');
                tr.appendChild(td);
            }
            const flagsTd = document.createElement('td');
            const badge = document.createElement('span');
            badge.className = 'flags-count-badge' + (it.failing_rules === 0 ? ' zero' : '');
            badge.textContent = it.failing_rules === 0 ? 'clean' : String(it.failing_rules);
            flagsTd.appendChild(badge);
            tr.appendChild(flagsTd);
            tbody.appendChild(tr);
        }
    }

    global.caClients = { renderClients, renderClientInvoices };
})(window);

// Invoice detail view — plain-language fields + amber flags.

(function (global) {
    'use strict';

    function fmtAmount(minor, currency) {
        if (minor == null) return '—';
        const whole = (minor / 100).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return (currency === 'INR' ? '₹' : (currency + ' ')) + whole;
    }

    function chipFor(status) {
        if (status === 'extracted') return ['ok', 'Ready'];
        if (status === 'extracting') return ['extract', 'Extracting…'];
        if (status === 'queued') return ['queued', 'Queued'];
        if (status === 'failed') return ['failed', 'Failed'];
        if (status === 'ignored') return ['ignored', 'Ignored'];
        return ['queued', status];
    }

    async function render(root, invoiceId) {
        const tpl = document.getElementById('view-invoice');
        root.replaceChildren(tpl.content.cloneNode(true));

        let payload;
        try {
            payload = await window.api.get('/api/invoices/' + encodeURIComponent(invoiceId));
        } catch (err) {
            const wrap = root.querySelector('.invoice-fields');
            const msg = document.createElement('p');
            msg.className = 'error';
            msg.textContent = err.status === 404 ? 'Invoice not found.' : (err.detail || 'Failed to load invoice.');
            wrap.appendChild(msg);
            return;
        }

        const inv = payload.invoice;
        root.querySelector('[data-role="vendor"]').textContent = inv.vendor_name || '(vendor not yet extracted)';
        root.querySelector('[data-role="invoice-no"]').textContent = inv.invoice_no || '—';
        root.querySelector('[data-role="invoice-date"]').textContent = inv.invoice_date || '—';
        root.querySelector('[data-role="total"]').textContent = fmtAmount(inv.total_amount_minor, inv.currency);

        const chipEl = root.querySelector('[data-role="status-chip"]');
        const [cls, txt] = chipFor(inv.extraction_status);
        const chip = document.createElement('span');
        chip.className = 'status-chip ' + cls;
        chip.textContent = txt;
        chipEl.replaceChildren(chip);

        // Image (workspace-gated endpoint). Only set src if extracted;
        // 404 on a queued invoice would render a broken-image icon.
        const img = root.querySelector('[data-role="invoice-image"]');
        img.src = inv.image_url;
        img.alt = 'Uploaded invoice — ' + (inv.vendor_name || 'pending extraction');

        // Flags (FAIL findings only for business persona).
        if (payload.flags && payload.flags.length > 0) {
            root.querySelector('[data-role="flags"]').hidden = false;
            const ul = root.querySelector('[data-role="flags-list"]');
            ul.replaceChildren();
            for (const f of payload.flags) {
                const li = document.createElement('li');
                li.textContent = f.reason || f.rule_name;
                ul.appendChild(li);
            }
        }

        // If extraction is still running, auto-refresh after 2s.
        if (inv.extraction_status === 'queued' || inv.extraction_status === 'extracting') {
            setTimeout(() => {
                if (window.location.hash === '#/invoice/' + invoiceId) {
                    render(root, invoiceId);
                }
            }, 2000);
        }
    }

    global.invoice = { render };
})(window);

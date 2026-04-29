// CA-persona full invoice detail — renders every finding (PASS/FAIL/NA).

(function (global) {
    'use strict';

    function fmtAmount(minor, currency) {
        if (minor == null) return '—';
        const whole = (minor / 100).toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        });
        return (currency === 'INR' ? '₹' : (currency + ' ')) + whole;
    }

    async function render(root, businessWorkspaceId, invoiceId) {
        const tpl = document.getElementById('view-invoice');
        root.replaceChildren(tpl.content.cloneNode(true));

        const backLink = root.querySelector('[data-role="back-link"]');
        backLink.setAttribute('href', '#/clients/' + encodeURIComponent(businessWorkspaceId));
        backLink.textContent = '← Back to invoices';

        let payload;
        try {
            payload = await window.api.get(
                '/api/ca/clients/' + encodeURIComponent(businessWorkspaceId)
                + '/invoices/' + encodeURIComponent(invoiceId)
            );
        } catch (err) {
            const h1 = root.querySelector('[data-role="vendor"]');
            h1.textContent = err.status === 404 ? 'Not found' : 'Failed to load';
            return;
        }

        const inv = payload.invoice;
        root.querySelector('[data-role="vendor"]').textContent = inv.vendor_name || '(vendor pending)';
        root.querySelector('[data-role="invoice-no"]').textContent = inv.invoice_no || '—';
        root.querySelector('[data-role="invoice-date"]').textContent = inv.invoice_date || '—';
        root.querySelector('[data-role="total"]').textContent = fmtAmount(inv.total_amount_minor, inv.currency);

        // Full CA detail — image + seller GSTIN from the pipeline extraction_result blob
        const sellerGstinEl = root.querySelector('[data-role="seller-gstin"]');
        const ex = payload.extraction_result;
        const sellerField = ex && ex.fields && ex.fields.tax_id;
        sellerGstinEl.textContent = (sellerField && sellerField.value) || '—';

        const img = root.querySelector('[data-role="invoice-image"]');
        // CA-scoped image route — authorised via the workspaces.ca_gstin
        // linkage rather than direct workspace ownership.
        img.src = '/api/ca/clients/' + encodeURIComponent(businessWorkspaceId)
            + '/invoices/' + encodeURIComponent(inv.id) + '/image';
        img.alt = 'Invoice from ' + (inv.vendor_name || 'vendor');

        // All findings — grouped by outcome for CA scanability.
        const findings = payload.findings || [];
        if (findings.length === 0) return;
        root.querySelector('[data-role="findings-wrap"]').hidden = false;
        const ul = root.querySelector('[data-role="findings-list"]');
        const ordered = findings.slice().sort((a, b) => {
            // FAIL first, then PASS, then NOT_APPLICABLE.
            const rank = { FAIL: 0, PASS: 1, NOT_APPLICABLE: 2 };
            return (rank[a.outcome] ?? 3) - (rank[b.outcome] ?? 3);
        });
        for (const f of ordered) {
            const li = document.createElement('li');
            const tag = document.createElement('span');
            if (f.outcome === 'FAIL') tag.className = 'outcome-fail';
            else if (f.outcome === 'PASS') tag.className = 'outcome-pass';
            else tag.className = 'outcome-na';
            tag.textContent = f.outcome + ' · ';
            li.appendChild(tag);
            const body = document.createElement('span');
            body.textContent = f.rule_name + (f.reason ? ' — ' + f.reason : '');
            li.appendChild(body);
            ul.appendChild(li);
        }
    }

    global.caInvoice = { render };
})(window);
